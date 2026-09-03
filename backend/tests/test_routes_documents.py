import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile


import backend.api.routes_documents as routes_documents


class DocumentRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_filename_validation_rejects_paths_and_windows_devices(self):
        self.assertEqual(routes_documents._validated_filename("报告.doc"), "报告.doc")
        for invalid in ("", "../report.doc", r"C:\fakepath\report.doc", "CON.doc", "bad:name.doc"):
            with self.subTest(filename=invalid), self.assertRaises(HTTPException):
                routes_documents._validated_filename(invalid)

    async def test_upload_size_limit_is_enforced_and_staging_file_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            upload = UploadFile(filename="large.doc", file=io.BytesIO(b"12345"))
            with (
                patch("backend.api.routes_documents.UPLOAD_DIR", Path(directory)),
                patch("backend.api.routes_documents.MAX_UPLOAD_SIZE", 4),
            ):
                with self.assertRaises(HTTPException) as context:
                    await routes_documents._save_upload(upload, upload.filename)
                self.assertEqual(context.exception.status_code, 413)
                self.assertEqual(list(Path(directory).iterdir()), [])

    async def test_parse_failure_preserves_existing_source_file(self):
        with tempfile.TemporaryDirectory() as directory:
            upload_directory = Path(directory)
            existing_path = upload_directory / "report.doc"
            existing_path.write_bytes(b"old source")
            upload = UploadFile(filename="report.doc", file=io.BytesIO(b"bad replacement"))
            with (
                patch("backend.api.routes_documents.UPLOAD_DIR", upload_directory),
                patch.object(
                    routes_documents.loader,
                    "load_document",
                    side_effect=ValueError("invalid document"),
                ),
            ):
                with self.assertRaises(HTTPException) as context:
                    await routes_documents.upload_document(upload)

            self.assertEqual(context.exception.status_code, 500)
            self.assertEqual(existing_path.read_bytes(), b"old source")
            self.assertEqual([path.name for path in upload_directory.iterdir()], ["report.doc"])


if __name__ == "__main__":
    unittest.main()
