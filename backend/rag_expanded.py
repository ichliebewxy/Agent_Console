"""Expanded-query retrieval node for the RAG graph."""
from typing import List

from query_expansion import generate_hypothetical_document
from rag_state import RAGState, format_docs
from rag_utils import retrieve_documents
from tools import emit_rag_step


def _init_meta() -> dict:
    return {
        "rerank_applied": False,
        "rerank_enabled": False,
        "rerank_model": None,
        "rerank_endpoint": None,
        "rerank_errors": [],
        "retrieval_mode": None,
        "candidate_k": None,
        "leaf_retrieve_level": None,
        "auto_merge_enabled": None,
        "auto_merge_applied": False,
        "auto_merge_threshold": None,
        "auto_merge_replaced_chunks": 0,
        "auto_merge_steps": 0,
    }


def _merge_meta(target: dict, source: dict, prefix: str):
    target["rerank_applied"] = target["rerank_applied"] or bool(source.get("rerank_applied"))
    target["rerank_enabled"] = target["rerank_enabled"] or bool(source.get("rerank_enabled"))
    target["rerank_model"] = target["rerank_model"] or source.get("rerank_model")
    target["rerank_endpoint"] = target["rerank_endpoint"] or source.get("rerank_endpoint")
    if source.get("rerank_error"):
        target["rerank_errors"].append(f"{prefix}:{source.get('rerank_error')}")
    target["retrieval_mode"] = target["retrieval_mode"] or source.get("retrieval_mode")
    target["candidate_k"] = target["candidate_k"] or source.get("candidate_k")
    target["leaf_retrieve_level"] = target["leaf_retrieve_level"] or source.get("leaf_retrieve_level")
    if target["auto_merge_enabled"] is None:
        target["auto_merge_enabled"] = source.get("auto_merge_enabled")
    target["auto_merge_applied"] = target["auto_merge_applied"] or bool(source.get("auto_merge_applied"))
    target["auto_merge_threshold"] = target["auto_merge_threshold"] or source.get("auto_merge_threshold")
    target["auto_merge_replaced_chunks"] += int(source.get("auto_merge_replaced_chunks") or 0)
    target["auto_merge_steps"] += int(source.get("auto_merge_steps") or 0)


def _dedupe(results: List[dict]) -> List[dict]:
    deduped = []
    seen = set()
    for item in results:
        key = item.get("chunk_id") or (item.get("filename"), item.get("page_number"), item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    for idx, item in enumerate(deduped, 1):
        item["rrf_rank"] = idx
    return deduped


def _retrieve_branch(label: str, query: str, meta: dict) -> List[dict]:
    retrieved = retrieve_documents(query, top_k=5)
    branch_meta = retrieved.get("meta", {})
    emit_rag_step(
        "🧱",
        f"{label} 三级检索",
        (
            f"L{branch_meta.get('leaf_retrieve_level', 3)} 召回，"
            f"候选 {branch_meta.get('candidate_k', 0)}，"
            f"合并替换 {branch_meta.get('auto_merge_replaced_chunks', 0)}"
        ),
    )
    _merge_meta(meta, branch_meta, label.lower())
    return retrieved.get("docs", [])


def retrieve_expanded(state: RAGState) -> RAGState:
    strategy = state.get("expansion_type") or "step_back"
    emit_rag_step("🔄", "使用扩展查询重新检索...", f"策略: {strategy}")
    results: List[dict] = []
    meta = _init_meta()

    if strategy in ("hyde", "complex"):
        hyde_query = state.get("hypothetical_doc") or generate_hypothetical_document(state["question"])
        results.extend(_retrieve_branch("HyDE", hyde_query, meta))

    if strategy in ("step_back", "complex"):
        step_query = state.get("expanded_query") or state["question"]
        results.extend(_retrieve_branch("Step-back", step_query, meta))

    deduped = _dedupe(results)
    emit_rag_step("✅", f"扩展检索完成，共 {len(deduped)} 个片段")
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "expanded_query": state.get("expanded_query") or state["question"],
        "step_back_question": state.get("step_back_question", ""),
        "step_back_answer": state.get("step_back_answer", ""),
        "hypothetical_doc": state.get("hypothetical_doc", ""),
        "expansion_type": strategy,
        "retrieved_chunks": deduped,
        "expanded_retrieved_chunks": deduped,
        "retrieval_stage": "expanded",
        "rerank_enabled": meta["rerank_enabled"],
        "rerank_applied": meta["rerank_applied"],
        "rerank_model": meta["rerank_model"],
        "rerank_endpoint": meta["rerank_endpoint"],
        "rerank_error": "; ".join(meta["rerank_errors"]) if meta["rerank_errors"] else None,
        "retrieval_mode": meta["retrieval_mode"],
        "candidate_k": meta["candidate_k"],
        "leaf_retrieve_level": meta["leaf_retrieve_level"],
        "auto_merge_enabled": meta["auto_merge_enabled"],
        "auto_merge_applied": meta["auto_merge_applied"],
        "auto_merge_threshold": meta["auto_merge_threshold"],
        "auto_merge_replaced_chunks": meta["auto_merge_replaced_chunks"],
        "auto_merge_steps": meta["auto_merge_steps"],
    })
    return {"docs": deduped, "context": format_docs(deduped), "rag_trace": rag_trace}
