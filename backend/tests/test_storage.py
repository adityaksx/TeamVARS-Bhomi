import tempfile
import unittest
from pathlib import Path

import app.services.case_store as case_store
from app.services.storage import (
    delete_document,
    exists,
    materialize,
    put_document,
    read_bytes,
)


class StorageTests(unittest.TestCase):
    def test_local_document_round_trip_and_materialize(self):
        original_uploads = case_store.UPLOADS
        with tempfile.TemporaryDirectory() as directory:
            case_store.UPLOADS = Path(directory)
            try:
                payload = b"%PDF-1.7\nhello"
                storage_ref = put_document(
                    "case_test",
                    "doc_test",
                    "record.pdf",
                    payload,
                    "application/pdf",
                )
                self.assertTrue(exists(storage_ref))
                self.assertEqual(read_bytes(storage_ref), payload)
                with materialize(storage_ref) as path:
                    self.assertEqual(path.read_bytes(), payload)
                    self.assertTrue(path.is_file())
                delete_document(storage_ref)
                self.assertFalse(exists(storage_ref))
            finally:
                case_store.UPLOADS = original_uploads


if __name__ == "__main__":
    unittest.main()
