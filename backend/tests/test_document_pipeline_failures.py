import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from app.core.config import Settings
from app.services.fallback_extraction import (
    extract_with_fallback,
    parse_json,
    DocumentProcessingError,
)
from app.services import case_store
from app.services.pipeline import analyze_case


class TestDocumentPipelineFailures(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = Settings(
            gemini_api_key=None,
            sarvam_api_key=None,
            grok_api_key=None,
            ollama_base_url="http://localhost:11434",
            ollama_model="qwen3:8b",
        )
        self.dummy_pdf = Path(__file__).resolve().parent / "dummy_test.pdf"
        # Create a tiny 1-page dummy PDF using pymupdf
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Khatauni Village Sikandra Owner Ramesh Kumar Survey 124")
        doc.save(self.dummy_pdf)
        doc.close()

    def tearDown(self):
        if self.dummy_pdf.exists():
            self.dummy_pdf.unlink()

    def test_parse_json_valid_and_invalid(self):
        # Valid JSON
        valid = parse_json('{"document_type": "Khatauni", "owner_names": ["Ramesh Kumar"]}')
        self.assertEqual(valid["document_type"], "Khatauni")

        # Markdown fenced JSON
        fenced = parse_json('```json\n{"document_type": "Sale Deed"}\n```')
        self.assertEqual(fenced["document_type"], "Sale Deed")

        # Invalid non-JSON string
        with self.assertRaises(DocumentProcessingError) as ctx:
            parse_json("This is not a JSON object")
        self.assertEqual(ctx.exception.stage, "ai_extraction")
        self.assertEqual(ctx.exception.error_code, "INVALID_JSON_RESPONSE")

    @patch("app.services.fallback_extraction.extract_text")
    async def test_scanned_pdf_gemini_vision_fallback_success(self, mock_extract_text):
        mock_extract_text.return_value = ""  # Simulating scanned PDF (0 characters)

        settings = self.settings.model_copy(update={"gemini_api_key": "valid-gemini-key"})
        mock_result = MagicMock()
        mock_result.text = '{"document_type": "Khatauni", "owner_names": ["Ramesh Kumar"]}'
        mock_result.provider = "gemini"
        mock_result.model = "gemini-3.5-flash-lite"

        with patch("app.providers.gemini.GeminiProvider.extract_pdf", new_callable=AsyncMock) as mock_extract_pdf:
            mock_extract_pdf.return_value = mock_result
            extracted, provider = await extract_with_fallback(
                settings=settings,
                path=self.dummy_pdf,
                schema="{}",
                preferred="auto",
            )
            self.assertEqual(extracted["document_type"], "Khatauni")
            self.assertEqual(provider, "gemini")

    @patch("app.services.fallback_extraction.extract_text")
    @patch("app.services.fallback_extraction.render_pdf_to_images")
    async def test_scanned_pdf_ollama_vision_fallback_success(self, mock_render_images, mock_extract_text):
        mock_extract_text.return_value = ""  # Scanned PDF
        mock_render_images.return_value = ["base64pngimage"]

        mock_ai_result = MagicMock()
        mock_ai_result.text = '{"document_type": "Sale Deed", "survey_number": "124/3"}'
        mock_ai_result.provider = "ollama"
        mock_ai_result.model = "qwen3-vl:4b"

        with patch("app.providers.ollama.OllamaProvider.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_ai_result
            extracted, provider = await extract_with_fallback(
                settings=self.settings,
                path=self.dummy_pdf,
                schema="{}",
                preferred="auto",
            )
            self.assertEqual(extracted["document_type"], "Sale Deed")
            self.assertEqual(provider, "ollama")

    @patch("app.services.fallback_extraction.extract_text")
    @patch("app.services.fallback_extraction.render_pdf_to_images")
    async def test_scanned_pdf_no_ocr_available_raises_structured_error(self, mock_render_images, mock_extract_text):
        mock_extract_text.return_value = ""  # Scanned PDF
        mock_render_images.return_value = []  # No images rendered

        # Settings with no vision provider
        settings = Settings(
            gemini_api_key=None,
            sarvam_api_key=None,
            grok_api_key=None,
            ollama_base_url="",  # Ollama disabled
        )

        with self.assertRaises(DocumentProcessingError) as ctx:
            await extract_with_fallback(
                settings=settings,
                path=self.dummy_pdf,
                schema="{}",
                preferred="auto",
            )
        self.assertEqual(ctx.exception.stage, "ocr_fallback")
        self.assertEqual(ctx.exception.error_code, "NO_TEXT_EXTRACTION_AVAILABLE")

    async def test_analyze_case_mock_fixture_success(self):
        case = case_store.create_case("Test Case Processing")
        doc = case_store.add_document(
            case["id"],
            "FABRICATED_Mutation_Record_TEST_v2.pdf",
            "application/pdf",
            self.dummy_pdf.read_bytes(),
        )
        await analyze_case(case["id"], self.settings, reasoning_provider="mock")
        updated = case_store.get_case(case["id"])
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["stage"], "completed")
        self.assertIsNotNone(updated["analysis"])
        self.assertIn("score", updated["analysis"])

    async def test_analyze_case_pipeline_failure_tracks_stage(self):
        case = case_store.create_case("Test Case Failure")
        doc = case_store.add_document(
            case["id"],
            "Scanned_Empty_Doc.pdf",
            "application/pdf",
            self.dummy_pdf.read_bytes(),
        )

        # Force failure in extract_with_fallback
        with patch("app.services.pipeline.extract_with_fallback", side_effect=DocumentProcessingError(
            stage="ocr_fallback",
            error_code="NO_TEXT_EXTRACTION_AVAILABLE",
            message="No OCR fallback available",
        )):
            await analyze_case(case["id"], self.settings, reasoning_provider="auto")

        updated = case_store.get_case(case["id"])
        self.assertEqual(updated["status"], "failed")
        self.assertEqual(updated["stage"], "ocr_fallback")
        self.assertEqual(updated["analysis"]["error_code"], "NO_TEXT_EXTRACTION_AVAILABLE")

        # Document status should also be marked failed with stage
        updated_doc = updated["documents"][doc["id"]]
        self.assertEqual(updated_doc["status"], "failed")
        self.assertEqual(updated_doc["stage"], "ocr_fallback")


if __name__ == "__main__":
    unittest.main()
