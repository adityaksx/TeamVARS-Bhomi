import json
from pathlib import Path
from typing import Any

import pymupdf

from app.core.config import Settings
from app.providers.factory import get_provider
from app.providers.gemini import GeminiProvider


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
            raise ValueError('AI extraction did not return JSON')
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError('AI extraction did not return an object')
    return value


async def extract_with_fallback(
    settings: Settings,
    path: Path,
    schema: str,
    preferred: str = 'auto',
) -> tuple[dict[str, Any], str]:
    # Gemini can inspect the original PDF, including scanned/image-only pages.
    if preferred == 'gemini' or (preferred in {'auto', 'fallback'} and settings.gemini_api_key):
        if settings.gemini_api_key:
            try:
                provider = GeminiProvider(settings.gemini_api_key, settings.gemini_base_url, settings.gemini_model)
                prompt = (
                    'Extract the Uttar Pradesh land record into ONLY a JSON object matching this schema. '
                    'Read both printed text and scanned/visual content. Preserve Hindi/English names and '
                    'Gata/Khasra identifiers exactly. Do not infer missing values.\\n\\n'
                    + schema
                )
                result = await provider.extract_pdf(path.read_bytes(), 'application/pdf', prompt)
                return parse_json(result.text), result.provider
            except Exception as exc:
                gemini_error = f'gemini: {exc}'
        else:
            gemini_error = 'gemini: GEMINI_API_KEY is not configured'
    else:
        gemini_error = ''

    text = extract_text(path)
    if not text.strip():
        if gemini_error:
            raise RuntimeError(f'AI extraction fallback failed: {gemini_error}; no machine-readable PDF text available for secondary fallback')
        raise RuntimeError('No machine-readable PDF text available for AI fallback extraction')

    if preferred in {'grok', 'ollama', 'local'}:
        candidates = [preferred]
    else:
        candidates = []
        if settings.grok_api_key:
            candidates.append('grok')
        candidates.append('ollama')
    prompt = (
        'Extract the Uttar Pradesh land record into ONLY a JSON object matching this schema. '
        'Preserve Hindi/English names and Gata/Khasra identifiers exactly. Do not infer missing values.\n\n'
        + schema + '\n\nDOCUMENT TEXT:\n' + text[:60000]
    )
    errors = [gemini_error] if gemini_error else []
    for name in candidates:
        try:
            provider = get_provider(settings, name)
            result = await provider.chat(
                system='You are a precise land-record document extraction engine. Return JSON only.',
                user=prompt,
            )
            return parse_json(result.text), result.provider
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    raise RuntimeError('AI extraction fallback failed: ' + ' | '.join(errors))