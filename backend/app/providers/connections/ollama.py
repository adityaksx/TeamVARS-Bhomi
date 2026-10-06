import time
from typing import Any, Dict, List, Optional
import httpx

from .base import BaseProviderConnection
from .models import ProviderTestResult, ProviderChatResult
from .errors import ProviderErrorCode, ProviderError, classify_http_error


class OllamaConnection(BaseProviderConnection):
    provider = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        timeout: float = 60.0,
        enable_thinking: bool = False,
    ):
        clean_url = base_url.rstrip("/")
        if clean_url.endswith("/v1"):
            clean_url = clean_url[:-3]
        self.base_url = clean_url
        self.model = model or "qwen3:8b"
        self.timeout = timeout
        self.enable_thinking = enable_thinking

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    async def list_models(self) -> List[Dict[str, Any]]:
        """Query Ollama /api/tags to list installed models and their metadata."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return data.get("models", [])
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(
                    code=ProviderErrorCode.OLLAMA_UNAVAILABLE,
                    message=f"Ollama is unreachable at {self.base_url}: {exc}",
                    retryable=False,
                ) from exc

    async def test_connection(self) -> ProviderTestResult:
        start_time = time.perf_counter()

        # 1. Check service availability & discover installed models
        try:
            installed_models = await self.list_models()
        except ProviderError as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=False,
                usable=False,
                model=self.model,
                latency_ms=elapsed_ms,
                error_code=exc.code,
                error_message=exc.message,
            )

        installed_names = [
            m.get("name") for m in installed_models if m.get("name")
        ]
        installed_names_bare = [
            name.split(":")[0] for name in installed_names
        ]

        # 2. Check if selected model is installed
        model_installed = (
            self.model in installed_names
            or self.model in installed_names_bare
            or any(m.startswith(f"{self.model}:") for m in installed_names)
        )
        if not model_installed:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=True,
                usable=False,
                model=self.model,
                latency_ms=elapsed_ms,
                error_code=ProviderErrorCode.OLLAMA_MODEL_NOT_FOUND,
                error_message=(
                    f"Model '{self.model}' is not installed in Ollama. "
                    f"Installed models: {', '.join(installed_names) or 'none'}."
                ),
                details={"installed_models": installed_names},
            )

        # 3. Minimal generation test via native /api/chat with think=False for speed
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Reply exactly: OK"},
            ],
            "stream": False,
            "think": self.enable_thinking,
            "options": {
                "num_predict": 30,
                "temperature": 0.1,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return ProviderTestResult(
                    provider=self.provider,
                    configured=True,
                    connected=True,
                    usable=False,
                    model=self.model,
                    latency_ms=elapsed_ms,
                    error_code=ProviderErrorCode.TIMEOUT,
                    error_message=f"Ollama request timed out after {self.timeout}s.",
                )
            except httpx.NetworkError as exc:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                return ProviderTestResult(
                    provider=self.provider,
                    configured=True,
                    connected=False,
                    usable=False,
                    model=self.model,
                    latency_ms=elapsed_ms,
                    error_code=ProviderErrorCode.NETWORK_ERROR,
                    error_message=f"Network error communicating with Ollama: {exc}",
                )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        status = response.status_code
        if status != 200:
            err_code, retryable, msg = classify_http_error(status, response.text, self.provider)
            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=True,
                usable=False,
                model=self.model,
                http_status=status,
                latency_ms=elapsed_ms,
                error_code=err_code,
                error_message=msg,
                raw_provider_status=response.text[:500],
            )

        data = response.json()
        message = data.get("message") or {}
        content = message.get("content") or ""
        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 0)
        tokens_per_sec = (
            round((eval_count / (eval_duration_ns / 1e9)), 2)
            if eval_duration_ns > 0
            else None
        )

        return ProviderTestResult(
            provider=self.provider,
            configured=True,
            connected=True,
            usable=True,
            model=self.model,
            http_status=200,
            latency_ms=elapsed_ms,
            attempts=1,
            details={
                "sample_reply": content.strip()[:100],
                "tokens_per_sec": tokens_per_sec,
                "total_duration_ms": int(data.get("total_duration", 0) / 1e6),
                "load_duration_ms": int(data.get("load_duration", 0) / 1e6),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": eval_count,
            },
        )

    async def chat(
        self,
        system: str,
        user: str,
        images: Optional[List[str]] = None,
    ) -> ProviderChatResult:
        start_time = time.perf_counter()
        messages = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        user_message: Dict[str, Any] = {"role": "user", "content": user}
        if images:
            user_message["images"] = images
        messages.append(user_message)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.enable_thinking,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    code=ProviderErrorCode.TIMEOUT,
                    message=f"Ollama chat timed out after {self.timeout}s: {exc}",
                    retryable=True,
                ) from exc
            except httpx.NetworkError as exc:
                raise ProviderError(
                    code=ProviderErrorCode.NETWORK_ERROR,
                    message=f"Ollama network error: {exc}",
                    retryable=True,
                ) from exc

        if response.status_code != 200:
            err_code, retryable, msg = classify_http_error(
                response.status_code, response.text, self.provider
            )
            raise ProviderError(
                code=err_code,
                message=msg,
                http_status=response.status_code,
                retryable=retryable,
                raw_status=response.text[:500],
            )

        data = response.json()
        message = data.get("message") or {}
        text = message.get("content") or ""
        thinking = message.get("thinking") or ""
        if not text and thinking:
            text = thinking

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ProviderChatResult(
            provider=self.provider,
            model=self.model,
            text=text.strip(),
            latency_ms=elapsed_ms,
            usage={
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
            },
        )
