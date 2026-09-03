import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.config.runtime_data import TMP_ROOT
from backend.knowledge.document_loader import DocumentLoader


class DocumentLoaderWordTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.dict("os.environ", {"DASHSCOPE_API_KEY": ""})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
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

    def test_default_image_directory_is_under_project_tmp(self):
        loader = DocumentLoader()
        self.assertEqual(Path(loader.image_output_dir), TMP_ROOT / "knowledge" / "extracted_images")

    def test_txt_preserves_three_level_parent_child_links(self):
        file_path = Path(self.temp_directory.name) / "hierarchy.txt"
        file_path.write_text("知识库文件切分与父子关系验证。\n" * 150, encoding="utf-8")
        chunks = self.loader.load_document(str(file_path), file_path.name)
        by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
        self.assertEqual(len(by_id), len(chunks))
        self.assertEqual({chunk["chunk_level"] for chunk in chunks}, {1, 2, 3})
        for chunk in chunks:
            self.assertEqual(by_id[chunk["root_chunk_id"]]["chunk_level"], 1)
            if chunk["chunk_level"] > 1:
                parent = by_id[chunk["parent_chunk_id"]]
                self.assertEqual(parent["chunk_level"], chunk["chunk_level"] - 1)
                self.assertIn(chunk["text"], parent["text"])

    def test_xlsx_parser_dependencies_are_available(self):
        from openpyxl import Workbook

        file_path = Path(self.temp_directory.name) / "table.xlsx"
        workbook = Workbook()
        workbook.active.append(["产品", "数量"])
        workbook.active.append(["知识库", 3])
        workbook.save(file_path)
        workbook.close()
        chunks = self.loader.load_document(str(file_path), file_path.name)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk["file_type"] == "Excel" for chunk in chunks))
        self.assertIn("知识库", chunks[0]["text"])

    def test_optional_ocr_dependency_is_available(self):
        from dashscope import MultiModalConversation
        from xlrd import open_workbook

        self.assertTrue(callable(MultiModalConversation.call))
        self.assertTrue(callable(open_workbook))


if __name__ == "__main__":
    unittest.main()
