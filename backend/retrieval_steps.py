"""Post-processing steps for local RAG retrieval."""
from collections import defaultdict
from typing import Any, Dict, List, Tuple
import json

import requests

from parent_chunk_store import ParentChunkStore
from settings import AUTO_MERGE_ENABLED, AUTO_MERGE_THRESHOLD, RERANK_API_KEY, RERANK_BINDING_HOST, RERANK_MODEL

_parent_chunk_store = ParentChunkStore()


def get_rerank_endpoint() -> str:
    if not RERANK_BINDING_HOST:
        return ""
    host = RERANK_BINDING_HOST.strip().rstrip("/")
    return host if host.endswith("/v1/rerank") else f"{host}/v1/rerank"


def merge_to_parent_level(docs: List[dict], threshold: int = 2) -> Tuple[List[dict], int]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for doc in docs:
        parent_id = (doc.get("parent_chunk_id") or "").strip()
        if parent_id:
            groups[parent_id].append(doc)

    merge_ids = [parent_id for parent_id, children in groups.items() if len(children) >= threshold]
    if not merge_ids:
        return docs, 0
    parent_docs = _parent_chunk_store.get_documents_by_ids(merge_ids)
    parent_map = {item.get("chunk_id", ""): item for item in parent_docs if item.get("chunk_id")}

    merged_docs = []
    merged_count = 0
    for doc in docs:
        parent_id = (doc.get("parent_chunk_id") or "").strip()
        if not parent_id or parent_id not in parent_map:
            merged_docs.append(doc)
            continue
        parent_doc = dict(parent_map[parent_id])
        score = doc.get("score")
        if score is not None:
            parent_doc["score"] = max(float(parent_doc.get("score", score)), float(score))
        parent_doc["merged_from_children"] = True
        parent_doc["merged_child_count"] = len(groups[parent_id])
        merged_docs.append(parent_doc)
        merged_count += 1
    return dedupe_retrieved_docs(merged_docs), merged_count


def auto_merge_documents(docs: List[dict], top_k: int) -> Tuple[List[dict], Dict[str, Any]]:
    meta = {
        "auto_merge_enabled": AUTO_MERGE_ENABLED,
        "auto_merge_applied": False,
        "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
        "auto_merge_replaced_chunks": 0,
        "auto_merge_steps": 0,
    }
    if not AUTO_MERGE_ENABLED or not docs:
        return docs[:top_k], meta

    merged_docs, l3_l2 = merge_to_parent_level(docs, threshold=AUTO_MERGE_THRESHOLD)
    merged_docs, l2_l1 = merge_to_parent_level(merged_docs, threshold=AUTO_MERGE_THRESHOLD)
    merged_docs.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    replaced_count = l3_l2 + l2_l1
    meta.update({
        "auto_merge_applied": replaced_count > 0,
        "auto_merge_replaced_chunks": replaced_count,
        "auto_merge_steps": int(l3_l2 > 0) + int(l2_l1 > 0),
    })
    return merged_docs[:top_k], meta


def rerank_documents(query: str, docs: List[dict], top_k: int) -> Tuple[List[dict], Dict[str, Any]]:
    docs_with_rank = [{**doc, "rrf_rank": i} for i, doc in enumerate(docs, 1)]
    meta: Dict[str, Any] = {
        "rerank_enabled": bool(RERANK_MODEL and RERANK_API_KEY and RERANK_BINDING_HOST),
        "rerank_applied": False,
        "rerank_model": RERANK_MODEL,
        "rerank_endpoint": get_rerank_endpoint(),
        "rerank_error": None,
        "candidate_count": len(docs_with_rank),
    }
    if not docs_with_rank or not meta["rerank_enabled"]:
        return docs_with_rank[:top_k], meta

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": [doc.get("text", "") for doc in docs_with_rank],
        "top_n": min(top_k, len(docs_with_rank)),
        "return_documents": False,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RERANK_API_KEY}"}
    try:
        meta["rerank_applied"] = True
        response = requests.post(meta["rerank_endpoint"], headers=headers, json=payload, timeout=15)
        if response.status_code >= 400:
            meta["rerank_error"] = f"HTTP {response.status_code}: {response.text}"
            return docs_with_rank[:top_k], meta
        reranked = []
        for item in response.json().get("results", []):
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < len(docs_with_rank):
                doc = dict(docs_with_rank[idx])
                if item.get("relevance_score") is not None:
                    doc["rerank_score"] = item.get("relevance_score")
                reranked.append(doc)
        if reranked:
            return reranked[:top_k], meta
        meta["rerank_error"] = "empty_rerank_results"
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        meta["rerank_error"] = str(exc)
    return docs_with_rank[:top_k], meta


def dedupe_retrieved_docs(docs: List[dict]) -> List[dict]:
    deduped = []
    seen = set()
    for item in docs:
        key = item.get("chunk_id") or (item.get("filename"), item.get("page_number"), item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    for idx, item in enumerate(deduped, 1):
        item["rrf_rank"] = idx
    return deduped
