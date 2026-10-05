import unittest

from app.core.config import Settings
from app.providers.factory import get_provider


class AIProviderTests(unittest.TestCase):
    def test_ollama_provider_requires_no_api_key(self):
        settings = Settings(ai_provider="ollama")
        provider = get_provider(settings)
        self.assertEqual(provider.name, "ollama")
        self.assertEqual(provider.model, settings.ollama_model)

    def test_gemini_provider_requires_key(self):
        settings = Settings(ai_provider="gemini", gemini_api_key="test-key")
        provider = get_provider(settings)
        self.assertEqual(provider.name, "gemini")

    def test_grok_provider_requires_key(self):
        settings = Settings(ai_provider="grok", grok_api_key="test-key")
        provider = get_provider(settings)
        self.assertEqual(provider.name, "grok")
        self.assertEqual(provider.model, "grok-4.7")

    def test_sarvam_provider_requires_key(self):
        settings = Settings(
            ai_provider="sarvam",
            sarvam_api_key="test-key",
        )
        provider = get_provider(settings)
        self.assertEqual(provider.name, "sarvam")


if __name__ == "__main__":
    unittest.main()
