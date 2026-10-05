import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.services import case_store
from app.services.normalization import normalize_document
from app.services.rules import build_coverage, reconcile_documents

EXTRACTION_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "document_type": {
                "type": "string",
                "description": "Land record document type such as RTC, mutation extract, sale deed, or encumbrance certificate",
            },
            "owner_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All owner or rights-holder names in the document",
            },
            "survey_number": {
                "type": "string",
                "description": "Survey number exactly as written",
            },
            "land_extent": {
                "type": "string",
                "description": "Recorded land extent with unit",
            },
            "village": {"type": "string", "description": "Village name"},
            "taluk": {"type": "string", "description": "Taluk name"},
            "district": {"type": "string", "description": "District name"},
            "document_date": {"type": "string", "description": "Date on the document"},
            "transaction_date": {"type": "string", "description": "Transaction date if present"},
        },
    }
)


def _fixture_for(filename: str) -> dict[str, Any]:
    name = filename.casefold()
    base = {
        "village": "example village",
        "taluk": "example taluk",
        "district": "example district",
        "owner_names": ["Ramesh Kumar"],
        "survey_number": "128/3A",
        "land_extent": "2.10 acres",
        "document_date": "2024-08-14",
    }
    if "sale" in name or "deed" in name:
        base.update(
            {
                "document_type": "Sale Deed",
                "survey_number": "128/3",
                "land_extent": "1.84 acres",
                "transaction_date": "2024-08-14",
            }
        )
    elif "mutation" in name:
        base.update({"document_type": "Mutation Extract", "transaction_date": "2021-04-02"})
    elif "ec" in name or "encumbrance" in name:
        base.update({"document_type": "Encumbrance Certificate"})
    elif "rtc" in name or "pahani" in name:
        base.update({"document_type": "RTC"})
    else:
        base.update({"document_type": "Other"})
    return base


async def _submit_sarvam(settings: Settings, document: dict[str, Any]) -> dict[str, Any]:
    headers = {"api-subscription-key": settings.sarvam_api_key or ""}
    form = {
        "schema": EXTRACTION_SCHEMA,
        "language": "en-IN",
        "output_format": "json",
        "classification": "true",
        "auto_orient": "true",
        "model": "sarvam-vision-v1",
    }
    path = Path(document["storage_path"])
    content = path.read_bytes()
    files = [("file", (document["filename"], content, document["content_type"] or "application/octet-stream"))]

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{settings.sarvam_base_url.rstrip('/')}/doc-ai/v1/job/extract",
            headers=headers,
            data=form,
            files=files,
        )
        response.raise_for_status()
        return response.json()


async def _poll_sarvam(settings: Settings, job_id: str) -> dict[str, Any]:
    base = settings.sarvam_base_url.rstrip("/")
    headers = {"api-subscription-key": settings.sarvam_api_key or ""}
    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(45):
            status = await client.get(f"{base}/doc-ai/v1/job/{job_id}/status", headers=headers)
            status.raise_for_status()
            payload = status.json()
            if payload.get("status") in {"completed", "partially_completed", "failed", "rejected"}:
                if payload.get("status") in {"failed", "rejected"}:
                    return payload
                result = await client.get(
                    f"{base}/doc-ai/v1/job/{job_id}/results?format=json",
                    headers=headers,
                )
                result.raise_for_status()
                return result.json()
            await asyncio.sleep(2)
    return {"status": "timeout", "job_id": job_id}


def _extract_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result", payload)
    if isinstance(result, dict) and "result" in result and isinstance(result["result"], dict):
        result = result["result"]
    return result if isinstance(result, dict) else {}


def build_dashboard(case: dict[str, Any], reasoning_provider: str = "mock") -> dict[str, Any]:
    documents = list(case.get("documents", {}).values())
    findings = reconcile_documents(documents)
    coverage = build_coverage(documents)

    score = max(0, 100 - sum(item.score_impact for item in findings))
    if score >= 90:
        status = "High consistency"
    elif score >= 75:
        status = "Needs review"
    elif score >= 50:
        status = "Significant review"
    else:
        status = "Material inconsistencies"

    normalized = [item.get("normalized", {}) for item in documents if item.get("normalized")]
    first = normalized[0] if normalized else {}
    owners = [name for item in normalized for name in item.get("owner_names", [])]

    return {
        "case_id": case["id"],
        "documents": len(documents),
        "fields_extracted": sum(len(item.get("extracted", {})) for item in documents),
        "entities_normalized": sum(
            len(item.get("normalized", {}).get("owner_names", []))
            + int(bool(item.get("normalized", {}).get("survey_number")))
            for item in documents
        ),
        "score": score,
        "status": status,
        "property": {
            "village": first.get("village") or "Not established",
            "taluk": first.get("taluk") or "Not established",
            "district": first.get("district") or "Not established",
            "survey": first.get("survey_number") or "Not established",
            "owner": owners[0] if owners else "Not established",
        },
        "findings": [item.model_dump() for item in findings],
        "coverage": coverage,
        "timeline": [],
        "extraction_status": case.get("status", "draft"),
        "reasoning_provider": reasoning_provider,
    }


async def analyze_case(case_id: str, settings: Settings, reasoning_provider: str = "mock") -> None:
    case = case_store.get_case(case_id)
    if not case:
        return

    case_store.update_case(case_id, status="processing", analysis=None)

    documents = list(case.get("documents", {}).values())

    try:
        for document in documents:
            if settings.sarvam_api_key:
                submitted = await _submit_sarvam(settings, document)
                job_id = submitted.get("job_id")
                case_store.update_document(
                    case_id,
                    document["id"],
                    status="processing",
                    job_id=job_id,
                )
                result = await _poll_sarvam(settings, job_id)
                extracted = _extract_result(result)
                case_store.update_document(
                    case_id,
                    document["id"],
                    status="completed" if result.get("status") not in {"failed", "rejected", "timeout"} else result.get("status"),
                    extracted=extracted,
                    normalized=normalize_document(extracted),
                    annotations=result.get("annotations", {}),
                )
            else:
                extracted = _fixture_for(document["filename"])
                case_store.update_document(
                    case_id,
                    document["id"],
                    status="completed",
                    extracted=extracted,
                    normalized=normalize_document(extracted),
                )

        fresh = case_store.get_case(case_id) or case
        dashboard = build_dashboard(fresh, reasoning_provider)
        case_store.update_case(case_id, status="completed", analysis=dashboard)

    except Exception as exc:
        case_store.update_case(
            case_id,
            status="failed",
            analysis={"error": str(exc), "case_id": case_id},
        )
