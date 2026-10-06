import unittest
from unittest.mock import patch

from app.api.routes import request_settings
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

    def test_request_settings_preserves_browser_ollama_values(self):
        base = Settings(
            ollama_base_url="http://server:11434/v1",
            ollama_model="base-model",
        )
        with patch("app.api.routes.settings", base):
            resolved = request_settings(
                ollama_base_url="http://localhost:11434/v1",
                ollama_model="qwen2.5:7b-instruct",
            )
        self.assertEqual(resolved.ollama_base_url, "http://localhost:11434/v1")
        self.assertEqual(resolved.ollama_model, "qwen2.5:7b-instruct")


if __name__ == "__main__":
    unittest.main()
