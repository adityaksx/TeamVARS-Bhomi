import tempfile
import unittest
from pathlib import Path

import fitz

from app.services.document_view import build_source_anchors, find_text_anchor, page_count


class DocumentViewTests(unittest.TestCase):
    def make_pdf(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.close()
        path = Path(handle.name)
        document = fitz.open()
        page = document.new_page(width=600, height=800)
        page.insert_text((72, 110), "Recorded owner: Ramesh Kumar")
        page.insert_text((72, 145), "Survey number: 128/3A")
        document.save(path)
        document.close()
        return path

    def test_finds_text_bbox(self):
        path = self.make_pdf()
        try:
            anchor = find_text_anchor(path, "Ramesh Kumar")
            self.assertIsNotNone(anchor)
            self.assertEqual(anchor["page"], 1)
            self.assertEqual(len(anchor["bbox"]), 4)
            self.assertGreater(anchor["bbox"][2], anchor["bbox"][0])
        finally:
            path.unlink(missing_ok=True)

    def test_builds_scalar_and_owner_anchors(self):
        path = self.make_pdf()
        try:
            anchors = build_source_anchors(
                path,
                {
                    "owner_names": ["Ramesh Kumar"],
                    "survey_number": "128/3A",
                },
                {"owner_names": 1, "survey_number": 1},
            )
            self.assertIn("owner_names:ramesh kumar", anchors)
            self.assertIn("survey_number", anchors)
            self.assertEqual(page_count(path), 1)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
