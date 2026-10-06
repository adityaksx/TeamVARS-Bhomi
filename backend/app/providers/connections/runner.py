import statistics
from typing import Any, Dict, List, Optional
from app.core.config import Settings, get_settings

from .base import BaseProviderConnection
from .models import ProviderTestResult
from .errors import ProviderErrorCode
from .sarvam import SarvamConnection
from .gemini import GeminiConnection
from .ollama import OllamaConnection


class ProviderRunner:
    @staticmethod
    def create_connection(
        provider: str,
        settings: Optional[Settings] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> BaseProviderConnection:
        cfg = settings or get_settings()
        prov = (provider or "ollama").lower()

        if prov in {"local", "ollama"}:
            return OllamaConnection(
                base_url=base_url or cfg.ollama_base_url,
                model=model or cfg.ollama_model,
            )
        elif prov == "sarvam":
            return SarvamConnection(
                api_key=api_key or cfg.sarvam_api_key,
                base_url=base_url or cfg.sarvam_base_url,
                model=model or cfg.sarvam_model,
            )
        elif prov == "gemini":
            return GeminiConnection(
                api_key=api_key or cfg.gemini_api_key,
                base_url=base_url or cfg.gemini_base_url,
                model=model or cfg.gemini_model,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")


async def test_provider_connection(
    provider: str,
    settings: Optional[Settings] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> ProviderTestResult:
    """Test connection to a single provider with normalized output."""
    try:
        conn = ProviderRunner.create_connection(
            provider=provider,
            settings=settings,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        return await conn.test_connection()
    except Exception as exc:
        return ProviderTestResult(
            provider=provider,
            configured=False,
            connected=False,
            usable=False,
            model=model or "unknown",
            error_code=ProviderErrorCode.UNKNOWN_PROVIDER_ERROR,
            error_message=f"Failed to initialize provider {provider}: {exc}",
        )


async def test_provider_repeated(
    provider: str,
    repeat: int = 3,
    settings: Optional[Settings] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute repeated connectivity tests (1-5 times) with statistical aggregation.

    Stops early if a non-retryable error occurs (e.g. invalid API key).
    """
    repeat = max(1, min(repeat, 5))
    results: List[ProviderTestResult] = []

    for i in range(repeat):
        result = await test_provider_connection(
            provider=provider,
            settings=settings,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        results.append(result)

        # If non-retryable error on first run, do not burn quota or repeat failures
        if not result.usable and not result.retryable:
            break

    passes = [r for r in results if r.usable]
    latencies = [r.latency_ms for r in passes]

    summary = {
        "provider": provider,
        "runs_attempted": len(results),
        "runs_requested": repeat,
        "passed": len(passes),
        "failed": len(results) - len(passes),
        "success_rate": round(len(passes) / len(results) * 100, 1) if results else 0.0,
        "median_latency_ms": int(statistics.median(latencies)) if latencies else None,
        "min_latency_ms": min(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
        "results": [r.model_dump() for r in results],
        "final_result": results[-1].model_dump() if results else None,
    }
    return summary
