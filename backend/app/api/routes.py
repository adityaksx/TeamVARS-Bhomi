import httpx
import io
from fastapi.responses import StreamingResponse

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.providers.factory import get_provider
from app.services import case_store
from app.services.document_view import render_page
from app.services.pipeline import analyze_case, build_dashboard
from app.services.storage import materialize, read_bytes
from app.services.upload_validation import (
    UploadValidationError,
    read_limited,
    safe_filename,
    validate_case_batch,
    validate_file_signature,
)
from app.services.reporting import build_pdf_report
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
        "document_limits": {
            "max_upload_mb": settings.max_upload_mb,
            "max_case_upload_mb": settings.max_case_upload_mb,
            "max_documents_per_case": settings.max_documents_per_case,
        },
        "storage": {
            "backend": settings.document_storage_backend,
        },
        "land_records": {
            "state": settings.land_record_state,
            "state_name": "Uttar Pradesh",
            "language": settings.sarvam_document_language,
            "document_types": [
                "Khatauni",
                "Gata / Khasra",
                "Mutation / Namantaran",
                "Sale Deed",
                "Encumbrance / Litigation",
            ],
        },
        "providers": [
            {
                "id": "sarvam",
                "label": "Sarvam AI",
                "model": settings.sarvam_model,
                "configured": bool(settings.sarvam_api_key),
                "note": "Sarvam 105B + Document AI",
            },
            {
                "id": "nvidia",
                "label": "NVIDIA NIM",
                "model": settings.nvidia_model,
                "configured": bool(settings.nvidia_api_key),
                "note": "OpenAI-compatible NVIDIA cloud reasoning",
            },
            {
                "id": "ollama",
                "label": "Ollama Local",
                "model": settings.ollama_model,
                "configured": True,
                "note": "Local model; no API key required",
            },
            {
                "id": "openmodel",
                "label": "OpenModel (legacy)",
                "model": settings.openmodel_model or "Configure OPENMODEL_MODEL",
                "configured": bool(settings.openmodel_api_key and settings.openmodel_model),
                "note": "Legacy provider kept for compatibility",
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

    incoming = []
    try:
        for file in files:
            content = await read_limited(
                file,
                settings.max_upload_mb * 1024 * 1024,
            )
            filename = safe_filename(file.filename)
            detected_type = validate_file_signature(
                filename,
                file.content_type,
                content,
            )
            incoming.append((filename, detected_type, content))

        existing_documents = list(case.get("documents", {}).values())
        validate_case_batch(
            existing_document_count=len(existing_documents),
            existing_bytes=sum(int(item.get("size") or 0) for item in existing_documents),
            incoming_sizes=(len(content) for _, _, content in incoming),
            max_documents=settings.max_documents_per_case,
            max_case_bytes=settings.max_case_upload_mb * 1024 * 1024,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploaded = []
    try:
        for filename, detected_type, content in incoming:
            uploaded.append(
                case_store.add_document(
                    case_id,
                    filename,
                    detected_type,
                    content,
                )
            )
    except Exception:
        case_store.update_case(case_id, status="failed")
        raise

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
    if provider not in {"mock", "sarvam", "nvidia", "ollama", "local", "openmodel"}:
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


@router.get("/cases/{case_id}/documents/{document_id}/page/{page_number}")
async def document_page(case_id: str, document_id: str, page_number: int):
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    document = case.get("documents", {}).get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if page_number < 1:
        raise HTTPException(status_code=400, detail="Page number must be at least 1")

    storage_ref = document["storage_path"]
    content_type = document.get("content_type", "")
    try:
        if content_type == "application/pdf":
            with materialize(storage_ref) as path:
                content, width, height = render_page(path, page_number)
            return StreamingResponse(
                io.BytesIO(content),
                media_type="image/png",
                headers={"X-Page-Width": str(width), "X-Page-Height": str(height)},
            )

        if page_number != 1:
            raise HTTPException(status_code=416, detail="Image documents contain one page")
        payload = read_bytes(storage_ref)
        return StreamingResponse(
            io.BytesIO(payload),
            media_type=content_type or "application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{document.get("filename", "document")}"'},
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document file not found") from exc


@router.get("/cases/{case_id}/documents/{document_id}/content")
async def document_content(case_id: str, document_id: str):
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    document = case.get("documents", {}).get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        payload = read_bytes(document["storage_path"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document file not found") from exc

    return StreamingResponse(
        io.BytesIO(payload),
        media_type=document.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{document.get("filename", "document")}"'},
    )


@router.get("/cases/{case_id}/report/pdf")
async def case_report_pdf(case_id: str):
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    dashboard = case.get("analysis") or build_dashboard(case, settings.ai_provider)
    payload = build_pdf_report(case, dashboard)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="bhoomilens-{case_id}.pdf"'},
    )


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

    try:
        content = await read_limited(
            file,
            settings.max_upload_mb * 1024 * 1024,
        )
        filename = safe_filename(file.filename)
        detected_type = validate_file_signature(
            filename,
            file.content_type,
            content,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = {"api-subscription-key": settings.sarvam_api_key}
    form = {
        "schema": schema,
        "language": language,
        "output_format": "json",
        "classification": "true",
        "model": "sarvam-vision-v1",
    }
    files = [
        (
            "file",
            (
                filename,
                content,
                detected_type,
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
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = {"error": response.text[:2000]}
        return JSONResponse(status_code=response.status_code, content=error_payload)

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
            try:
                error_payload = status_response.json()
            except ValueError:
                error_payload = {"error": status_response.text[:2000]}
            return JSONResponse(
                status_code=status_response.status_code,
                content=error_payload,
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
