"""Local hybrid retrieval orchestration."""
from typing import Any, Dict

from embedding import embedding_service as _embedding_service
from milvus_client import MilvusManager
from ops_store import record_tool_failure
from retrieval_steps import auto_merge_documents, get_rerank_endpoint, rerank_documents
from settings import (
    AUTO_MERGE_ENABLED,
    AUTO_MERGE_THRESHOLD,
    LEAF_RETRIEVE_LEVEL,
    RERANK_API_KEY,
    RERANK_BINDING_HOST,
    RERANK_MODEL,
)

_milvus_manager = MilvusManager()


def _base_meta(candidate_k: int) -> Dict[str, Any]:
    return {
        "rerank_enabled": bool(RERANK_MODEL and RERANK_API_KEY and RERANK_BINDING_HOST),
        "rerank_applied": False,
        "rerank_model": RERANK_MODEL,
        "rerank_endpoint": get_rerank_endpoint(),
        "rerank_error": None,
        "candidate_k": candidate_k,
        "candidate_count": 0,
        "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
        "auto_merge_enabled": AUTO_MERGE_ENABLED,
        "auto_merge_applied": False,
        "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
        "auto_merge_replaced_chunks": 0,
        "auto_merge_steps": 0,
    }


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

    try:
        retrieved = _search_local(query, candidate_k, filter_expr)
        docs, meta = _finalize_retrieval(query, retrieved, top_k, candidate_k)
        if not docs:
            meta["retrieval_mode"] = "hybrid_empty"
        return {"docs": docs, "meta": meta}
    except Exception as exc:
        record_tool_failure(
            "milvus_hybrid_retrieval",
            str(exc),
            {"query": query, "top_k": top_k},
            "Returning empty retrieval so the RAG graph can try query rewriting.",
        )
        meta = _base_meta(candidate_k)
        meta.update({
            "rerank_error": "hybrid_retrieve_failed",
            "retrieval_mode": "failed",
        })
        return {"docs": [], "meta": meta}
