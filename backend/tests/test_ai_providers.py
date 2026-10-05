import unittest

from app.core.config import Settings
from app.providers.factory import get_provider


class AIProviderTests(unittest.TestCase):
    def test_ollama_provider_requires_no_api_key(self):
        settings = Settings(ai_provider="ollama")
        provider = get_provider(settings)
        self.assertEqual(provider.name, "ollama")
        self.assertEqual(provider.model, settings.ollama_model)

    def test_nvidia_provider_requires_key(self):
        settings = Settings(
            ai_provider="nvidia",
            nvidia_api_key="test-key",
            nvidia_model="openai/gpt-oss-20b",
        )
        provider = get_provider(settings)
        self.assertEqual(provider.name, "nvidia")
        self.assertEqual(provider.model, "openai/gpt-oss-20b")

    def test_sarvam_provider_requires_key(self):
        settings = Settings(
            ai_provider="sarvam",
            sarvam_api_key="test-key",
        )
        provider = get_provider(settings)
        self.assertEqual(provider.name, "sarvam")


if __name__ == "__main__":
    unittest.main()
