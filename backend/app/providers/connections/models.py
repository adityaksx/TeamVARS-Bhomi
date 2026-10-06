from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from .errors import ProviderErrorCode


class ProviderTestResult(BaseModel):
    provider: str
    configured: bool
    connected: bool
    usable: bool
    model: str
    http_status: Optional[int] = None
    latency_ms: int = 0
    attempts: int = 1
    retryable: bool = False
    error_code: Optional[ProviderErrorCode] = None
    error_message: Optional[str] = None
    raw_provider_status: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_summary(self) -> str:
        if self.usable:
            return f"PASS ({self.latency_ms} ms, model: {self.model})"
        err = self.error_code.value if self.error_code else "ERROR"
        return f"FAIL [{err}] {self.error_message or 'Unknown error'} (status: {self.http_status})"


class ProviderChatResult(BaseModel):
    provider: str
    model: str
    text: str
    latency_ms: int = 0
    usage: Optional[Dict[str, Any]] = None
    thinking_tokens: Optional[int] = None
