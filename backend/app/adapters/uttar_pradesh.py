"""Uttar Pradesh land-record adapter.

Maps UP-specific document vocabulary to BhoomiLens' canonical land-record schema.
The adapter is deliberately thin: reconciliation rules remain state-agnostic.
"""

from typing import Any

UP_DOCUMENT_TYPES = {
    "khatauni": "Khatauni",
    "khatoni": "Khatauni",
    "gata": "Gata / Khasra",
    "khasra": "Gata / Khasra",
    "mutation": "Mutation / Namantaran",
    "namantaran": "Mutation / Namantaran",
    "sale deed": "Sale Deed",
    "sale_deed": "Sale Deed",
    "registry": "Sale Deed",
    "encumbrance": "Encumbrance / Litigation",
    "litigation": "Encumbrance / Litigation",
}


def classify_up_document(raw: dict[str, Any]) -> str:
    explicit = str(raw.get("document_type") or raw.get("type") or "").strip().casefold()
    if explicit:
        for token, canonical in UP_DOCUMENT_TYPES.items():
            if token in explicit:
                return canonical

    haystack = " ".join(
        str(raw.get(key) or "")
        for key in ("filename", "title", "text", "document_type", "type")
    ).casefold()
    for token, canonical in UP_DOCUMENT_TYPES.items():
        if token in haystack:
            return canonical

    return str(raw.get("document_type") or raw.get("type") or "Other")


def adapt_up_document(raw: dict[str, Any]) -> dict[str, Any]:
    mapped = dict(raw)
    mapped["document_type"] = classify_up_document(raw)

    if not mapped.get("survey_number"):
        mapped["survey_number"] = (
            mapped.get("gata_number")
            or mapped.get("khasra_number")
            or mapped.get("plot_number")
            or ""
        )

    if not mapped.get("tehsil"):
        mapped["tehsil"] = mapped.get("taluk") or ""

    if not mapped.get("taluk"):
        mapped["taluk"] = mapped.get("tehsil") or ""

    if not mapped.get("owner_names"):
        mapped["owner_names"] = mapped.get("khatedar_names") or mapped.get("khatedars") or []

    return mapped
