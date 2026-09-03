"""Verify the retained RAG service without loading models or connecting to Milvus."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.config.settings import MILVUS_DENSE_DIM
from backend.rag_app import app, embedding_service
from backend.retrieval import rag_expanded, rag_pipeline, rag_utils


class KnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        self.warmup = patch.object(embedding_service, "warm_up", return_value={"dim": MILVUS_DENSE_DIM})
        self.warmup.start()
        self.addCleanup(self.warmup.stop)
        self.client = self.enterContext(TestClient(app))

    def test_health_and_retired_memory_routes(self):
        self.assertEqual(self.client.get("/health").json(), {"ok": True, "service": "rag"})
        for method, route in (
            ("GET", "/memory/status"),
            ("GET", "/memory/user"),
            ("POST", "/memory/user"),
            ("PUT", "/memory/entry"),
            ("DELETE", "/memory/entry"),
            ("DELETE", "/memory/user/user"),
        ):
            with self.subTest(method=method, route=route):
                self.assertEqual(self.client.request(method, route).status_code, 404)

    def test_relevant_search_returns_source_chunks_without_rewriting(self):
        doc = {"filename": "manual.txt", "page_number": 1, "text": "Pi 使用说明"}
        grader = Mock()
        grader.invoke.return_value = SimpleNamespace(content="yes")
        with (
            patch.object(rag_pipeline, "retrieve_documents", return_value={"docs": [doc], "meta": {}}),
            patch.object(rag_pipeline, "_get_grader_model", return_value=grader),
            patch.object(rag_pipeline, "_choose_strategy") as rewrite,
        ):
            response = self.client.post("/knowledge/search", json={"query": "Pi 怎么使用？"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["docs"], [doc])
        self.assertEqual(response.json()["rag_trace"]["grade_score"], "yes")
        rewrite.assert_not_called()

    def test_empty_results_still_use_query_expansion(self):
        doc = {"filename": "guide.pdf", "page_number": 2, "text": "工作区配置", "chunk_id": "guide-2"}
        with (
            patch.object(rag_pipeline, "retrieve_documents", return_value={"docs": [], "meta": {}}),
            patch.object(rag_pipeline, "_choose_strategy", return_value="step_back"),
            patch.object(rag_pipeline, "step_back_expand", return_value={"expanded_query": "工作区配置"}),
            patch.object(rag_expanded, "retrieve_documents", return_value={"docs": [doc], "meta": {}}) as expanded,
        ):
            response = self.client.post("/knowledge/search", json={"query": "如何选目录？"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["docs"][0]["filename"], "guide.pdf")
        self.assertEqual(response.json()["rag_trace"]["retrieval_stage"], "expanded")
        expanded.assert_called_once_with("工作区配置", top_k=5)

    def test_milvus_failure_is_an_error_not_an_empty_answer(self):
        with (
            patch.object(rag_utils, "_search_local", side_effect=RuntimeError("Milvus offline")),
            patch.object(rag_pipeline, "_choose_strategy") as rewrite,
        ):
            response = self.client.post("/knowledge/search", json={"query": "检索资料"})
        self.assertEqual(response.status_code, 500)
        self.assertIn("Milvus offline", response.json()["detail"])
        self.assertNotIn("docs", response.json())
        rewrite.assert_not_called()

    def test_binary_ppt_is_rejected_before_parsing(self):
        response = self.client.post("/documents/upload", files={"file": ("old.ppt", b"legacy binary")})
        self.assertEqual(response.status_code, 400)
        self.assertIn(".pptx", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
