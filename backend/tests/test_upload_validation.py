import unittest

from app.services.upload_validation import (
    UploadValidationError,
    safe_filename,
    validate_case_batch,
    validate_file_signature,
)


class UploadValidationTests(unittest.TestCase):
    def test_pdf_signature_and_normalized_filename(self):
        name = safe_filename("../RTC record.pdf")
        self.assertEqual(name, "RTC record.pdf")
        self.assertEqual(
            validate_file_signature(name, "application/pdf", b"%PDF-1.7\n..."),
            "application/pdf",
        )

    def test_rejects_spoofed_extension(self):
        with self.assertRaises(UploadValidationError):
            validate_file_signature("record.pdf", "application/pdf", b"\x89PNG\r\n\x1a\n")

    def test_rejects_unknown_signature(self):
        with self.assertRaises(UploadValidationError):
            validate_file_signature("record.jpg", "image/jpeg", b"not-an-image")

    def test_case_document_limit(self):
        with self.assertRaises(UploadValidationError):
            validate_case_batch(
                existing_document_count=20,
                existing_bytes=0,
                incoming_sizes=[1024],
                max_documents=20,
                max_case_bytes=100 * 1024 * 1024,
            )

    def test_case_size_limit(self):
        with self.assertRaises(UploadValidationError):
            validate_case_batch(
                existing_document_count=1,
                existing_bytes=95,
                incoming_sizes=[10],
                max_documents=20,
                max_case_bytes=100,
            )


if __name__ == "__main__":
    unittest.main()
