import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from app.providers.connections.ollama import OllamaConnection
from app.providers.connections.errors import ProviderErrorCode


class TestOllamaConnection(unittest.IsolatedAsyncioTestCase):
    @patch("httpx.AsyncClient.get")
    async def test_ollama_unavailable(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        conn = OllamaConnection(base_url="http://127.0.0.1:99999")
        res = await conn.test_connection()
        self.assertFalse(res.connected)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.OLLAMA_UNAVAILABLE)

    @patch("httpx.AsyncClient.get")
    async def test_model_not_found(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "models": [{"name": "qwen3:8b"}, {"name": "gemma3:4b"}]
        })
        mock_get.return_value = mock_resp

        conn = OllamaConnection(model="nonexistent-model")
        res = await conn.test_connection()
        self.assertTrue(res.connected)
        self.assertFalse(res.usable)
        self.assertEqual(res.error_code, ProviderErrorCode.OLLAMA_MODEL_NOT_FOUND)

    @patch("httpx.AsyncClient.post")
    @patch("httpx.AsyncClient.get")
    async def test_success_200(self, mock_get, mock_post):
        mock_tags = AsyncMock()
        mock_tags.status_code = 200
        mock_tags.raise_for_status = MagicMock()
        mock_tags.json = MagicMock(return_value={"models": [{"name": "qwen3:8b"}]})
        mock_get.return_value = mock_tags

        mock_chat = AsyncMock()
        mock_chat.status_code = 200
        mock_chat.json = MagicMock(return_value={
            "model": "qwen3:8b",
            "message": {"content": "OK"},
            "eval_count": 5,
            "eval_duration": 200_000_000,
        })
        mock_post.return_value = mock_chat

        conn = OllamaConnection(model="qwen3:8b")
        res = await conn.test_connection()
        self.assertTrue(res.connected)
        self.assertTrue(res.usable)
        self.assertEqual(res.details.get("tokens_per_sec"), 25.0)


if __name__ == "__main__":
    unittest.main()
