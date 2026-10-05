from .base import AIProvider, AIResult


class MockProvider(AIProvider):
    name = "mock"

    async def chat(self, system: str, user: str) -> AIResult:
        return AIResult(
            provider=self.name,
            model="local-demo",
            text=(
                "The uploaded records show a survey identifier mismatch. "
                "The RTC lists 128/3A while the Sale Deed lists 128/3. "
                "This is a document inconsistency that should be verified against the authoritative survey record."
            ),
        )
