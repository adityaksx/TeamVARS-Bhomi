import unittest

from app.services.pipeline import _digitise_anchors
from app.services.reporting import build_pdf_report


class DigitiseAndReportingTests(unittest.TestCase):
    def test_digitise_block_becomes_source_anchor(self):
        payload = {
            "result": {
                "pages": [
                    {
                        "page_num": 1,
                        "width": 1000,
                        "height": 1400,
                        "origin": "top-left",
                        "blocks": [
                            {
                                "id": "b1",
                                "type": "paragraph",
                                "text": "Recorded owner: Ramesh Kumar",
                                "bbox": [100, 200, 500, 260],
                                "ocr_confidence": 0.97,
                            }
                        ],
                    }
                ]
            }
        }
        anchors = _digitise_anchors(
            payload,
            {"owner_names": ["Ramesh Kumar"]},
            page_offset=1,
        )
        anchor = anchors["owner_names:ramesh kumar"]
        self.assertEqual(anchor["page"], 2)
        self.assertEqual(anchor["method"], "sarvam-digitise")
        self.assertEqual(anchor["bbox"], [100.0, 200.0, 500.0, 260.0])
        self.assertEqual(anchor["confidence"], 0.97)

    def test_pdf_report_is_valid_pdf(self):
        dashboard = {
            "score": 75,
            "status": "Needs review",
            "documents": 2,
            "reasoning_provider": "mock",
            "property": {
                "village": "Example Village",
                "taluk": "Example Taluk",
                "district": "Example District",
                "survey": "128/3A",
                "owner": "Ramesh Kumar",
            },
            "findings": [],
            "coverage": [],
        }
        payload = build_pdf_report({"id": "case_test", "name": "Test"}, dashboard)
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertGreater(len(payload), 1000)


if __name__ == "__main__":
    unittest.main()
