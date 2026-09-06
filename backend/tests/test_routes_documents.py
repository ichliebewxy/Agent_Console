import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request, UploadFile
from backend.knowledge.milvus_writer import MilvusWriter


import backend.api.routes_documents as routes_documents


class DocumentRouteTests(unittest.IsolatedAsyncioTestCase):
    def ingestion_fixture(self, directory, *, fail_write=False):
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(routes_documents, "UPLOAD_DIR", Path(directory)))
        docs = [
            {"filename": "码蹄杯资料.docx", "chunk_level": level, "text": "中文正文保持正确"}
            for level in (1, 2, 3)
        ]
        stack.enter_context(patch.object(routes_documents.loader, "load_document", return_value=docs))
        stack.enter_context(patch.object(routes_documents.milvus_manager, "init_collection"))
        delete = stack.enter_context(patch.object(routes_documents, "_delete_existing"))
        parents = stack.enter_context(patch.object(routes_documents.parent_chunk_store, "upsert_documents"))

        def write(documents, on_progress):
            self.assertEqual(documents[0]["filename"], "码蹄杯资料.docx")
            self.assertEqual(documents[0]["text"], "中文正文保持正确")
            if fail_write:
                raise RuntimeError("索引写入失败")
            on_progress(1, 1)

        stack.enter_context(patch.object(routes_documents.milvus_writer, "write_documents", side_effect=write))
        return delete, parents

    async def streamed_upload(self):
        request = Request({"type": "http", "headers": [(b"accept", b"text/event-stream")]})
        upload = UploadFile(filename="码蹄杯资料.docx", file=io.BytesIO(b"source"))
        response = await routes_documents.upload_document(upload, request)
        # The response must no longer depend on the multipart file being open.
        await upload.close()
        frames = [frame async for frame in response.body_iterator]
        return [json.loads(frame.removeprefix("data: ")) for frame in frames if frame.startswith("data:")]

    async def test_stream_reports_real_stages_then_success_after_both_stores_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            _, parents = self.ingestion_fixture(directory)
            events = await self.streamed_upload()
            self.assertEqual([event["stage"] for event in events], ["parsing", "indexing", "indexing", "saving", "complete"])
            self.assertEqual(events[1]["processed"], 0)
            self.assertEqual(events[2]["processed"], 1)
            self.assertEqual(events[-1]["chunks_processed"], 1)
            self.assertEqual(events[-1]["parent_chunks_processed"], 2)
            self.assertEqual(events[-1]["filename"], "码蹄杯资料.docx")
            parents.assert_called_once()
            self.assertEqual([path.name for path in Path(directory).iterdir()], ["码蹄杯资料.docx"])

    async def test_streamed_write_failure_reports_error_and_cleans_partial_index(self):
        with tempfile.TemporaryDirectory() as directory:
            delete, parents = self.ingestion_fixture(directory, fail_write=True)
            events = await self.streamed_upload()
            self.assertEqual(events[-1]["type"], "error")
            self.assertIn("索引写入失败", events[-1]["message"])
            self.assertFalse(any(event["type"] == "complete" for event in events))
            self.assertEqual(delete.call_count, 2)
            parents.assert_not_called()

    async def test_streamed_parent_save_failure_never_emits_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            delete, parents = self.ingestion_fixture(directory)
            parents.side_effect = OSError("上下文保存失败")
            events = await self.streamed_upload()
            self.assertEqual(events[-1]["type"], "error")
            self.assertIn("上下文保存失败", events[-1]["message"])
            self.assertEqual(delete.call_count, 2)

    async def test_json_upload_keeps_the_existing_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            self.ingestion_fixture(directory)
            upload = UploadFile(filename="码蹄杯资料.docx", file=io.BytesIO(b"source"))
            response = await routes_documents.upload_document(upload)
            self.assertEqual(response.filename, "码蹄杯资料.docx")
            self.assertEqual(response.chunks_processed, 1)
            self.assertEqual(response.parent_chunks_processed, 2)

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


class WriterProgressTests(unittest.TestCase):
    def test_progress_only_advances_after_successful_batch_insertion(self):
        embedding = Mock()
        embedding.get_all_embeddings.side_effect = lambda texts: ([[1.0]] * len(texts), [{}] * len(texts))
        manager = Mock()
        writer = MilvusWriter(embedding, manager)
        progress = []
        docs = [{"text": "中文正文", "filename": "资料.docx", "file_type": "Word"}] * 3

        def report(done, total):
            progress.append((done, total, manager.insert.call_count))

        writer.write_documents(docs, batch_size=2, on_progress=report)
        self.assertEqual(progress, [(2, 3, 1), (3, 3, 2)])
        progress.clear()
        manager.insert.side_effect = RuntimeError("write failed")
        with self.assertRaises(RuntimeError):
            writer.write_documents(docs, batch_size=2, on_progress=report)
        self.assertEqual(progress, [])
        embedding.increment_remove_documents.assert_called_once()


if __name__ == "__main__":
    unittest.main()
