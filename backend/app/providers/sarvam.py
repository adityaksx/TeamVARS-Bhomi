from .base import AIProvider, AIResult
from .connections.sarvam import SarvamConnection


class SarvamProvider(AIProvider):
    name = "sarvam"

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.connection = SarvamConnection(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=90.0,
        )

    async def chat(self, system: str, user: str) -> AIResult:
        result = await self.connection.chat(system, user)
        return AIResult(
            provider=self.name,
            model=result.model,
            text=result.text,
        )
