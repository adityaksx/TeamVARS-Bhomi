from .base import AIProvider, AIResult
from .connections.gemini import GeminiConnection


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.connection = GeminiConnection(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    async def chat(self, system: str, user: str) -> AIResult:
        result = await self.connection.chat(system, user)
        return AIResult(provider=self.name, model=result.model, text=result.text)

    async def extract_pdf(self, content: bytes, mime_type: str, prompt: str) -> AIResult:
        result = await self.connection.extract_pdf(content, mime_type, prompt)
        return AIResult(provider=self.name, model=result.model, text=result.text)
