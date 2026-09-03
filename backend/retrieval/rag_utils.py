"""Local hybrid retrieval orchestration."""
from typing import Any, Dict

from backend.knowledge.embedding import embedding_service as _embedding_service
from backend.knowledge.milvus_client import MilvusManager
from backend.retrieval.retrieval_steps import auto_merge_documents, rerank_documents
from backend.config.settings import LEAF_RETRIEVE_LEVEL

_milvus_manager = MilvusManager()


def _search_local(query: str, candidate_k: int, filter_expr: str) -> list[dict]:
    dense_embedding = _embedding_service.get_query_embeddings([query])[0]
    sparse_embedding = _embedding_service.get_sparse_embedding(query)
    return _milvus_manager.hybrid_retrieve(
        dense_embedding=dense_embedding,
        sparse_embedding=sparse_embedding,
        top_k=candidate_k,
        filter_expr=filter_expr,
    )


def _finalize_retrieval(query: str, retrieved: list[dict], top_k: int, candidate_k: int):
    merged_candidates, merge_meta = auto_merge_documents(docs=retrieved, top_k=candidate_k)
    reranked, rerank_meta = rerank_documents(query=query, docs=merged_candidates, top_k=top_k)
    rerank_meta.update({
        "retrieval_mode": "hybrid",
        "candidate_k": candidate_k,
        "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
    })
    rerank_meta.update(merge_meta)
    return reranked, rerank_meta


def retrieve_documents(query: str, top_k: int = 5) -> Dict[str, Any]:
    candidate_k = max(top_k * 3, top_k)
    filter_expr = f"chunk_level == {LEAF_RETRIEVE_LEVEL}"

    # Infrastructure failures propagate to the HTTP/tool error response. Only a
    # successful search with no matches should trigger empty-result rewriting.
    retrieved = _search_local(query, candidate_k, filter_expr)
    docs, meta = _finalize_retrieval(query, retrieved, top_k, candidate_k)
    if not docs:
        meta["retrieval_mode"] = "hybrid_empty"
    return {"docs": docs, "meta": meta}
