import base64
import json
from pathlib import Path
from typing import Any, Optional

import pymupdf

from app.core.config import Settings
from app.core.logging import get_logger, current_stage, current_document_id
from app.providers.factory import get_provider
from app.providers.gemini import GeminiProvider
from app.providers.ollama import OllamaProvider

logger = get_logger()


class DocumentProcessingError(Exception):
    def __init__(self, stage: str, error_code: str, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(f"[{stage}] {error_code}: {message}")
        self.stage = stage
        self.error_code = error_code
        self.message = message
        self.details = details or {}


def extract_text(path: Path) -> str:
    if path.suffix.casefold() != '.pdf':
        return ''
    doc = pymupdf.open(path)
    try:
        pages = []
        for index, page in enumerate(doc):
            text = page.get_text('text')
            if text.strip():
                pages.append(f'PAGE {index + 1}\n{text}')
        return '\n\n'.join(pages)
    finally:
        doc.close()


def render_pdf_to_images(path: Path, max_pages: int = 3, dpi: int = 150) -> list[str]:
    """Render PDF pages to base64 PNG strings for vision OCR extraction."""
    if path.suffix.casefold() != '.pdf':
        return []
    doc = pymupdf.open(path)
    images: list[str] = []
    try:
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            pix = page.get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")
            images.append(base64.b64encode(png_bytes).decode("ascii"))
        return images
    finally:
        doc.close()


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith('```'):
        parts = text.split('\n', 1)
        text = parts[1] if len(parts) == 2 else text
        if text.endswith('```'):
            text = text[:-3].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            raise DocumentProcessingError(
                stage="ai_extraction",
                error_code="INVALID_JSON_RESPONSE",
                message="AI extraction did not return JSON: " + text[:200],
            )
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as err:
            raise DocumentProcessingError(
                stage="ai_extraction",
                error_code="INVALID_JSON_RESPONSE",
                message=f"AI extraction returned malformed JSON: {err}",
            ) from err
    if not isinstance(value, dict):
        raise DocumentProcessingError(
            stage="ai_extraction",
            error_code="INVALID_JSON_RESPONSE",
            message="AI extraction did not return a JSON object",
        )
    return value


async def extract_with_fallback(
    settings: Settings,
    path: Path,
    schema: str,
    preferred: str = 'auto',
    document_id: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    if document_id:
        current_document_id.set(document_id)

    current_stage.set("detecting_document")
    logger.info(f"Detecting document structure for {path.name}...")

    current_stage.set("extracting_text")
    text = extract_text(path)

    # Scanned or image-only PDF branch
    if not text.strip():
        current_stage.set("ocr_fallback")
        logger.info(f"No machine-readable text found in {path.name} (0 characters). Entering OCR / vision fallback stage.")

        ocr_errors: list[str] = []

        # 1. Gemini multimodal PDF extraction
        if settings.gemini_api_key and preferred in {'auto', 'fallback', 'gemini'}:
            try:
                logger.info(f"Attempting Gemini multimodal PDF extraction for {path.name}...")
                provider = GeminiProvider(settings.gemini_api_key, settings.gemini_base_url, settings.gemini_model)
                prompt = (
                    'Extract the Uttar Pradesh land record into ONLY a JSON object matching this schema. '
                    'Read both printed text and scanned/visual content. Preserve Hindi/English names and '
                    'Gata/Khasra identifiers exactly. Do not infer missing values.\n\n'
                    + schema
                )
                result = await provider.extract_pdf(path.read_bytes(), 'application/pdf', prompt)
                current_stage.set("ai_extraction")
                parsed = parse_json(result.text)
                logger.info(f"Scanned document {path.name} extracted via Gemini PDF vision ({result.model})")
                return parsed, result.provider
            except Exception as exc:
                logger.warning(f"Gemini PDF vision extraction failed: {exc}")
                ocr_errors.append(f"gemini_vision: {exc}")

        # 2. Ollama vision extraction
        if settings.ollama_base_url and preferred in {'auto', 'fallback', 'ollama', 'local'}:
            try:
                images = render_pdf_to_images(path, max_pages=3)
                if images:
                    vision_model = settings.ollama_model if any(v in settings.ollama_model.lower() for v in ['vl', 'vision', 'gemma3']) else 'qwen3-vl:4b'
                    logger.info(f"Attempting Ollama vision extraction with model '{vision_model}' for {path.name} ({len(images)} pages)...")
                    ollama_provider = OllamaProvider(
                        base_url=settings.ollama_base_url,
                        model=vision_model,
                        timeout=getattr(settings, "ollama_timeout", 120.0),
                    )
                    vision_prompt = (
                        'Extract the Uttar Pradesh land record in these scanned document images into ONLY a JSON object matching this schema. '
                        'Preserve Hindi/English names and Gata/Khasra identifiers exactly. Do not infer missing values.\n\n'
                        + schema
                    )
                    result = await ollama_provider.chat(
                        system="You are a precise land-record document extraction engine. Return JSON only.",
                        user=vision_prompt,
                        images=images,
                    )
                    current_stage.set("ai_extraction")
                    parsed = parse_json(result.text)
                    logger.info(f"Scanned document {path.name} extracted via Ollama vision ({result.model})")
                    return parsed, result.provider
            except Exception as exc:
                logger.warning(f"Ollama vision extraction failed: {exc}")
                ocr_errors.append(f"ollama_vision: {exc}")

        err_detail = " | ".join(ocr_errors) if ocr_errors else "No vision/OCR fallback provider configured"
        logger.error(f"Document processing failed for {path.name}: {err_detail}")
        raise DocumentProcessingError(
            stage="ocr_fallback",
            error_code="NO_TEXT_EXTRACTION_AVAILABLE",
            message=f"No machine-readable PDF text available and vision/OCR fallback failed: {err_detail}",
            details={"errors": ocr_errors},
        )

    # Machine-readable PDF text branch
    logger.info(f"Extracted {len(text)} characters of native machine-readable text from {path.name}. Entering ai_extraction stage.")
    current_stage.set("ai_extraction")

    if preferred in {'grok', 'ollama', 'local'}:
        candidates = [preferred]
    elif preferred == 'gemini':
        candidates = ['gemini']
    else:
        candidates = []
        if settings.gemini_api_key:
            candidates.append('gemini')
        if settings.grok_api_key:
            candidates.append('grok')
        candidates.append('ollama')

    prompt = (
        'Extract the Uttar Pradesh land record into ONLY a JSON object matching this schema. '
        'Preserve Hindi/English names and Gata/Khasra identifiers exactly. Do not infer missing values.\n\n'
        + schema + '\n\nDOCUMENT TEXT:\n' + text[:60000]
    )

    errors = []
    for name in candidates:
        try:
            logger.info(f"Attempting AI extraction for {path.name} using provider '{name}'...")
            provider = get_provider(settings, name)
            result = await provider.chat(
                system='You are a precise land-record document extraction engine. Return JSON only.',
                user=prompt,
            )
            parsed = parse_json(result.text)
            logger.info(f"Successfully extracted document {path.name} using provider '{name}' ({result.model})")
            return parsed, result.provider
        except Exception as exc:
            logger.warning(f"Provider '{name}' extraction failed for {path.name}: {exc}")
            errors.append(f'{name}: {exc}')

    err_msg = 'AI extraction fallback failed: ' + ' | '.join(errors)
    logger.error(f"{path.name} extraction failed: {err_msg}")
    raise DocumentProcessingError(
        stage="ai_extraction",
        error_code="AI_EXTRACTION_FAILED",
        message=err_msg,
        details={"errors": errors},
    )