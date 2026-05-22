"""Local/RAGFlow retrieval orchestration."""
from typing import Any, Dict

from embedding import EmbeddingService
from milvus_client import MilvusManager
from ops_store import record_tool_failure
from query_expansion import generate_hypothetical_document, step_back_expand
from ragflow_client import retrieve_from_ragflow
from retrieval_steps import auto_merge_documents, dedupe_retrieved_docs, get_rerank_endpoint, rerank_documents
from settings import AUTO_MERGE_ENABLED, AUTO_MERGE_THRESHOLD, LEAF_RETRIEVE_LEVEL, RERANK_API_KEY, RERANK_BINDING_HOST, RERANK_MODEL

_embedding_service = EmbeddingService()
_milvus_manager = MilvusManager()


def _base_failure_meta(candidate_k: int, ragflow_meta: dict) -> Dict[str, Any]:
    meta = {
        "rerank_enabled": bool(RERANK_MODEL and RERANK_API_KEY and RERANK_BINDING_HOST),
        "rerank_applied": False,
        "rerank_model": RERANK_MODEL,
        "rerank_endpoint": get_rerank_endpoint(),
        "candidate_k": candidate_k,
        "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
        "auto_merge_enabled": AUTO_MERGE_ENABLED,
        "auto_merge_applied": False,
        "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
        "auto_merge_replaced_chunks": 0,
        "auto_merge_steps": 0,
    }
    meta.update(ragflow_meta)
    return meta


def _search_local(query: str, candidate_k: int, filter_expr: str, dense_only: bool = False) -> list[dict]:
    dense_embedding = _embedding_service.get_embeddings([query])[0]
    if dense_only:
        return _milvus_manager.dense_retrieve(
            dense_embedding=dense_embedding,
            top_k=candidate_k,
            filter_expr=filter_expr,
        )
    sparse_embedding = _embedding_service.get_sparse_embedding(query)
    return _milvus_manager.hybrid_retrieve(
        dense_embedding=dense_embedding,
        sparse_embedding=sparse_embedding,
        top_k=candidate_k,
        filter_expr=filter_expr,
    )


def _finalize_retrieval(query: str, retrieved: list[dict], top_k: int, candidate_k: int, ragflow_meta: dict, mode: str):
    reranked, rerank_meta = rerank_documents(query=query, docs=retrieved, top_k=top_k)
    merged_docs, merge_meta = auto_merge_documents(docs=reranked, top_k=top_k)
    rerank_meta.update({
        "retrieval_mode": mode,
        "candidate_k": candidate_k,
        "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
    })
    rerank_meta.update(merge_meta)
    rerank_meta.update(ragflow_meta)
    return merged_docs, rerank_meta


def retrieve_documents(query: str, top_k: int = 5) -> Dict[str, Any]:
    candidate_k = max(top_k * 3, top_k)
    filter_expr = f"chunk_level == {LEAF_RETRIEVE_LEVEL}"
    ragflow_docs, ragflow_meta = retrieve_from_ragflow(query, top_k=top_k)

    try:
        retrieved = _search_local(query, candidate_k, filter_expr, dense_only=False)
        local_docs, meta = _finalize_retrieval(query, retrieved, top_k, candidate_k, ragflow_meta, "hybrid")
        return {"docs": dedupe_retrieved_docs(ragflow_docs + local_docs)[:top_k], "meta": meta}
    except Exception as hybrid_error:
        record_tool_failure(
            "milvus_hybrid_retrieval",
            str(hybrid_error),
            {"query": query, "top_k": top_k},
            "Trying dense retrieval fallback.",
        )

    try:
        retrieved = _search_local(query, candidate_k, filter_expr, dense_only=True)
        local_docs, meta = _finalize_retrieval(query, retrieved, top_k, candidate_k, ragflow_meta, "dense_fallback")
        return {"docs": dedupe_retrieved_docs(ragflow_docs + local_docs)[:top_k], "meta": meta}
    except Exception as dense_error:
        record_tool_failure(
            "milvus_dense_retrieval",
            str(dense_error),
            {"query": query, "top_k": top_k},
            "Returning RAGFlow results if available, otherwise empty retrieval.",
        )

    meta = _base_failure_meta(candidate_k, ragflow_meta)
    meta.update({
        "rerank_error": "local_retrieve_failed" if ragflow_docs else "retrieve_failed",
        "retrieval_mode": "ragflow_fallback" if ragflow_docs else "failed",
        "candidate_count": len(ragflow_docs),
    })
    return {"docs": ragflow_docs[:top_k], "meta": meta}
