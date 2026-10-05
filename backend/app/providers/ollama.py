from .openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        super().__init__(
            name=self.name,
            api_key=None,
            base_url=base_url,
            model=model,
            timeout=180,
        )
