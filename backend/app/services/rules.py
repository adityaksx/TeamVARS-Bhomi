from typing import Any

from app.domain.schemas import Evidence, Finding
from app.services.normalization import normalize_name, normalize_survey


EXPECTED_DOCUMENTS = [
    ("RTC", "rtc"),
    ("Mutation", "mutation"),
    ("Sale Deed", "sale_deed"),
    ("Encumbrance Certificate", "encumbrance_certificate"),
]


def _evidence(document: dict[str, Any], field: str, value: Any) -> Evidence:
    return Evidence(
        document_id=document["id"],
        document=document.get("filename", document["id"]),
        page=int(document.get("page", 1)),
        field=field,
        value=value,
    )


def _finding_id(index: int) -> str:
    return f"F-{index:03d}"


def reconcile_documents(documents: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    normalized_docs = [item for item in documents if item.get("normalized")]

    # Owner comparison
    owners: list[tuple[dict[str, Any], str]] = []
    for document in normalized_docs:
        names = document["normalized"].get("owner_names", [])
        if names:
            owners.append((document, names[0]))

    if len(owners) >= 2:
        canonical = {normalize_name(name) for _, name in owners}
        if len(canonical) > 1:
            evidence = [_evidence(doc, "owner_names", name) for doc, name in owners]
            findings.append(
                Finding(
                    id=_finding_id(len(findings) + 1),
                    kind="owner_mismatch",
                    severity="high",
                    title="Recorded owner differs",
                    summary="The uploaded records contain different normalized owner names.",
                    score_impact=25,
                    evidence=evidence,
                )
            )

    # Survey comparison
    surveys: list[tuple[dict[str, Any], str]] = []
    for document in normalized_docs:
        survey = document["normalized"].get("survey_number")
        if survey:
            surveys.append((document, survey))

    if len(surveys) >= 2:
        canonical = {normalize_survey(survey) for _, survey in surveys}
        if len(canonical) > 1:
            evidence = [_evidence(doc, "survey_number", survey) for doc, survey in surveys]
            findings.append(
                Finding(
                    id=_finding_id(len(findings) + 1),
                    kind="survey_mismatch",
                    severity="medium",
                    title="Survey identifier differs",
                    summary="At least two uploaded records identify the parcel differently.",
                    score_impact=20,
                    evidence=evidence,
                )
            )

    # Extent comparison
    extents: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for document in normalized_docs:
        extent = document["normalized"].get("land_extent")
        if extent:
            extents.append((document, extent))

    if len(extents) >= 2:
        values = {round(float(item["acres"]), 6) for _, item in extents}
        if len(values) > 1:
            evidence = [_evidence(doc, "land_extent", extent.get("raw") or extent) for doc, extent in extents]
            findings.append(
                Finding(
                    id=_finding_id(len(findings) + 1),
                    kind="extent_mismatch",
                    severity="medium",
                    title="Recorded extent differs",
                    summary="The normalized land extent differs across the uploaded records.",
                    score_impact=15,
                    evidence=evidence,
                )
            )

    # Mutation relationship check
    has_sale = any(
        (document.get("normalized", {}).get("document_type") or "").casefold() in {"sale deed", "sale_deed"}
        or "sale" in document.get("filename", "").casefold()
        for document in normalized_docs
    )
    has_mutation = any(
        "mutation" in (document.get("normalized", {}).get("document_type") or "").casefold()
        or "mutation" in document.get("filename", "").casefold()
        for document in normalized_docs
    )
    if has_sale and not has_mutation:
        findings.append(
            Finding(
                id=_finding_id(len(findings) + 1),
                kind="mutation_gap",
                severity="high",
                title="Mutation evidence not found",
                summary="A sale-related record is present, but no uploaded mutation record was identified.",
                score_impact=20,
                evidence=[],
            )
        )

    return findings


def build_coverage(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    names = " ".join(
        f"{document.get('filename', '')} {document.get('normalized', {}).get('document_type', '')}".casefold()
        for document in documents
    )
    coverage = []
    for label, token in EXPECTED_DOCUMENTS:
        coverage.append(
            {
                "name": label,
                "status": "present" if token in names.replace("-", "_").replace(" ", "_") or label.casefold() in names else "missing",
            }
        )
    return coverage
