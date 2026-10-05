import httpx

from .base import AIProvider, AIResult


class OpenAICompatibleProvider(AIProvider):
    """Provider for OpenAI-compatible chat APIs such as NVIDIA NIM and Ollama."""

    def __init__(
        self,
        name: str,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout: float = 90,
    ):
        self.name = name
        self.api_key = api_key or "not-needed"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(self, system: str, user: str) -> AIResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 1800,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                detail = response.text[:2000]
                raise RuntimeError(
                    f"{self.name} request failed ({response.status_code}): {detail}"
                )
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.name} returned no choices")

        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if not text:
            raise RuntimeError(f"{self.name} returned an empty response")

        return AIResult(provider=self.name, model=self.model, text=text)
