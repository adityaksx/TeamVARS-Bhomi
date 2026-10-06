import base64
import time
from typing import Any, Dict, Optional
import httpx

from .base import BaseProviderConnection
from .models import ProviderTestResult, ProviderChatResult
from .errors import ProviderErrorCode, ProviderError, classify_http_error
from .retry import execute_with_retry


class GeminiConnection(BaseProviderConnection):
    provider = "gemini"

    # Recommended fallback models on free tier if primary model encounters quota/access issues
    FREE_TIER_FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "gemini-3.5-flash-lite",
        timeout: float = 30.0,
    ):
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.rstrip("/")
        # Migrate deprecated models if specified
        if model in {"gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"}:
            self.model = "gemini-3.5-flash-lite"
        else:
            self.model = model or "gemini-3.5-flash-lite"
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _post_generate(self, model: str, payload: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        if not self.is_configured:
            raise ProviderError(
                code=ProviderErrorCode.CONFIGURATION_ERROR,
                message="Gemini API key is not configured.",
                retryable=False,
            )

        url = f"{self.base_url}/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    code=ProviderErrorCode.TIMEOUT,
                    message=f"Gemini connection timed out ({self.timeout}s): {exc}",
                    retryable=True,
                ) from exc
            except httpx.NetworkError as exc:
                raise ProviderError(
                    code=ProviderErrorCode.NETWORK_ERROR,
                    message=f"Gemini network error: {exc}",
                    retryable=True,
                ) from exc

        status = response.status_code
        if status >= 400:
            err_code, retryable, msg = classify_http_error(status, response.text, self.provider)
            if status == 404 and "not available to new users" in response.text:
                msg = f"Model '{model}' is restricted for new projects/free tier. Use gemini-3.5-flash-lite."
            raise ProviderError(
                code=err_code,
                message=msg,
                http_status=status,
                retryable=retryable,
                raw_status=response.text[:500],
            )

        try:
            data = response.json()
        except Exception as exc:
            raise ProviderError(
                code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                message=f"Failed to parse Gemini JSON response: {exc}",
                http_status=status,
                retryable=False,
            ) from exc

        return data, status

    async def test_connection(self) -> ProviderTestResult:
        if not self.is_configured:
            return ProviderTestResult(
                provider=self.provider,
                configured=False,
                connected=False,
                usable=False,
                model=self.model,
                error_code=ProviderErrorCode.CONFIGURATION_ERROR,
                error_message="Gemini API key is missing. Please configure GEMINI_API_KEY.",
            )

        start_time = time.perf_counter()
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": "Reply exactly: OK"}]}
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 20},
        }

        attempts = 0
        target_model = self.model

        async def _attempt_call():
            nonlocal attempts
            attempts += 1
            return await self._post_generate(target_model, payload)

        try:
            # Try with bounded retry in case of transient 503 high-demand spike
            (data, status), total_attempts = await execute_with_retry(_attempt_call, max_attempts=2)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            candidates = data.get("candidates") or []
            if not candidates:
                return ProviderTestResult(
                    provider=self.provider,
                    configured=True,
                    connected=True,
                    usable=False,
                    model=target_model,
                    http_status=status,
                    latency_ms=elapsed_ms,
                    attempts=total_attempts,
                    error_code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                    error_message="Gemini returned no candidates in response.",
                )

            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=True,
                usable=True,
                model=target_model,
                http_status=status,
                latency_ms=elapsed_ms,
                attempts=total_attempts,
                details={
                    "sample_reply": text.strip()[:100],
                    "usage": data.get("usageMetadata", {}),
                },
            )
        except ProviderError as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=False,
                usable=False,
                model=target_model,
                http_status=exc.http_status,
                latency_ms=elapsed_ms,
                attempts=max(1, attempts),
                retryable=exc.retryable,
                error_code=exc.code,
                error_message=exc.message,
                raw_provider_status=exc.raw_status,
            )

    async def chat(self, system: str, user: str) -> ProviderChatResult:
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"SYSTEM INSTRUCTIONS:\n{system}\n\nUSER:\n{user}"}],
                }
            ],
            "generationConfig": {"temperature": 0.2},
        }

        start_time = time.perf_counter()

        async def _call():
            return await self._post_generate(self.model, payload)

        (data, _), _ = await execute_with_retry(_call, max_attempts=3)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError(
                code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                message="Gemini returned no candidates in response.",
            )

        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text:
            raise ProviderError(
                code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                message="Gemini candidate content was empty.",
            )

        return ProviderChatResult(
            provider=self.provider,
            model=self.model,
            text=text.strip(),
            latency_ms=elapsed_ms,
            usage=data.get("usageMetadata"),
        )

    async def extract_pdf(self, content: bytes, mime_type: str, prompt: str) -> ProviderChatResult:
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64.b64encode(content).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        start_time = time.perf_counter()

        async def _call():
            return await self._post_generate(self.model, payload)

        (data, _), _ = await execute_with_retry(_call, max_attempts=3)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError(
                code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                message="Gemini returned no candidates.",
            )
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        return ProviderChatResult(
            provider=self.provider,
            model=self.model,
            text=text.strip(),
            latency_ms=elapsed_ms,
            usage=data.get("usageMetadata"),
        )
