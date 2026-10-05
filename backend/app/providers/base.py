from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AIResult:
    provider: str
    model: str
    text: str


class AIProvider(ABC):
    name: str

    @abstractmethod
    async def chat(self, system: str, user: str) -> AIResult:
        raise NotImplementedError
