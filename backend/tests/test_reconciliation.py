import unittest

from app.services.entity_resolution import classify_name_match
from app.services.normalization import normalize_document
from app.services.rules import reconcile_documents


def doc(doc_id: str, name: str, **raw):
    extracted = {
        "document_type": raw.pop("document_type", "RTC"),
        "owner_names": raw.pop("owner_names", ["Ramesh Kumar"]),
        "survey_number": raw.pop("survey_number", "128/3A"),
        "land_extent": raw.pop("land_extent", "2.10 acres"),
        "village": "Example Village",
        "taluk": "Example Taluk",
        "district": "Example District",
        **raw,
    }
    normalized = normalize_document(extracted)
    return {
        "id": doc_id,
        "filename": name,
        "extracted": extracted,
        "normalized": normalized,
        "source_pages": {"owner_names": 2, "survey_number": 2, "land_extent": 3},
    }


class ReconciliationTests(unittest.TestCase):
    def test_same_owner_and_survey_is_clean(self):
        findings = reconcile_documents([
            doc("1", "rtc.pdf"),
            doc("2", "mutation.pdf", document_type="Mutation Extract"),
        ])
        kinds = {item.kind for item in findings}
        self.assertNotIn("owner_mismatch", kinds)
        self.assertNotIn("survey_mismatch", kinds)

    def test_kumar_is_preserved_as_part_of_name(self):
        normalized = normalize_document({"owner_names": ["Shri Ramesh Kumar"]})
        self.assertEqual(normalized["owner_names"], ["ramesh kumar"])

    def test_survey_mismatch_is_reported_with_source_page(self):
        findings = reconcile_documents([
            doc("1", "rtc.pdf"),
            doc("2", "sale_deed.pdf", document_type="Sale Deed", survey_number="128/3"),
        ])
        finding = next(item for item in findings if item.kind == "survey_mismatch")
        self.assertEqual(finding.evidence[0].page, 2)

    def test_extent_mismatch_is_reported(self):
        findings = reconcile_documents([
            doc("1", "rtc.pdf", land_extent="2.10 acres"),
            doc("2", "sale_deed.pdf", document_type="Sale Deed", land_extent="1.84 acres"),
        ])
        self.assertIn("extent_mismatch", {item.kind for item in findings})

    def test_missing_mutation_is_reported_for_sale_deed(self):
        findings = reconcile_documents([
            doc("1", "sale_deed.pdf", document_type="Sale Deed"),
        ])
        self.assertIn("mutation_gap", {item.kind for item in findings})

    def test_similar_names_are_ambiguous_not_automatically_equal(self):
        self.assertEqual(classify_name_match("ramesh kumar", "ramesh kumar singh"), "ambiguous")

    def test_ambiguous_owner_finding_contains_resolution_and_action(self):
        findings = reconcile_documents([
            doc("1", "rtc.pdf", owner_names=["Ramesh Kumar"]),
            doc("2", "mutation.pdf", owner_names=["Ramesh Kumar Singh"], document_type="Mutation Extract"),
        ])
        finding = next(item for item in findings if item.kind == "entity_ambiguity")
        self.assertGreater(finding.confidence, 0)
        self.assertTrue(finding.verification_action)
        self.assertEqual(finding.resolutions[0].state, "ambiguous")


if __name__ == "__main__":
    unittest.main()
