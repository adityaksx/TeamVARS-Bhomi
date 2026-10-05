import base64
import json

import httpx

from .base import AIProvider, AIResult


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

    async def chat(self, system: str, user: str) -> AIResult:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTIONS:\\n{system}\\n\\nUSER:\\n{user}"}]}],
            "generationConfig": {"temperature": 0.2},
        }
        return await self._generate(payload)

    async def extract_pdf(self, content: bytes, mime_type: str, prompt: str) -> AIResult:
        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(content).decode("ascii")}},
                ],
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        return await self._generate(payload)

    async def _generate(self, payload: dict) -> AIResult:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"Gemini request failed ({response.status_code}): {response.text[:2000]}")
            data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data!r}")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text:
            raise RuntimeError(f"Gemini returned an empty response: {data!r}")
        return AIResult(provider="gemini", model=self.model, text=text)
