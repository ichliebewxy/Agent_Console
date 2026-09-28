"""Opt-in integration check against a local Milvus instance."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from document_versions import DocumentVersionStore, version_filter
from milvus_client import MilvusManager


@unittest.skipUnless(os.environ.get("MILVUS_INTEGRATION") == "1", "requires local Milvus")
class DocumentVersionMilvusTests(unittest.TestCase):
    def test_active_version_filters_query_and_hybrid_search(self):
        manager = MilvusManager()
        manager.collection_name = "agent_console_version_check_" + uuid4().hex[:12]
        fields = {
            "dense_embedding": [1.0, 0.0, 0.0, 0.0],
            "sparse_embedding": {1: 1.0},
            "filename": "check.txt",
            "file_type": "TXT",
            "file_path": "",
            "page_number": 1,
            "chunk_idx": 0,
            "parent_chunk_id": "",
            "root_chunk_id": "",
            "chunk_level": 3,
        }
        try:
            manager.init_collection(dense_dim=4)
            manager.insert([
                {**fields, "text": "old", "chunk_id": "check.txt::p1::l3::0"},
                {
                    **fields,
                    "text": "new",
                    "chunk_id": "vabc123::check.txt::p1::l3::0",
                    "document_version": "abc123",
                },
            ])
            manager._call(lambda client: client.load_collection(manager.collection_name))
            with tempfile.TemporaryDirectory() as directory:
                versions = DocumentVersionStore(Path(directory) / "versions.sqlite3")
                versions.prepare("check.txt")
                old = manager.query(
                    filter_expr=versions.active_filter(), output_fields=["text"], limit=10
                )
                self.assertEqual([row["text"] for row in old], ["old"])

                versions.activate("check.txt", "abc123")
                new = manager.query(
                    filter_expr=versions.active_filter(), output_fields=["text"], limit=10
                )
                self.assertEqual([row["text"] for row in new], ["new"])
                hits = manager.hybrid_retrieve(
                    [1.0, 0.0, 0.0, 0.0],
                    {1: 1.0},
                    top_k=2,
                    filter_expr=versions.active_filter(),
                )
                self.assertEqual([hit["text"] for hit in hits], ["new"])

                manager.delete(version_filter("check.txt", ""))
                remaining = manager.query(output_fields=["text"], limit=10)
                self.assertEqual([row["text"] for row in remaining], ["new"])
        finally:
            try:
                manager._call(lambda client: client.drop_collection(manager.collection_name))
            finally:
                manager.close()
