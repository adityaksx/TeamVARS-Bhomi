import base64
import time
from typing import Any, Dict, List, Optional
import httpx

from .base import BaseProviderConnection
from .models import ProviderTestResult, ProviderChatResult
from .errors import ProviderErrorCode, ProviderError, classify_http_error
from .retry import execute_with_retry
from app.core.logging import get_logger

logger = get_logger()


class GeminiConnection(BaseProviderConnection):
    provider = "gemini"

    # Compatible free-tier fallback models in priority order
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

    def _candidate_models(self) -> List[str]:
        """Return candidate models: primary first, followed by up to 2 fallbacks."""
        candidates = [self.model]
        for fb in self.FREE_TIER_FALLBACK_MODELS:
            if fb not in candidates and len(candidates) < 3:
                candidates.append(fb)
        return candidates

    def _is_fallback_candidate_error(self, exc: ProviderError) -> bool:
        """Determine if an error warrants attempting a fallback model."""
        if exc.code in {
            ProviderErrorCode.AUTHENTICATION_ERROR,
            ProviderErrorCode.AUTHORIZATION_ERROR,
            ProviderErrorCode.CONFIGURATION_ERROR,
            ProviderErrorCode.INVALID_REQUEST,
        } or exc.http_status in {400, 401, 403}:
            return False

        if exc.code in {
            ProviderErrorCode.MODEL_NOT_AVAILABLE,
            ProviderErrorCode.QUOTA_EXCEEDED,
            ProviderErrorCode.RATE_LIMITED,
            ProviderErrorCode.PROVIDER_SERVER_ERROR,
        } or exc.http_status in {404, 429, 503}:
            return True

        return False

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

        candidate_models = self._candidate_models()
        attempts_log = []
        last_exception: Optional[ProviderError] = None
        total_attempts = 0

        for idx, model_to_test in enumerate(candidate_models):
            is_fallback = idx > 0
            model_start = time.perf_counter()

            async def _attempt_call():
                return await self._post_generate(model_to_test, payload)

            try:
                (data, status), retry_attempts = await execute_with_retry(_attempt_call, max_attempts=2)
                total_attempts += retry_attempts
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                model_ms = int((time.perf_counter() - model_start) * 1000)

                candidates = data.get("candidates") or []
                if not candidates:
                    raise ProviderError(
                        code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                        message=f"Gemini returned no candidates for model {model_to_test}.",
                        http_status=status,
                    )

                parts = (candidates[0].get("content") or {}).get("parts") or []
                text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

                attempts_log.append({
                    "model": model_to_test,
                    "status": "PASS",
                    "http_status": status,
                    "latency_ms": model_ms,
                    "fallback": is_fallback,
                })

                if is_fallback:
                    logger.info(f"Gemini fallback succeeded using {model_to_test} ({model_ms}ms)")
                    self.model = model_to_test

                return ProviderTestResult(
                    provider=self.provider,
                    configured=True,
                    connected=True,
                    usable=True,
                    model=model_to_test,
                    http_status=status,
                    latency_ms=elapsed_ms,
                    attempts=total_attempts,
                    fallback_used=is_fallback,
                    details={
                        "sample_reply": text.strip()[:100],
                        "usage": data.get("usageMetadata", {}),
                        "attempts": attempts_log,
                    },
                )
            except ProviderError as exc:
                total_attempts += 1
                model_ms = int((time.perf_counter() - model_start) * 1000)
                attempts_log.append({
                    "model": model_to_test,
                    "status": "FAIL",
                    "error_code": exc.code.value,
                    "http_status": exc.http_status,
                    "latency_ms": model_ms,
                    "fallback": is_fallback,
                })
                last_exception = exc

                if self._is_fallback_candidate_error(exc) and idx + 1 < len(candidate_models):
                    logger.warning(
                        f"Gemini model {model_to_test} failed ({exc.code.value}); attempting fallback to {candidate_models[idx + 1]}"
                    )
                    continue
                else:
                    break

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ProviderTestResult(
            provider=self.provider,
            configured=True,
            connected=False,
            usable=False,
            model=candidate_models[0],
            http_status=last_exception.http_status if last_exception else None,
            latency_ms=elapsed_ms,
            attempts=total_attempts,
            retryable=last_exception.retryable if last_exception else False,
            fallback_used=len(candidate_models) > 1,
            error_code=last_exception.code if last_exception else ProviderErrorCode.UNKNOWN_PROVIDER_ERROR,
            error_message=last_exception.message if last_exception else "Gemini test failed",
            raw_provider_status=last_exception.raw_status if last_exception else None,
            details={"attempts": attempts_log},
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
        candidate_models = self._candidate_models()
        last_exc = None

        for idx, model_to_use in enumerate(candidate_models):
            is_fallback = idx > 0

            async def _call():
                return await self._post_generate(model_to_use, payload)

            try:
                (data, _), _ = await execute_with_retry(_call, max_attempts=2)
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)

                candidates = data.get("candidates") or []
                if not candidates:
                    raise ProviderError(
                        code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                        message=f"Gemini returned no candidates for model {model_to_use}.",
                    )

                parts = (candidates[0].get("content") or {}).get("parts") or []
                text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
                if not text:
                    raise ProviderError(
                        code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                        message=f"Gemini candidate content was empty for model {model_to_use}.",
                    )

                if is_fallback:
                    self.model = model_to_use

                return ProviderChatResult(
                    provider=self.provider,
                    model=model_to_use,
                    text=text.strip(),
                    latency_ms=elapsed_ms,
                    fallback_used=is_fallback,
                    usage=data.get("usageMetadata"),
                )
            except ProviderError as exc:
                last_exc = exc
                if self._is_fallback_candidate_error(exc) and idx + 1 < len(candidate_models):
                    logger.warning(f"Gemini chat failed on {model_to_use} ({exc.code.value}); falling back...")
                    continue
                raise

        if last_exc:
            raise last_exc
        raise ProviderError(code=ProviderErrorCode.UNKNOWN_PROVIDER_ERROR, message="Gemini chat failed.")

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
        candidate_models = self._candidate_models()
        last_exc = None

        for idx, model_to_use in enumerate(candidate_models):
            is_fallback = idx > 0

            async def _call():
                return await self._post_generate(model_to_use, payload)

            try:
                (data, _), _ = await execute_with_retry(_call, max_attempts=2)
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)

                candidates = data.get("candidates") or []
                if not candidates:
                    raise ProviderError(
                        code=ProviderErrorCode.RESPONSE_PARSE_ERROR,
                        message=f"Gemini returned no candidates for model {model_to_use}.",
                    )
                parts = (candidates[0].get("content") or {}).get("parts") or []
                text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

                if is_fallback:
                    self.model = model_to_use

                return ProviderChatResult(
                    provider=self.provider,
                    model=model_to_use,
                    text=text.strip(),
                    latency_ms=elapsed_ms,
                    fallback_used=is_fallback,
                    usage=data.get("usageMetadata"),
                )
            except ProviderError as exc:
                last_exc = exc
                if self._is_fallback_candidate_error(exc) and idx + 1 < len(candidate_models):
                    logger.warning(f"Gemini PDF extraction failed on {model_to_use} ({exc.code.value}); falling back...")
                    continue
                raise

        if last_exc:
            raise last_exc
        raise ProviderError(code=ProviderErrorCode.UNKNOWN_PROVIDER_ERROR, message="Gemini PDF extraction failed.")
