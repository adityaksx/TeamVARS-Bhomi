import re
from typing import Any


HONORIFICS = re.compile(r"\b(shri|smt|mr|mrs|ms|dr)\.?\b", re.I)
SPACE_RE = re.compile(r"\s+")
UNIT_TO_ACRES = {
    "acre": 1.0,
    "acres": 1.0,
    "cent": 0.01,
    "cents": 0.01,
    "sqft": 1 / 43560,
    "sq ft": 1 / 43560,
    "square feet": 1 / 43560,
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = HONORIFICS.sub(" ", text)
    text = text.replace(",", " ")
    text = SPACE_RE.sub(" ", text)
    return text.strip().casefold()


def display_text(value: Any) -> str:
    if value is None:
        return ""
    return SPACE_RE.sub(" ", str(value).strip())


def normalize_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"\b(s/o|d/o|w/o|c/o)\b.*$", "", text)
    return SPACE_RE.sub(" ", text).strip()


def normalize_survey(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold()
    text = text.replace("survey no.", "").replace("survey no", "")
    text = text.replace("sy.no.", "").replace("sy.no", "")
    text = re.sub(r"\s+", "", text)
    return text.replace("-", "/")


def parse_extent(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    text = str(value).strip().casefold()
    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*(acres?|cent|cents|sq\.?\s*ft|square feet|sqft)\b",
        text,
    )
    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2).replace(".", "")
    factor = UNIT_TO_ACRES.get(unit)
    if factor is None:
        return None

    return {
        "value": number,
        "unit": unit,
        "acres": number * factor,
        "raw": str(value),
    }


def normalize_document(raw: dict[str, Any]) -> dict[str, Any]:
    owners = raw.get("owner_names") or raw.get("owners") or []
    if isinstance(owners, str):
        owners = [owners]

    return {
        "document_type": display_text(raw.get("document_type") or raw.get("type")),
        "owner_names": [normalize_name(item) for item in owners if normalize_name(item)],
        "survey_number": normalize_survey(raw.get("survey_number")),
        "land_extent": parse_extent(raw.get("land_extent") or raw.get("extent")),
        "village": normalize_text(raw.get("village")),
        "taluk": normalize_text(raw.get("taluk")),
        "district": normalize_text(raw.get("district")),
        "document_date": display_text(raw.get("document_date") or raw.get("date")),
        "transaction_date": display_text(raw.get("transaction_date")),
    }
