import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.services import case_store
from app.services.document_view import build_source_anchors, page_count
from app.services.normalization import normalize_document
from app.services.pdf_utils import split_pdf
from app.services.rules import build_coverage, reconcile_documents
from app.adapters.uttar_pradesh import adapt_up_document
from app.services.storage import materialize
from app.services.fallback_extraction import extract_with_fallback

EXTRACTION_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "document_type": {
                "type": "string",
                "description": "Uttar Pradesh land-record document type such as Khatauni, Gata/Khasra, Mutation/Namantaran, Sale Deed, or encumbrance/litigation record",
            },
            "owner_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All Khatedar/owner/rights-holder names; preserve original script where available",
            },
            "previous_owner_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Previous owner names when this is a mutation/ownership transition record",
            },
            "new_owner_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New owner names when this is a mutation/ownership transition record",
            },
            "survey_number": {
                "type": "string",
                "description": "Gata/Khasra/plot identifier exactly as written; preserve subdivision notation",
            },
            "gata_number": {
                "type": "string",
                "description": "Gata number when explicitly labeled",
            },
            "khasra_number": {
                "type": "string",
                "description": "Khasra number when explicitly labeled",
            },
            "land_extent": {
                "type": "string",
                "description": "Recorded land area/extent with unit, exactly as written",
            },
            "village": {"type": "string", "description": "Village / Gram name"},
            "tehsil": {"type": "string", "description": "Tehsil name"},
            "district": {"type": "string", "description": "District / Janpad name"},
            "mutation_number": {"type": "string", "description": "Mutation/Namantaran entry or order number if present"},
            "document_date": {"type": "string", "description": "Date on the document"},
            "transaction_date": {"type": "string", "description": "Transaction/registration date if present"},
        },
    }
)


def _fixture_for(filename: str) -> dict[str, Any]:
    name = filename.casefold()
    base = {
        "document_type": "Khatauni",
        "village": "sikandra",
        "tehsil": "agra sadar",
        "district": "agra",
        "owner_names": ["Ramesh Kumar"],
        "survey_number": "124",
        "gata_number": "124",
        "land_extent": "2.50 acres",
        "document_date": "2025-08-14",
    }
    if "sale" in name or "deed" in name or "registry" in name:
        base.update(
            {
                "document_type": "Sale Deed",
                "survey_number": "124/3",
                "gata_number": "124/3",
                "land_extent": "2.10 acres",
                "transaction_date": "2025-08-14",
            }
        )
    elif "mutation" in name or "namantaran" in name:
        base.update(
            {
                "document_type": "Mutation / Namantaran",
                "previous_owner_names": ["Ramesh Kumar"],
                "new_owner_names": ["Suresh Kumar"],
                "owner_names": ["Ramesh Kumar", "Suresh Kumar"],
                "mutation_number": "MUT-2025-0412",
                "transaction_date": "2025-09-02",
            }
        )
        if "mismatch" in name:
            base["new_owner_names"] = ["Rajesh Kumar"]
            base["owner_names"] = ["Ramesh Kumar", "Rajesh Kumar"]
    elif "gata" in name or "khasra" in name:
        base.update({"document_type": "Gata / Khasra"})
    elif "litigation" in name or "encumbrance" in name or "ec" in name:
        base.update({"document_type": "Encumbrance / Litigation"})
    elif "khatauni" in name or "khatoni" in name:
        base.update({"document_type": "Khatauni"})
    else:
        base.update({"document_type": "Other"})
    return base


def _annotation_page(annotation: Any) -> int | None:
    if not isinstance(annotation, dict):
        return None
    sources = annotation.get("sources")
    if not isinstance(sources, list):
        return None

    for source in sources:
        if not isinstance(source, dict):
            continue
        page = source.get("page") or source.get("page_number") or source.get("pageIndex")
        if isinstance(page, int):
            return page + 1 if source.get("pageIndex") is not None else page
    return None


def _merge_chunk_results(
    chunks: list[tuple[dict[str, Any], dict[str, Any], int]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    merged: dict[str, Any] = {}
    annotations: dict[str, Any] = {}
    source_pages: dict[str, int] = {}

    for result, chunk_annotations, page_offset in chunks:
        for key, value in result.items():
            if value in (None, "", []):
                continue
            if key not in merged or merged[key] in (None, "", []):
                merged[key] = value
            elif isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = list(dict.fromkeys(merged[key] + value))

        if isinstance(chunk_annotations, dict):
            for key, value in chunk_annotations.items():
                annotations.setdefault(key, value)
                page = _annotation_page(value)
                if page is not None:
                    adjusted = page + page_offset
                    source_pages[key] = min(source_pages.get(key, adjusted), adjusted)

    return merged, annotations, source_pages


async def _submit_sarvam(
    settings: Settings,
    document: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    headers = {"api-subscription-key": settings.sarvam_api_key or ""}
    form = {
        "schema": EXTRACTION_SCHEMA,
        "language": settings.sarvam_document_language,
        "output_format": "json",
    }
    content = path.read_bytes()
    files = [
        (
            "file",
            (
                path.name,
                content,
                document["content_type"] or "application/pdf",
            ),
        )
    ]

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{settings.sarvam_base_url.rstrip('/')}/doc-ai/v1/job/extract",
            headers=headers,
            data=form,
            files=files,
        )
        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {"error": response.text[:2000]}
            raise RuntimeError(
                f"Sarvam Document AI extract failed ({response.status_code}): {error_payload}"
            )
        return response.json()


async def _poll_sarvam(settings: Settings, job_id: str) -> dict[str, Any]:
    base = settings.sarvam_base_url.rstrip("/")
    headers = {"api-subscription-key": settings.sarvam_api_key or ""}
    async with httpx.AsyncClient(timeout=60) as client:
        for _ in range(45):
            status = await client.get(
                f"{base}/doc-ai/v1/job/{job_id}/status",
                headers=headers,
            )
            if status.status_code >= 400:
                try:
                    error_payload = status.json()
                except ValueError:
                    error_payload = {"error": status.text[:2000]}
                raise RuntimeError(
                    f"Sarvam Document AI status failed ({status.status_code}): {error_payload}"
                )
            payload = status.json()

            if payload.get("status") in {
                "completed",
                "partially_completed",
                "failed",
                "rejected",
            }:
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


def _sarvam_value_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("raw") or value.get("acres") or value.get("value") or ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _text_tokens(value: Any) -> list[str]:
    import re

    return [token for token in re.findall(r"[\w./-]+", _sarvam_value_text(value).casefold()) if token]


def _block_anchor(block: dict[str, Any], target: Any, page: dict[str, Any], page_offset: int) -> dict[str, Any] | None:
    text = str(block.get("text") or "")
    target_tokens = _text_tokens(target)
    block_tokens = _text_tokens(text)
    if not target_tokens or not block_tokens:
        return None
    normalized_target = " ".join(target_tokens)
    normalized_block = " ".join(block_tokens)
    if normalized_target not in normalized_block:
        return None

    bbox = block.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    try:
        coords = [float(value) for value in bbox[:4]]
        width = float(page.get("width") or 0)
        height = float(page.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None

    if str(page.get("origin") or "").casefold() in {"bottom-left", "bottom_left"}:
        coords[1], coords[3] = height - coords[3], height - coords[1]

    confidence = block.get("ocr_confidence")
    if confidence is None:
        confidence = block.get("layout_confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    return {
        "page": int(page.get("page_num") or page.get("page_number") or 1) + page_offset,
        "page_width": round(width, 2),
        "page_height": round(height, 2),
        "bbox": [round(coord, 2) for coord in coords],
        "text": text,
        "method": "sarvam-digitise",
        "confidence": round(confidence, 3) if confidence is not None else None,
        "source": "Sarvam Document AI Digitise",
    }


def _digitise_anchors(payload: dict[str, Any], normalized: dict[str, Any], page_offset: int = 0) -> dict[str, Any]:
    result = payload.get("result", payload)
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        result = result["result"]
    pages = result.get("pages", []) if isinstance(result, dict) else []
    if not isinstance(pages, list):
        return {}

    targets: list[tuple[str, Any]] = [
        ("survey_number", normalized.get("survey_number")),
        ("land_extent", normalized.get("land_extent")),
        ("village", normalized.get("village")),
        ("taluk", normalized.get("taluk")),
        ("district", normalized.get("district")),
        ("document_date", normalized.get("document_date")),
        ("transaction_date", normalized.get("transaction_date")),
        ("document_type", normalized.get("document_type")),
    ]
    targets.extend((f"owner_names:{owner.casefold()}", owner) for owner in normalized.get("owner_names", []))

    anchors: dict[str, Any] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        blocks = page.get("blocks", [])
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for key, target in targets:
                if key in anchors or target in (None, "", []):
                    continue
                anchor = _block_anchor(block, target, page, page_offset)
                if anchor:
                    anchors[key] = anchor
    return anchors


async def _submit_sarvam_digitise(settings: Settings, document: dict[str, Any], path: Path) -> dict[str, Any]:
    headers = {"api-subscription-key": settings.sarvam_api_key or ""}
    form = {
        "language": settings.sarvam_document_language,
        "output_format": "json",
    }
    content = path.read_bytes()
    files = [("file", (path.name, content, document["content_type"] or "application/pdf"))]
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{settings.sarvam_base_url.rstrip('/')}/doc-ai/v1/job/digitise",
            headers=headers,
            data=form,
            files=files,
        )
        response.raise_for_status()
        return response.json()


async def _poll_sarvam_digitise(settings: Settings, job_id: str) -> dict[str, Any]:
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
                result = await client.get(f"{base}/doc-ai/v1/job/{job_id}/results?format=json", headers=headers)
                result.raise_for_status()
                return result.json()
            await asyncio.sleep(2)
    return {"status": "timeout", "job_id": job_id}


def _extract_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result", payload)
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
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

    timeline = []
    for document in documents:
        normalized_doc = document.get("normalized", {})
        event_date = normalized_doc.get("transaction_date") or normalized_doc.get("document_date")
        if event_date:
            timeline.append(
                {
                    "date": str(event_date),
                    "label": f"{normalized_doc.get('document_type') or document.get('filename', 'Document')} reviewed",
                    "type": (normalized_doc.get("document_type") or "record").casefold(),
                }
            )
    timeline.sort(key=lambda item: item["date"])

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
            "state": "Uttar Pradesh",
            "village": first.get("village") or "Not established",
            "tehsil": first.get("tehsil") or first.get("taluk") or "Not established",
            "taluk": first.get("tehsil") or first.get("taluk") or "Not established",
            "district": first.get("district") or "Not established",
            "survey": first.get("plot_number") or first.get("survey_number") or "Not established",
            "owner": owners[0] if owners else "Not established",
        },
        "findings": [item.model_dump() for item in findings],
        "confidence": round(sum(item.confidence for item in findings) / len(findings), 2) if findings else 1.0,
        "coverage": coverage,
        "timeline": timeline,
        "extraction_status": case.get("status", "draft"),
        "reasoning_provider": reasoning_provider,
    }


async def analyze_case(
    case_id: str,
    settings: Settings,
    reasoning_provider: str = "mock",
) -> None:
    case = case_store.get_case(case_id)
    if not case:
        return

    case_store.update_case(case_id, status="processing", analysis=None)
    documents = list(case.get("documents", {}).values())

    try:
        for document in documents:
            with materialize(document["storage_path"]) as original:
                is_pdf = original.suffix.casefold() == ".pdf"
                chunk_dir = case_store.UPLOADS / case_id / f"{document['id']}_chunks"

                try:
                    if settings.sarvam_api_key and is_pdf:
                        chunks = split_pdf(original, chunk_dir)
                    else:
                        chunks = [type(
                            "Chunk",
                            (),
                            {
                                "path": original,
                                "start_page": 1,
                                "end_page": 1,
                            },
                        )()]

                    chunk_results = []
                    digitise_results = []
                    latest_job_id = None

                    extraction_provider = 'sarvam'
                    merged = None
                    annotations = {}
                    source_pages = {}
                    sarvam_error = None

                    if settings.sarvam_api_key and extraction_provider in {'auto', 'fallback', 'sarvam'}:
                        try:
                            for chunk in chunks:
                                submitted = await _submit_sarvam(settings, document, chunk.path)
                                latest_job_id = submitted.get('job_id')
                                if not latest_job_id:
                                    raise RuntimeError(f'Sarvam extraction did not return a job ID for {document["filename"]}.')
                                result_payload = await _poll_sarvam(settings, latest_job_id)
                                extracted = _extract_result(result_payload)
                                chunk_results.append((extracted, result_payload.get('annotations', {}), chunk.start_page - 1))
                                if settings.sarvam_digitise_enabled and is_pdf:
                                    digitise_job = await _submit_sarvam_digitise(settings, document, chunk.path)
                                    digitise_job_id = digitise_job.get('job_id')
                                    if digitise_job_id:
                                        digitise_results.append((await _poll_sarvam_digitise(settings, digitise_job_id), chunk.start_page - 1))
                            merged, annotations, source_pages = _merge_chunk_results(chunk_results)
                        except Exception as exc:
                            sarvam_error = str(exc)
                            merged = None

                    if not merged:
                        try:
                            merged, extraction_provider = await extract_with_fallback(
                                settings, original, EXTRACTION_SCHEMA,
                                extraction_provider if extraction_provider in {'gemini', 'grok', 'ollama', 'local'} else 'auto',
                            )
                        except Exception as fallback_error:
                            if sarvam_error:
                                raise RuntimeError(
                                    f"Sarvam extraction failed: {sarvam_error}; "
                                    f"AI fallback failed: {fallback_error}"
                                ) from fallback_error
                            raise
                        source_pages = {'owner_names': 1, 'survey_number': 1, 'land_extent': 1}

                    merged = adapt_up_document(merged)
                    normalized = normalize_document(merged)
                    source_anchors = {}
                    local_page_count = None
                    if is_pdf:
                        for digitise_payload, page_offset in digitise_results:
                            for key, anchor in _digitise_anchors(
                                digitise_payload,
                                normalized,
                                page_offset,
                            ).items():
                                source_anchors.setdefault(key, anchor)

                        for key, value in build_source_anchors(
                            original,
                            normalized,
                            source_pages,
                        ).items():
                            source_anchors.setdefault(key, value)

                        local_page_count = page_count(original)

                    update_fields = {
                        "status": "completed",
                        "extracted": merged,
                        "normalized": normalized,
                        "annotations": annotations,
                        "source_pages": source_pages,
                        "source_anchors": source_anchors,
                        "page_count": local_page_count,
                    }
                    if latest_job_id:
                        update_fields["job_id"] = latest_job_id

                    case_store.update_document(
                        case_id,
                        document["id"],
                        **update_fields,
                    )
                finally:
                    if chunk_dir.exists() and chunk_dir != original.parent:
                        shutil.rmtree(chunk_dir, ignore_errors=True)

        fresh = case_store.get_case(case_id) or case
        dashboard = build_dashboard(fresh, reasoning_provider)
        case_store.update_case(
            case_id,
            status="completed",
            analysis=dashboard,
        )

    except Exception as exc:
        case_store.update_case(
            case_id,
            status="failed",
            analysis={"error": str(exc), "case_id": case_id},
        )
