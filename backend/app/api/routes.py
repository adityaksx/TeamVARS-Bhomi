import httpx

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.providers.factory import get_provider
from app.services.reconciliation import build_demo_dashboard

router = APIRouter(prefix="/api")
settings = get_settings()


class ChatRequest(BaseModel):
    message: str
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
