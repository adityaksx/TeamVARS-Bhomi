from typing import Any


def build_demo_dashboard() -> dict[str, Any]:
    return {
        "documents": 4,
        "fields_extracted": 47,
        "entities_normalized": 31,
        "score": 82,
        "status": "Needs review",
        "property": {
            "village": "Example Village",
            "taluk": "Example Taluk",
            "district": "Example District",
            "survey": "128/3A",
            "owner": "Ramesh Kumar",
        },
        "findings": [
            {
                "id": "F-001",
                "severity": "medium",
                "kind": "survey_mismatch",
                "title": "Survey identifier differs",
                "summary": "RTC and mutation use 128/3A, while the Sale Deed uses 128/3.",
                "evidence": [
                    {"document": "RTC", "page": 2, "field": "survey_number", "value": "128/3A"},
                    {"document": "Sale Deed", "page": 4, "field": "survey_number", "value": "128/3"},
                ],
            },
            {
                "id": "F-002",
                "severity": "medium",
                "kind": "extent_mismatch",
                "title": "Recorded extent differs",
                "summary": "The RTC records 2.10 acres; the Sale Deed records 1.84 acres.",
                "evidence": [
                    {"document": "RTC", "page": 2, "field": "extent", "value": "2.10 acres"},
                    {"document": "Sale Deed", "page": 4, "field": "extent", "value": "1.84 acres"},
                ],
            },
        ],
        "coverage": [
            {"name": "RTC", "status": "present"},
            {"name": "Mutation", "status": "present"},
            {"name": "Sale Deed", "status": "present"},
            {"name": "Encumbrance Certificate", "status": "missing"},
        ],
        "timeline": [
            {"date": "2012", "label": "Owner A recorded", "type": "record"},
            {"date": "2017", "label": "Sale transaction → Ramesh Kumar", "type": "sale"},
            {"date": "2021", "label": "Mutation recorded", "type": "mutation"},
            {"date": "2024", "label": "Sale deed reviewed", "type": "sale"},
        ],
    }
