import unittest
from fastapi import HTTPException

from app.api.v1.endpoints.bills import _detect_mime, _scan_upload_metadata


class UploadValidationTests(unittest.TestCase):
    def test_detect_mime_rejects_unknown_binary(self) -> None:
        payload = b'MZ\x90\x00\x03\x00\x00\x00'
        self.assertIsNone(_detect_mime(payload))

    def test_pdf_metadata_scan_rejects_corrupted_pdf(self) -> None:
        payload = b'%PDF-1.7\nthis-is-not-a-valid-pdf'
        with self.assertRaises(HTTPException):
            _scan_upload_metadata(payload, 'application/pdf')


if __name__ == '__main__':
    unittest.main()
