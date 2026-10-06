import unittest
from unittest.mock import patch, AsyncMock

from app.providers.connections.runner import ProviderRunner, test_provider_repeated
from app.providers.connections.models import ProviderTestResult
from app.providers.connections.errors import ProviderErrorCode
from app.core.config import Settings


class TestProviderRunner(unittest.IsolatedAsyncioTestCase):
    def test_create_connection(self):
        settings = Settings(
            sarvam_api_key="sarvam-key",
            gemini_api_key="gemini-key",
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:8b",
        )
        s_conn = ProviderRunner.create_connection("sarvam", settings)
        self.assertEqual(s_conn.provider, "sarvam")

        g_conn = ProviderRunner.create_connection("gemini", settings)
        self.assertEqual(g_conn.provider, "gemini")

        o_conn = ProviderRunner.create_connection("ollama", settings)
        self.assertEqual(o_conn.provider, "ollama")

    @patch("app.providers.connections.runner.test_provider_connection")
    async def test_repeated_stops_on_fatal_error(self, mock_test):
        # Return fatal auth error on run 1
        mock_test.return_value = ProviderTestResult(
            provider="sarvam",
            configured=True,
            connected=False,
            usable=False,
            model="sarvam-105b",
            retryable=False,
            error_code=ProviderErrorCode.AUTHENTICATION_ERROR,
            error_message="Invalid key",
        )

        summary = await test_provider_repeated("sarvam", repeat=5)
        # Should stop after run 1 instead of repeating 5 times
        self.assertEqual(summary["runs_attempted"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["success_rate"], 0.0)

    @patch("app.providers.connections.runner.test_provider_connection")
    async def test_repeated_aggregates_latencies(self, mock_test):
        mock_test.side_effect = [
            ProviderTestResult(provider="gemini", configured=True, connected=True, usable=True, model="gemini-3.5-flash-lite", latency_ms=100),
            ProviderTestResult(provider="gemini", configured=True, connected=True, usable=True, model="gemini-3.5-flash-lite", latency_ms=150),
            ProviderTestResult(provider="gemini", configured=True, connected=True, usable=True, model="gemini-3.5-flash-lite", latency_ms=200),
        ]

        summary = await test_provider_repeated("gemini", repeat=3)
        self.assertEqual(summary["runs_attempted"], 3)
        self.assertEqual(summary["passed"], 3)
        self.assertEqual(summary["median_latency_ms"], 150)
        self.assertEqual(summary["min_latency_ms"], 100)
        self.assertEqual(summary["max_latency_ms"], 200)


if __name__ == "__main__":
    unittest.main()
