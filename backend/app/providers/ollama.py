from .base import AIProvider, AIResult
from .connections.ollama import OllamaConnection


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 120):
        self.base_url = base_url
        self.model = model
        self.connection = OllamaConnection(
            base_url=base_url,
            model=model,
            timeout=timeout,
            enable_thinking=False,
        )

    async def chat(self, system: str, user: str) -> AIResult:
        result = await self.connection.chat(system, user)
        return AIResult(provider=self.name, model=result.model, text=result.text)
