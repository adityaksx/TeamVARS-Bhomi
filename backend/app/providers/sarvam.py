import httpx

from .base import AIProvider, AIResult


class SarvamProvider(AIProvider):
    name = "sarvam"

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

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
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Sarvam chat request failed ({response.status_code}): {response.text[:2000]}"
                )
            data = response.json()

        return AIResult(
            provider=self.name,
            model=self.model,
            text=data["choices"][0]["message"]["content"],
        )
