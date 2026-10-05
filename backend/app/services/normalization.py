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
    for prefix in ("survey no.", "survey no", "sy.no.", "sy.no", "gata no.", "gata no", "gatta no.", "khasra no.", "khasra no"):
        text = text.replace(prefix, "")
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

    survey_value = raw.get("survey_number") or raw.get("gata_number") or raw.get("khasra_number") or raw.get("plot_number")
    tehsil = normalize_text(raw.get("tehsil") or raw.get("taluk"))
    return {
        "document_type": display_text(raw.get("document_type") or raw.get("type")),
        "owner_names": [normalize_name(item) for item in owners if normalize_name(item)],
        "survey_number": normalize_survey(survey_value),
        "plot_number": normalize_survey(survey_value),
        "land_extent": parse_extent(raw.get("land_extent") or raw.get("extent")),
        "village": normalize_text(raw.get("village")),
        "tehsil": tehsil,
        "taluk": tehsil,
        "district": normalize_text(raw.get("district")),
        "document_date": display_text(raw.get("document_date") or raw.get("date")),
        "transaction_date": display_text(raw.get("transaction_date")),
        "previous_owner_names": [normalize_name(item) for item in (raw.get("previous_owner_names") or []) if normalize_name(item)],
        "new_owner_names": [normalize_name(item) for item in (raw.get("new_owner_names") or []) if normalize_name(item)],
        "mutation_number": display_text(raw.get("mutation_number")),
    }
