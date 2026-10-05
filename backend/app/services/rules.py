from typing import Any

from app.domain.schemas import EntityResolution, Evidence, EvidenceAnchor, Finding
from app.services.entity_resolution import classify_name_match, similarity
from app.services.normalization import normalize_survey

EXPECTED_DOCUMENTS = [("RTC", "rtc"), ("Mutation", "mutation"), ("Sale Deed", "sale_deed"), ("Encumbrance Certificate", "encumbrance_certificate")]

def _evidence(document: dict[str, Any], field: str, value: Any) -> Evidence:
    page = int(document.get("source_pages", {}).get(field, 1))
    anchors = document.get("source_anchors", {}) or {}
    anchor_key = f"{field}:{value.casefold()}" if field == "owner_names" and isinstance(value, str) else field
    raw_anchor = anchors.get(anchor_key)
    anchor = EvidenceAnchor.model_validate(raw_anchor) if isinstance(raw_anchor, dict) else None
    if anchor:
        page = anchor.page
    return Evidence(
        document_id=document["id"],
        document=document.get("filename", document["id"]),
        page=page,
        field=field,
        value=value,
        anchor=anchor,
    )

def _finding_id(index: int) -> str:
    return f"F-{index:03d}"

def _owner_resolutions(owners: list[tuple[dict[str, Any], str]]) -> list[EntityResolution]:
    out = []
    for index, (left_doc, left_name) in enumerate(owners):
        for right_doc, right_name in owners[index + 1:]:
            state = classify_name_match(left_name, right_name)
            out.append(EntityResolution(
                left_document_id=left_doc["id"], right_document_id=right_doc["id"],
                left_value=left_name, right_value=right_name,
                similarity=round(similarity(left_name, right_name), 3),
                state={"same": "auto-match", "ambiguous": "ambiguous", "different": "conflict"}[state],
                rationale={
                    "same": "Names are sufficiently similar for automatic normalization.",
                    "ambiguous": "Names are similar but require manual verification.",
                    "different": "Names differ beyond the automatic matching threshold.",
                }[state],
            ))
    return out

def reconcile_documents(documents: list[dict[str, Any]]) -> list[Finding]:
    findings = []
    normalized_docs = [item for item in documents if item.get("normalized")]

    owners = []
    for document in normalized_docs:
        names = document["normalized"].get("owner_names", [])
        if names:
            owners.append((document, names[0]))

    if len(owners) >= 2:
        resolutions = _owner_resolutions(owners)
        states = {item.state for item in resolutions}
        evidence = [_evidence(doc, "owner_names", name) for doc, name in owners]
        if "conflict" in states:
            findings.append(Finding(
                id=_finding_id(len(findings) + 1), kind="owner_mismatch", severity="high",
                title="Recorded owner differs",
                summary="The uploaded records contain owner names that do not resolve to the same entity.",
                score_impact=25, confidence=0.98,
                verification_action="Verify the owner identity against the original deed and identity-linked record.",
                evidence=evidence, resolutions=resolutions,
            ))
        elif "ambiguous" in states:
            findings.append(Finding(
                id=_finding_id(len(findings) + 1), kind="entity_ambiguity", severity="medium",
                title="Owner identity needs verification",
                summary="Owner names are similar but not strong enough for automatic entity matching.",
                score_impact=10, confidence=0.72,
                verification_action="Compare initials, parent/spouse name, address and the original registered deed.",
                evidence=evidence, resolutions=resolutions,
            ))

    surveys = [(document, document["normalized"].get("survey_number")) for document in normalized_docs if document["normalized"].get("survey_number")]
    if len(surveys) >= 2 and len({normalize_survey(value) for _, value in surveys}) > 1:
        findings.append(Finding(
            id=_finding_id(len(findings) + 1), kind="survey_mismatch", severity="medium",
            title="Survey identifier differs",
            summary="At least two uploaded records identify the parcel differently.",
            score_impact=20, confidence=0.96,
            verification_action="Verify the survey/subdivision number against the latest RTC and registered deed.",
            evidence=[_evidence(doc, "survey_number", value) for doc, value in surveys],
        ))

    extents = [(document, document["normalized"].get("land_extent")) for document in normalized_docs if document["normalized"].get("land_extent")]
    if len(extents) >= 2 and len({round(float(item["acres"]), 6) for _, item in extents}) > 1:
        findings.append(Finding(
            id=_finding_id(len(findings) + 1), kind="extent_mismatch", severity="medium",
            title="Recorded extent differs",
            summary="The normalized land extent differs across the uploaded records.",
            score_impact=15, confidence=0.95,
            verification_action="Check whether the difference represents a subdivision, partial transfer or extraction error.",
            evidence=[_evidence(doc, "land_extent", item.get("raw") or item) for doc, item in extents],
        ))

    has_sale = any((d.get("normalized", {}).get("document_type") or "").casefold() in {"sale deed", "sale_deed"} or "sale" in d.get("filename", "").casefold() for d in normalized_docs)
    has_mutation = any("mutation" in (d.get("normalized", {}).get("document_type") or "").casefold() or "mutation" in d.get("filename", "").casefold() for d in normalized_docs)
    if has_sale and not has_mutation:
        findings.append(Finding(
            id=_finding_id(len(findings) + 1), kind="mutation_gap", severity="high",
            title="Mutation evidence not found",
            summary="A sale-related record is present, but no uploaded mutation record was identified.",
            score_impact=20, confidence=0.90,
            verification_action="Obtain the mutation extract or confirm mutation status from the authoritative land-record system.",
        ))
    return findings

def build_coverage(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    names = " ".join(f"{d.get('filename', '')} {d.get('normalized', {}).get('document_type', '')}".casefold() for d in documents)
    normalized_names = names.replace("-", "_").replace(" ", "_")
    return [{"name": label, "status": "present" if token in normalized_names or label.casefold() in names else "missing"} for label, token in EXPECTED_DOCUMENTS]
