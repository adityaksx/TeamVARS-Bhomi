import unittest

from app.adapters.uttar_pradesh import adapt_up_document
from app.services.normalization import normalize_document
from app.services.rules import build_coverage


class UttarPradeshAdapterTests(unittest.TestCase):
    def test_gata_and_tehsil_map_to_canonical_fields(self):
        raw = {
            "document_type": "Khatauni",
            "khatedar_names": ["श्री Ramesh Kumar"],
            "gata_number": "Gata No. 124/3",
            "tehsil": "Agra Sadar",
            "village": "Sikandra",
            "district": "Agra",
        }
        adapted = adapt_up_document(raw)
        normalized = normalize_document(adapted)

        self.assertEqual(normalized["survey_number"], "124/3")
        self.assertEqual(normalized["plot_number"], "124/3")
        self.assertEqual(normalized["tehsil"], "agra sadar")
        self.assertEqual(normalized["taluk"], "agra sadar")
        self.assertEqual(normalized["owner_names"], ["ramesh kumar"])

    def test_up_document_types_have_expected_coverage(self):
        docs = [
            {"filename": "khatauni.pdf", "normalized": {"document_type": "Khatauni"}},
            {"filename": "gata-khasra.pdf", "normalized": {"document_type": "Gata / Khasra"}},
            {"filename": "namantaran.pdf", "normalized": {"document_type": "Mutation / Namantaran"}},
            {"filename": "sale-deed.pdf", "normalized": {"document_type": "Sale Deed"}},
        ]
        coverage = {item["name"]: item["status"] for item in build_coverage(docs)}
        self.assertEqual(coverage["Khatauni"], "present")
        self.assertEqual(coverage["Gata / Khasra"], "present")
        self.assertEqual(coverage["Mutation / Namantaran"], "present")
        self.assertEqual(coverage["Sale Deed"], "present")
        self.assertEqual(coverage["Encumbrance / Litigation"], "missing")


if __name__ == "__main__":
    unittest.main()
