from pathlib import Path
from typing import Any

import fitz


def _token(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum() or character in "./-")


def _target_tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("raw") or value.get("acres") or ""
    if not isinstance(value, str):
        return []
    return [_token(item) for item in value.split() if _token(item)]


def _words_for_page(page: fitz.Page) -> list[tuple[float, float, float, float, str]]:
    words = []
    for item in page.get_text("words", sort=True):
        x0, y0, x1, y1, text = item[:5]
        cleaned = _token(text)
        if cleaned:
            words.append((x0, y0, x1, y1, cleaned))
    return words


def find_text_anchor(
    path: Path,
    value: Any,
    preferred_page: int | None = None,
) -> dict[str, Any] | None:
    tokens = _target_tokens(value)
    if not tokens:
        return None

    with fitz.open(path) as document:
        page_numbers = []
        if preferred_page and 1 <= preferred_page <= len(document):
            page_numbers.append(preferred_page)
        page_numbers.extend(
            page_number
            for page_number in range(1, len(document) + 1)
            if page_number not in page_numbers
        )

        for page_number in page_numbers:
            page = document[page_number - 1]
            words = _words_for_page(page)
            for index in range(0, len(words) - len(tokens) + 1):
                window = words[index:index + len(tokens)]
                if [item[4] for item in window] != tokens:
                    continue

                x0 = min(item[0] for item in window)
                y0 = min(item[1] for item in window)
                x1 = max(item[2] for item in window)
                y1 = max(item[3] for item in window)
                return {
                    "page": page_number,
                    "page_width": round(page.rect.width, 2),
                    "page_height": round(page.rect.height, 2),
                    "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    "text": " ".join(item[4] for item in window),
                    "method": "local-text-anchor",
                }
    return None


def build_source_anchors(
    path: Path,
    normalized: dict[str, Any],
    source_pages: dict[str, int] | None = None,
) -> dict[str, Any]:
    source_pages = source_pages or {}
    anchors: dict[str, Any] = {}

    scalar_fields = (
        "survey_number",
        "land_extent",
        "village",
        "taluk",
        "district",
        "document_date",
        "transaction_date",
        "document_type",
    )
    for field in scalar_fields:
        value = normalized.get(field)
        anchor = find_text_anchor(path, value, source_pages.get(field))
        if anchor:
            anchors[field] = anchor

    for owner in normalized.get("owner_names", []):
        anchor = find_text_anchor(path, owner, source_pages.get("owner_names"))
        if anchor:
            anchors[f"owner_names:{owner.casefold()}"] = anchor

    return anchors


def render_page(path: Path, page_number: int, dpi: int = 144) -> tuple[bytes, int, int]:
    with fitz.open(path) as document:
        if page_number < 1 or page_number > len(document):
            raise ValueError(f"Page {page_number} is outside the document.")
        page = document[page_number - 1]
        scale = dpi / 72
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pixmap.tobytes("png"), pixmap.width, pixmap.height


def page_count(path: Path) -> int:
    with fitz.open(path) as document:
        return len(document)
