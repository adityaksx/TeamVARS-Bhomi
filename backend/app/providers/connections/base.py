from abc import ABC, abstractmethod
from typing import Optional
from .models import ProviderTestResult, ProviderChatResult


class BaseProviderConnection(ABC):
    provider: str
    model: str

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the minimum required configuration/credentials are present."""
        raise NotImplementedError

    @abstractmethod
    async def test_connection(self) -> ProviderTestResult:
        """Perform a minimal, isolated connectivity and generation test."""
        raise NotImplementedError

    @abstractmethod
    async def chat(self, system: str, user: str) -> ProviderChatResult:
        """Perform a chat/generation request reusing the same connection pipeline."""
        raise NotImplementedError
