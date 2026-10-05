from typing import Any


def build_demo_dashboard() -> dict[str, Any]:
    return {
        "documents": 4,
        "fields_extracted": 47,
        "entities_normalized": 29,
        "score": 82,
        "status": "Needs review",
        "property": {
            "village": "Sikandra",
            "taluk": "Agra Sadar",
            "district": "Agra",
            "survey": "124",
            "owner": "Ramesh Kumar",
        },
        "findings": [
            {
                "id": "F-001",
                "severity": "medium",
                "kind": "survey_mismatch",
                "title": "Gata identifier differs",
                "summary": "Khatauni records Gata 124, while the Sale Deed identifies Gata 124/3.",
                "confidence": 0.96,
                "verification_action": "Verify the Gata/subdivision number against the authoritative revenue/cadastral record and registered deed.",
                "evidence": [
                    {"document": "Khatauni", "page": 2, "field": "survey_number", "value": "124"},
                    {"document": "Sale Deed", "page": 4, "field": "survey_number", "value": "124/3"},
                ],
            },
            {
                "id": "F-002",
                "severity": "medium",
                "kind": "extent_mismatch",
                "title": "Recorded extent differs",
                "summary": "The Khatauni records 2.50 acres; the Sale Deed records 2.10 acres.",
                "confidence": 0.95,
                "verification_action": "Check whether the difference represents a subdivision, partial transfer or extraction error.",
                "evidence": [
                    {"document": "Khatauni", "page": 2, "field": "land_extent", "value": "2.50 acres"},
                    {"document": "Sale Deed", "page": 4, "field": "land_extent", "value": "2.10 acres"},
                ],
            },
        ],
        "coverage": [
            {"name": "Khatauni", "status": "present"},
            {"name": "Gata / Khasra", "status": "present"},
            {"name": "Mutation / Namantaran", "status": "present"},
            {"name": "Sale Deed", "status": "present"},
            {"name": "Encumbrance / Litigation", "status": "missing"},
        ],
        "timeline": [
            {"date": "2019", "label": "Khatauni record reviewed — Ramesh Kumar", "type": "khatauni"},
            {"date": "2025-08-14", "label": "Registered sale deed reviewed", "type": "sale"},
            {"date": "2025-09-02", "label": "Mutation / Namantaran entry", "type": "mutation"},
            {"date": "2026-10", "label": "Current reconciliation review", "type": "review"},
        ],
    }
