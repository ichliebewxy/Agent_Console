import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException, UploadFile

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import rag_utils
import routes_documents
from document_versions import DocumentVersionStore, version_chunk_prefix, version_filter
from parent_chunk_store import ParentChunkStore


class DocumentRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_filename_validation_rejects_paths_and_windows_devices(self):
        self.assertEqual(routes_documents._validated_filename("报告.doc"), "报告.doc")
        mojibake_filename = "码蹄杯资料.docx".encode("utf-8").decode("latin-1")
        self.assertEqual(
            routes_documents._validated_filename(mojibake_filename),
            "码蹄杯资料.docx",
        )
        for invalid in ("", "../report.doc", r"C:\fakepath\report.doc", "CON.doc", "bad:name.doc", "bad\x81.doc"):
            with self.subTest(filename=invalid), self.assertRaises(HTTPException):
                routes_documents._validated_filename(invalid)

    async def test_upload_size_limit_is_enforced_and_staging_file_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            upload = UploadFile(filename="large.doc", file=io.BytesIO(b"12345"))
            with (
                patch("routes_documents.UPLOAD_DIR", Path(directory)),
                patch("routes_documents.MAX_UPLOAD_SIZE", 4),
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
                patch("routes_documents.UPLOAD_DIR", upload_directory),
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

    async def test_empty_upload_returns_422_without_replacing_existing_document(self):
        with tempfile.TemporaryDirectory() as directory:
            upload_directory = Path(directory)
            existing_path = upload_directory / "report.txt"
            existing_path.write_bytes(b"old source")
            app = FastAPI()
            app.include_router(routes_documents.router)
            with (
                patch("routes_documents.UPLOAD_DIR", upload_directory),
                patch.object(routes_documents.milvus_manager, "init_collection") as init_collection,
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    for content in (b"", b"   \n"):
                        with self.subTest(content=content):
                            response = await client.post(
                                "/documents/upload",
                                files={"file": ("report.txt", content, "text/plain")},
                            )
                            self.assertEqual(response.status_code, 422)

            init_collection.assert_not_called()
            self.assertEqual(existing_path.read_bytes(), b"old source")
            self.assertEqual([path.name for path in upload_directory.iterdir()], ["report.txt"])

    async def test_document_without_leaf_chunks_returns_422(self):
        with tempfile.TemporaryDirectory() as directory:
            upload_directory = Path(directory)
            with (
                patch("routes_documents.UPLOAD_DIR", upload_directory),
                patch.object(
                    routes_documents.loader,
                    "load_document",
                    return_value=[{"chunk_level": 1, "text": "only parent"}],
                ),
                patch.object(routes_documents.milvus_manager, "init_collection") as init_collection,
            ):
                with self.assertRaises(HTTPException) as context:
                    await routes_documents.upload_document(
                        UploadFile(filename="report.txt", file=io.BytesIO(b"content"))
                    )

            self.assertEqual(context.exception.status_code, 422)
            init_collection.assert_not_called()
            self.assertEqual(list(upload_directory.iterdir()), [])

    async def test_failed_replacement_keeps_old_source_index_and_parents(self):
        class FakeMilvus:
            def __init__(self):
                self.rows = [{"filename": "report.txt", "chunk_id": "report.txt::p1::l3::0", "text": "old"}]

            def init_collection(self):
                pass

            def query(self, filter_expr="", output_fields=None, limit=10000):
                filename = re.search(r'filename == "([^"]+)"', filter_expr)
                prefix = re.search(r'chunk_id like "([^"]+)%"', filter_expr)
                return [
                    row for row in self.rows
                    if (not filename or row["filename"] == filename.group(1))
                    and (not prefix or row["chunk_id"].startswith(prefix.group(1)))
                ][:limit]

            def delete(self, filter_expr):
                selected = self.query(filter_expr)
                self.rows = [row for row in self.rows if row not in selected]
                return {"delete_count": len(selected)}

        docs = [
            {"filename": "report.txt", "file_type": "TXT", "text": "new parent", "chunk_id": "report.txt::p1::l1::0", "parent_chunk_id": "", "root_chunk_id": "report.txt::p1::l1::0", "chunk_level": 1},
            {"filename": "report.txt", "file_type": "TXT", "text": "new leaf", "chunk_id": "report.txt::p1::l3::0", "parent_chunk_id": "report.txt::p1::l1::0", "root_chunk_id": "report.txt::p1::l1::0", "chunk_level": 3},
        ]
        for failure in ("embedding", "insert", "parent", "commit"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "report.txt").write_bytes(b"old source")
                versions = DocumentVersionStore(root / "versions.sqlite3")
                parents = ParentChunkStore(root / "parents.json")
                parents.upsert_documents([{"filename": "report.txt", "chunk_id": "report.txt::p1::l1::0", "text": "old parent"}])
                milvus = FakeMilvus()
                state = {"failure": failure}

                def write_documents(rows):
                    if state["failure"] == "embedding":
                        raise RuntimeError("embedding failed")
                    milvus.rows.extend(dict(row) for row in rows)
                    if state["failure"] == "insert":
                        raise RuntimeError("insert failed after partial write")

                real_upsert = parents.upsert_documents

                def upsert_documents(rows):
                    real_upsert(rows)
                    if state["failure"] == "parent":
                        raise RuntimeError("parent store failed after write")

                real_activate = versions.activate

                def activate(filename, version):
                    if state["failure"] == "commit":
                        raise RuntimeError("commit failed")
                    real_activate(filename, version)

                with (
                    patch("routes_documents.UPLOAD_DIR", root),
                    patch.object(routes_documents, "document_versions", versions),
                    patch.object(routes_documents, "parent_chunk_store", parents),
                    patch.object(routes_documents, "milvus_manager", milvus),
                    patch.object(routes_documents.milvus_writer, "write_documents", side_effect=write_documents),
                    patch.object(routes_documents.loader, "load_document", side_effect=lambda *_: [dict(doc) for doc in docs]),
                    patch.object(routes_documents.embedding_service, "increment_remove_documents"),
                    patch.object(parents, "upsert_documents", side_effect=upsert_documents),
                    patch.object(versions, "activate", side_effect=activate),
                ):
                    with self.assertRaises(HTTPException):
                        await routes_documents.upload_document(
                            UploadFile(filename="report.txt", file=io.BytesIO(b"new source"))
                        )
                    self.assertEqual((root / "report.txt").read_bytes(), b"old source")
                    self.assertEqual([row["text"] for row in milvus.rows], ["old"])
                    self.assertEqual(versions.active_version("report.txt"), "")
                    self.assertEqual(parents.get_documents_by_ids(["report.txt::p1::l1::0"])[0]["text"], "old parent")

                    state["failure"] = None
                    result = await routes_documents.upload_document(
                        UploadFile(filename="report.txt", file=io.BytesIO(b"new source"))
                    )
                    self.assertEqual(result.chunks_processed, 1)
                    self.assertEqual(len(milvus.rows), 1)
                    self.assertEqual(milvus.rows[0]["text"], "new leaf")
                    version = versions.active_version("report.txt")
                    self.assertTrue(milvus.rows[0]["chunk_id"].startswith(version_chunk_prefix("report.txt", version)))
                    self.assertEqual(Path(milvus.rows[0]["file_path"]).read_bytes(), b"new source")

    def test_retrieval_uses_only_the_active_document_version(self):
        with tempfile.TemporaryDirectory() as directory:
            versions = DocumentVersionStore(Path(directory) / "versions.sqlite3")
            versions.prepare("report.txt")
            with (
                patch.object(rag_utils, "_document_versions", versions),
                patch.object(rag_utils, "_search_local", return_value=[]) as search,
            ):
                rag_utils.retrieve_documents("query")
                self.assertIn('chunk_id like "report.txt::%"', search.call_args.args[2])

                versions.activate("report.txt", "abc123")
                rag_utils.retrieve_documents("query")
                self.assertIn('chunk_id like "vabc123::%"', search.call_args.args[2])
                self.assertNotIn('chunk_id like "report.txt::%"', search.call_args.args[2])

    def test_legacy_version_filter_escapes_filename_wildcards(self):
        expression = version_filter("v%_file.txt", "")
        self.assertIn(r"v\\%\\_file.txt::%", expression)


if __name__ == "__main__":
    unittest.main()
