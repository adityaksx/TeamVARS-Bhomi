from fastapi import HTTPException

from app.core.config import Settings
from .base import AIProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openmodel import OpenModelProvider
from .sarvam import SarvamProvider
from .gemini import GeminiProvider


def get_provider(settings: Settings, override: str | None = None) -> AIProvider:
    provider = (override or settings.ai_provider).lower()

    if provider in {"auto", "fallback"}:
        if settings.sarvam_api_key:
            provider = "sarvam"
        elif settings.gemini_api_key:
            provider = "gemini"
        elif settings.grok_api_key:
            provider = "grok"
        else:
            provider = "ollama"

    if provider == "mock":
        return MockProvider()

    if provider == "sarvam":
        if not settings.sarvam_api_key:
            raise HTTPException(status_code=503, detail="SARVAM_API_KEY is not configured")
        return SarvamProvider(
            settings.sarvam_api_key,
            settings.sarvam_base_url,
            settings.sarvam_model,
        )

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured")
        return GeminiProvider(settings.gemini_api_key, settings.gemini_base_url, settings.gemini_model)

    if provider == "grok":
        if not settings.grok_api_key:
            raise HTTPException(status_code=503, detail="GROK_API_KEY is not configured")
        from .openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider("grok", settings.grok_api_key, settings.grok_base_url, settings.grok_model)

    if provider in {"ollama", "local"}:
        return OllamaProvider(
            settings.ollama_base_url,
            settings.ollama_model,
        )

    if provider == "openmodel":
        if not settings.openmodel_api_key or not settings.openmodel_model:
            raise HTTPException(
                status_code=503,
                detail="OPENMODEL_API_KEY and OPENMODEL_MODEL are required",
            )
        return OpenModelProvider(
            settings.openmodel_api_key,
            settings.openmodel_base_url,
            settings.openmodel_model,
        )

    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
