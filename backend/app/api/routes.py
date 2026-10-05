import httpx
import io

from fastapi.responses import StreamingResponse

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.providers.factory import get_provider
from app.services import case_store
from app.services.pipeline import analyze_case, build_dashboard
from app.services.reconciliation import build_demo_dashboard

router = APIRouter(prefix="/api")
settings = get_settings()


class ChatRequest(BaseModel):
    message: str
    provider: str | None = None


class CaseCreateRequest(BaseModel):
    name: str = "Untitled property review"


class ExplainRequest(BaseModel):
    finding: dict
    provider: str | None = None


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.app_name}


@router.get("/config")
async def config() -> dict:
    return {
        "default_provider": settings.ai_provider,
        "providers": [
            {
                "id": "sarvam",
                "label": "Sarvam AI",
                "model": settings.sarvam_model,
                "configured": bool(settings.sarvam_api_key),
                "note": "Sarvam 105B + Document AI",
            },
            {
                "id": "openmodel",
                "label": "OpenModel",
                "model": settings.openmodel_model or "Configure OPENMODEL_MODEL",
                "configured": bool(settings.openmodel_api_key and settings.openmodel_model),
                "note": "OpenModel proxy; model selected from env",
            },
            {
                "id": "mock",
                "label": "Local Demo",
                "model": "deterministic-demo",
                "configured": True,
                "note": "Zero-key local testing",
            },
        ],
    }


@router.get("/demo/case")
async def demo_case() -> dict:
    return build_demo_dashboard()


@router.get("/cases")
async def cases() -> list[dict]:
    return case_store.list_cases()


@router.post("/cases")
async def create_case(payload: CaseCreateRequest) -> dict:
    return case_store.create_case(payload.name)


@router.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/cases/{case_id}/documents")
async def upload_case_documents(
    case_id: str,
    files: list[UploadFile] = File(...),
) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    allowed = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
    uploaded = []
    for file in files:
        if file.content_type not in allowed:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type for {file.filename}. Use PDF, PNG or JPEG.",
            )
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"{file.filename} is empty")
        uploaded.append(
            case_store.add_document(
                case_id,
                file.filename or "document",
                file.content_type or "application/octet-stream",
                content,
            )
        )

    case_store.update_case(case_id, status="ready")
    return {"case_id": case_id, "documents": uploaded}


@router.post("/cases/{case_id}/analyze")
async def analyze(
    case_id: str,
    background_tasks: BackgroundTasks,
    reasoning_provider: str | None = None,
) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.get("documents"):
        raise HTTPException(status_code=400, detail="Upload at least one document first")

    provider = reasoning_provider or settings.ai_provider
    if provider not in {"mock", "sarvam", "openmodel"}:
        raise HTTPException(status_code=400, detail="Unsupported reasoning provider")

    background_tasks.add_task(analyze_case, case_id, settings, provider)
    case_store.update_case(case_id, status="queued")
    return {"case_id": case_id, "status": "queued", "reasoning_provider": provider}


@router.get("/cases/{case_id}/dashboard")
async def case_dashboard(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.get("analysis"):
        return case["analysis"]

    return build_dashboard(case, settings.ai_provider)


@router.get("/cases/{case_id}/report")
async def case_report(case_id: str):
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    dashboard = case.get("analysis") or build_dashboard(case, settings.ai_provider)

    lines = [
        "BHOOMILENS — EVIDENCE REVIEW REPORT",
        f"Case: {case_id}",
        "",
        f"Record Consistency Score: {dashboard.get('score', '—')}/100",
        f"Status: {dashboard.get('status', '—')}",
        f"Documents reviewed: {dashboard.get('documents', 0)}",
        "",
        "PROPERTY SNAPSHOT",
        *[f"{key.title()}: {value}" for key, value in dashboard.get("property", {}).items()],
        "",
        "FINDINGS",
    ]
    for finding in dashboard.get("findings", []):
        lines.extend([
            f"{finding['id']} [{finding['severity'].upper()}] {finding['title']}",
            finding["summary"],
            f"Confidence: {round(finding.get('confidence', 1) * 100)}%",
            f"Verification: {finding.get('verification_action') or 'Review source documents.'}",
        ])
        for evidence in finding.get("evidence", []):
            lines.append(f"  - {evidence['document']} p.{evidence['page']} · {evidence['field']}: {evidence['value']}")
        lines.append("")

    lines.extend([
        "DISCLAIMER",
        "AI-assisted screening only. This report does not establish legal title, ownership, fraud, or litigation status.",
    ])
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bhoomilens-{case_id}.txt"'},
    )


@router.post("/cases/{case_id}/explain")
async def explain_case(case_id: str, payload: ExplainRequest) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    provider = get_provider(settings, payload.provider)
    context = payload.finding
    result = await provider.chat(
        system=(
            "You are BhoomiLens. Explain a land-record inconsistency using only the supplied "
            "evidence. Do not claim legal title, fraud, or litigation status. Distinguish a "
            "contradiction from an ambiguity and end with a verification action."
        ),
        user=(
            "Case evidence:\n"
            f"{context}\n\n"
            "Explain this finding in 3 concise parts: what the records say, why it matters, "
            "and what should be verified next."
        ),
    )
    return {"provider": result.provider, "model": result.model, "answer": result.text}


@router.post("/chat")
async def chat(payload: ChatRequest) -> dict:
    provider = get_provider(settings, payload.provider)
    result = await provider.chat(
        system=(
            "You are BhoomiLens, an evidence-constrained land-record reconciliation assistant. "
            "Do not claim legal title or fraud. Explain findings only from supplied context and "
            "be explicit when evidence is insufficient."
        ),
        user=payload.message,
    )
    return {"provider": result.provider, "model": result.model, "answer": result.text}


@router.post("/documents/extract")
async def upload_for_extraction(
    file: UploadFile = File(...),
    schema: str = Form(...),
    language: str = Form("en-IN"),
):
    if not settings.sarvam_api_key:
        return {
            "status": "demo",
            "message": "Sarvam Document AI is not configured. Use AI_PROVIDER=mock for zero-key testing.",
            "filename": file.filename,
        }

    content = await file.read()
    headers = {"api-subscription-key": settings.sarvam_api_key}
    form = {
        "schema": schema,
        "language": language,
        "output_format": "json",
        "classification": "true",
        "auto_orient": "true",
        "model": "sarvam-vision-v1",
    }
    files = [
        (
            "file",
            (
                file.filename or "document",
                content,
                file.content_type or "application/octet-stream",
            ),
        )
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.sarvam_base_url.rstrip('/')}/doc-ai/v1/job/extract",
            headers=headers,
            data=form,
            files=files,
        )

    if response.status_code >= 400:
        return JSONResponse(status_code=response.status_code, content=response.json())

    return response.json()


@router.get("/documents/extract/{job_id}")
async def extraction_status(job_id: str):
    if not settings.sarvam_api_key:
        return {"status": "demo", "job_id": job_id}

    headers = {"api-subscription-key": settings.sarvam_api_key}
    base = settings.sarvam_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=30) as client:
        status_response = await client.get(
            f"{base}/doc-ai/v1/job/{job_id}/status",
            headers=headers,
        )
        if status_response.status_code >= 400:
            return JSONResponse(
                status_code=status_response.status_code,
                content=status_response.json(),
            )

        status = status_response.json()
        if status.get("status") in {
            "completed",
            "partially_completed",
            "failed",
            "rejected",
        }:
            result_response = await client.get(
                f"{base}/doc-ai/v1/job/{job_id}/results?format=json",
                headers=headers,
            )
            if result_response.status_code < 400:
                return result_response.json()

    return status
