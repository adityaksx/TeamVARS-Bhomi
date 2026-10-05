import json
from pathlib import Path
from typing import Any

import pymupdf

from app.core.config import Settings
from app.providers.factory import get_provider


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
    text = extract_text(path)
    if not text.strip():
        raise RuntimeError('No machine-readable PDF text available for AI fallback extraction')
    if preferred in {'nvidia', 'ollama', 'local'}:
        candidates = [preferred]
    else:
        candidates = []
        if settings.nvidia_api_key:
            candidates.append('nvidia')
        candidates.append('ollama')
    prompt = (
        'Extract the Uttar Pradesh land record into ONLY a JSON object matching this schema. '
        'Preserve Hindi/English names and Gata/Khasra identifiers exactly. Do not infer missing values.\n\n'
        + schema + '\n\nDOCUMENT TEXT:\n' + text[:60000]
    )
    errors = []
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