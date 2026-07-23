import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from document_loader import DocumentLoader


class DocumentLoaderWordTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.loader = DocumentLoader(image_output_dir=self.temp_directory.name)

    def test_doc_uses_legacy_reader_instead_of_python_docx(self):
        file_path = Path(self.temp_directory.name) / "legacy.doc"
        file_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

        with (
            patch.object(
                self.loader,
                "_extract_legacy_doc_text",
                return_value="旧版 Word 正文",
            ) as legacy_reader,
            patch.object(self.loader, "_extract_docx_text") as docx_reader,
        ):
            documents = self.loader.load_document(str(file_path), file_path.name)

        legacy_reader.assert_called_once_with(str(file_path))
        docx_reader.assert_not_called()
        self.assertTrue(documents)
        self.assertTrue(all(item["file_type"] == "Word" for item in documents))

    def test_docx_uses_openxml_reader(self):
        file_path = Path(self.temp_directory.name) / "modern.docx"
        file_path.write_bytes(b"PK")

        with (
            patch.object(
                self.loader,
                "_extract_docx_text",
                return_value="OpenXML Word 正文",
            ) as docx_reader,
            patch.object(self.loader, "_extract_legacy_doc_text") as legacy_reader,
        ):
            documents = self.loader.load_document(str(file_path), file_path.name)

        docx_reader.assert_called_once_with(str(file_path))
        legacy_reader.assert_not_called()
        self.assertTrue(documents)

    def test_stale_doc_extension_with_zip_signature_uses_docx_reader(self):
        file_path = Path(self.temp_directory.name) / "renamed.doc"
        file_path.write_bytes(b"PK\x03\x04")

        with patch.object(
            self.loader._word_reader,
            "extract_docx_text",
            return_value="扩展名错误但内容可读",
        ) as docx_reader:
            text = self.loader._extract_legacy_doc_text(str(file_path))

        self.assertEqual(text, "扩展名错误但内容可读")
        docx_reader.assert_called_once_with(str(file_path))

    def test_word_control_characters_are_normalized(self):
        normalized = self.loader._normalize_word_text("\x01标题\r正文\x07单元格\x0c下一页")

        self.assertEqual(normalized, "标题\n正文\t单元格\x0c下一页")


if __name__ == "__main__":
    unittest.main()
