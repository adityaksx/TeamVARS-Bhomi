import unittest
from app.providers.connections.models import ProviderTestResult, ProviderChatResult
from app.providers.connections.errors import ProviderErrorCode, classify_http_error


class TestProviderModels(unittest.TestCase):
    def test_provider_test_result_pass_summary(self):
        result = ProviderTestResult(
            provider="gemini",
            configured=True,
            connected=True,
            usable=True,
            model="gemini-3.5-flash-lite",
            latency_ms=450,
            http_status=200,
        )
        self.assertTrue(result.usable)
        self.assertIn("PASS", result.to_summary())
        self.assertIn("450 ms", result.to_summary())

    def test_provider_test_result_fail_summary(self):
        result = ProviderTestResult(
            provider="sarvam",
            configured=True,
            connected=False,
            usable=False,
            model="sarvam-105b",
            http_status=401,
            error_code=ProviderErrorCode.AUTHENTICATION_ERROR,
            error_message="Invalid key",
        )
        self.assertFalse(result.usable)
        self.assertIn("FAIL", result.to_summary())
        self.assertIn("AUTHENTICATION_ERROR", result.to_summary())

    def test_classify_http_errors(self):
        code, retryable, msg = classify_http_error(401, "unauthorized", "sarvam")
        self.assertEqual(code, ProviderErrorCode.AUTHENTICATION_ERROR)
        self.assertFalse(retryable)

        code, retryable, msg = classify_http_error(404, "model not found", "ollama")
        self.assertEqual(code, ProviderErrorCode.OLLAMA_MODEL_NOT_FOUND)
        self.assertFalse(retryable)

        code, retryable, msg = classify_http_error(404, "models/gemini-2.5-flash is not found", "gemini")
        self.assertEqual(code, ProviderErrorCode.MODEL_NOT_AVAILABLE)
        self.assertFalse(retryable)

        code, retryable, msg = classify_http_error(429, "rate limit exceeded", "gemini")
        self.assertEqual(code, ProviderErrorCode.RATE_LIMITED)
        self.assertTrue(retryable)

        code, retryable, msg = classify_http_error(503, "high demand spike", "gemini")
        self.assertEqual(code, ProviderErrorCode.PROVIDER_SERVER_ERROR)
        self.assertTrue(retryable)


if __name__ == "__main__":
    unittest.main()
