from enum import Enum
import re
from typing import Tuple


class ProviderErrorCode(str, Enum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_SERVER_ERROR = "PROVIDER_SERVER_ERROR"
    RESPONSE_PARSE_ERROR = "RESPONSE_PARSE_ERROR"
    OLLAMA_UNAVAILABLE = "OLLAMA_UNAVAILABLE"
    OLLAMA_MODEL_NOT_FOUND = "OLLAMA_MODEL_NOT_FOUND"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


class ProviderError(Exception):
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        http_status: int | None = None,
        retryable: bool = False,
        raw_status: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.raw_status = raw_status


def classify_http_error(
    status_code: int,
    body: str,
    provider: str,
) -> Tuple[ProviderErrorCode, bool, str]:
    """Classify an HTTP error response into a normalized error code, retryability flag, and clean message.

    Never echoes API keys or authorization secrets.
    """
    clean_body = body.strip()
    lower_body = clean_body.lower()

    # Model not found / unavailable
    if status_code == 404:
        if provider == "ollama" or "model" in lower_body:
            if provider == "ollama":
                return ProviderErrorCode.OLLAMA_MODEL_NOT_FOUND, False, "Requested Ollama model is not installed."
            return ProviderErrorCode.MODEL_NOT_AVAILABLE, False, f"Model unavailable on {provider}: not accessible or not found."
        return ProviderErrorCode.INVALID_REQUEST, False, f"Endpoint not found on {provider} (404)."

    # Authentication / Authorization
    if status_code == 401:
        return ProviderErrorCode.AUTHENTICATION_ERROR, False, f"Invalid or expired API key for {provider}."
    if status_code == 403:
        if "quota" in lower_body or "resource_exhausted" in lower_body or "billing" in lower_body:
            return ProviderErrorCode.QUOTA_EXCEEDED, False, f"Quota or billing limit reached on {provider}."
        return ProviderErrorCode.AUTHORIZATION_ERROR, False, f"Permission denied for {provider} API key or project."

    # Rate limiting / Quota
    if status_code == 429:
        if "quota" in lower_body or "exhausted" in lower_body:
            return ProviderErrorCode.QUOTA_EXCEEDED, True, f"Free tier quota exceeded on {provider}."
        return ProviderErrorCode.RATE_LIMITED, True, f"Rate limited by {provider}. Please back off."

    # Invalid request / client errors
    if status_code == 400:
        if "model" in lower_body and ("not supported" in lower_body or "unknown" in lower_body or "not found" in lower_body):
            return ProviderErrorCode.MODEL_NOT_AVAILABLE, False, f"Model is not supported by {provider}."
        return ProviderErrorCode.INVALID_REQUEST, False, f"Bad request sent to {provider}."

    if status_code == 408:
        return ProviderErrorCode.TIMEOUT, True, f"Request to {provider} timed out (408)."

    # Server errors (5xx) - transient & retryable
    if 500 <= status_code < 600:
        if status_code == 503 and ("demand" in lower_body or "overloaded" in lower_body or "capacity" in lower_body):
            return ProviderErrorCode.PROVIDER_SERVER_ERROR, True, f"{provider} is experiencing high demand (503). Retrying may succeed."
        return ProviderErrorCode.PROVIDER_SERVER_ERROR, True, f"{provider} server error ({status_code})."

    return ProviderErrorCode.UNKNOWN_PROVIDER_ERROR, False, f"Unexpected HTTP status {status_code} from {provider}."
