from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["high", "medium", "low"]


class Evidence(BaseModel):
    document_id: str
    document: str
    page: int = 1
    field: str
    value: Any


class Finding(BaseModel):
    id: str
    kind: str
    severity: Severity
    title: str
    summary: str
    score_impact: int
    evidence: list[Evidence] = Field(default_factory=list)


class PropertySnapshot(BaseModel):
    village: str = "Not established"
    taluk: str = "Not established"
    district: str = "Not established"
    survey: str = "Not established"
    owner: str = "Not established"


class AnalysisDashboard(BaseModel):
    case_id: str
    documents: int
    fields_extracted: int
    entities_normalized: int
    score: int
    status: str
    property: PropertySnapshot
    findings: list[Finding] = Field(default_factory=list)
    coverage: list[dict[str, str]] = Field(default_factory=list)
    timeline: list[dict[str, str]] = Field(default_factory=list)
    extraction_status: str = "pending"
    reasoning_provider: str = "mock"


def field_value(document: dict[str, Any], field: str, default: Any = None) -> Any:
    value = document.get("normalized", {}).get(field)
    if value is None:
        value = document.get("extracted", {}).get(field)
    return value if value is not None else document.get(field, default)
