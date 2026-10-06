import time
from typing import Any, Dict, Optional
import httpx

from .base import BaseProviderConnection
from .models import ProviderTestResult, ProviderChatResult
from .errors import ProviderErrorCode, ProviderError, classify_http_error
from .retry import execute_with_retry


class SarvamConnection(BaseProviderConnection):
    provider = "sarvam"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.sarvam.ai",
        model: str = "sarvam-105b",
        timeout: float = 30.0,
    ):
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.rstrip("/")
        self.model = model or "sarvam-105b"
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["api-subscription-key"] = self.api_key
        return headers

    async def _post_chat(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
        if not self.is_configured:
            raise ProviderError(
                code=ProviderErrorCode.CONFIGURATION_ERROR,
                message="Sarvam API key is not configured.",
                retryable=False,
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    code=ProviderErrorCode.TIMEOUT,
                    message=f"Sarvam connection timed out ({self.timeout}s): {exc}",
                    retryable=True,
                ) from exc
            except httpx.NetworkError as exc:
                raise ProviderError(
                    code=ProviderErrorCode.NETWORK_ERROR,
                    message=f"Sarvam network error: {exc}",
                    retryable=True,
                ) from exc

        status = response.status_code
        if status >= 400:
            err_code, retryable, msg = classify_http_error(status, response.text, self.provider)
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
                message=f"Failed to parse Sarvam JSON response: {exc}",
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
                error_message="Sarvam API key is missing. Please configure SARVAM_API_KEY.",
            )

        start_time = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Reply exactly: OK"},
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
            "reasoning_effort": "low",
        }

        attempts = 0

        async def _call():
            nonlocal attempts
            attempts += 1
            return await self._post_chat(payload)

        try:
            (data, status), total_attempts = await execute_with_retry(_call, max_attempts=3)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            choices = data.get("choices") or []
            if not choices:
                return ProviderTestResult(
                    provider=self.provider,
                    configured=True,
                    connected=True,
                    usable=False,
                    model=self.model,
                    http_status=status,
                    latency_ms=elapsed_ms,
                    attempts=total_attempts,
                    error_code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                    error_message="Sarvam returned no choices in response.",
                )

            message = choices[0].get("message") or {}
            content = message.get("content") or message.get("reasoning_content") or ""
            usage = data.get("usage") or {}

            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=True,
                usable=True,
                model=self.model,
                http_status=status,
                latency_ms=elapsed_ms,
                attempts=total_attempts,
                details={
                    "sample_reply": content.strip()[:100],
                    "usage": usage,
                },
            )
        except ProviderError as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ProviderTestResult(
                provider=self.provider,
                configured=True,
                connected=False,
                usable=False,
                model=self.model,
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
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
            "reasoning_effort": "low",
        }

        start_time = time.perf_counter()

        async def _call():
            return await self._post_chat(payload)

        (data, _), attempts = await execute_with_retry(_call, max_attempts=3)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(
                code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                message="Sarvam returned no choices in response.",
            )

        message = choices[0].get("message") or {}
        text = message.get("content") or message.get("reasoning_content") or ""
        if not text:
            raise ProviderError(
                code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                message="Sarvam response choice was empty.",
            )

        usage = data.get("usage") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        thinking_tokens = completion_details.get("reasoning_tokens")

        return ProviderChatResult(
            provider=self.provider,
            model=self.model,
            text=text.strip(),
            latency_ms=elapsed_ms,
            usage=usage,
            thinking_tokens=thinking_tokens,
        )
