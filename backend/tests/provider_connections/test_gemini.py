import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from app.providers.connections.gemini import GeminiConnection
from app.providers.connections.errors import ProviderErrorCode


class TestGeminiConnection(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key(self):
        conn = GeminiConnection(api_key=None)
        res = await conn.test_connection()
        self.assertFalse(res.configured)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.CONFIGURATION_ERROR)

    @patch("httpx.AsyncClient.post")
    async def test_model_404_not_available(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.text = '{"error": {"code": 404, "message": "This model is no longer available to new users."}}'
        mock_post.return_value = mock_resp

        conn = GeminiConnection(api_key="valid-key", model="gemini-custom-404")
        res = await conn.test_connection()
        self.assertTrue(res.configured)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.MODEL_NOT_AVAILABLE)

    @patch("httpx.AsyncClient.post")
    async def test_quota_429(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"error": {"code": 429, "message": "Resource has been exhausted (quota)."}}'
        mock_post.return_value = mock_resp

        conn = GeminiConnection(api_key="valid-key")
        res = await conn.test_connection()
        self.assertTrue(res.configured)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.QUOTA_EXCEEDED)

    @patch("httpx.AsyncClient.post")
    async def test_success_200(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
            "usageMetadata": {"totalTokenCount": 6},
        })
        mock_post.return_value = mock_resp

        conn = GeminiConnection(api_key="valid-key", model="gemini-3.5-flash-lite")
        res = await conn.test_connection()
        self.assertTrue(res.usable)
        self.assertEqual(res.model, "gemini-3.5-flash-lite")
        self.assertEqual(res.details.get("sample_reply"), "OK")


if __name__ == "__main__":
    unittest.main()
