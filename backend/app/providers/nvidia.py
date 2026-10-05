from .openai_compatible import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):
    name = "nvidia"

    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__(
            name=self.name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=120,
        )
