import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from app.providers.connections.sarvam import SarvamConnection
from app.providers.connections.errors import ProviderErrorCode


class TestSarvamConnection(unittest.IsolatedAsyncioTestCase):
    async def test_missing_key(self):
        conn = SarvamConnection(api_key=None)
        res = await conn.test_connection()
        self.assertFalse(res.configured)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.CONFIGURATION_ERROR)

    @patch("httpx.AsyncClient.post")
    async def test_auth_error_401(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"detail": "Invalid subscription key"}'
        mock_post.return_value = mock_resp

        conn = SarvamConnection(api_key="bad-key")
        res = await conn.test_connection()
        self.assertTrue(res.configured)
        self.assertFalse(res.connected)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.AUTHENTICATION_ERROR)

    @patch("httpx.AsyncClient.post")
    async def test_success_with_content(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            "usage": {"total_tokens": 10},
        })
        mock_post.return_value = mock_resp

        conn = SarvamConnection(api_key="valid-key")
        res = await conn.test_connection()
        self.assertTrue(res.usable)
        self.assertEqual(res.model, "sarvam-105b")
        self.assertEqual(res.details.get("sample_reply"), "OK")

    @patch("httpx.AsyncClient.post")
    async def test_success_with_reasoning_content(self, mock_post):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={
            "choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "Thinking done. OK"}}],
            "usage": {"total_tokens": 15},
        })
        mock_post.return_value = mock_resp

        conn = SarvamConnection(api_key="valid-key")
        res = await conn.test_connection()
        self.assertTrue(res.usable)
        self.assertIn("OK", res.details.get("sample_reply"))


if __name__ == "__main__":
    unittest.main()
