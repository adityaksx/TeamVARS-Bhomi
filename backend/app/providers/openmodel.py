import httpx

from .base import AIProvider, AIResult


class OpenModelProvider(AIProvider):
    name = "openmodel"

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def chat(self, system: str, user: str) -> AIResult:
        payload = {
            "model": self.model,
            "max_tokens": 900,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()

        return AIResult(provider=self.name, model=self.model, text=text)
