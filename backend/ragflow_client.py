"""Optional RAGFlow retrieval adapter."""
import json
from typing import Any, Dict, List, Tuple

import requests

from ops_store import record_tool_failure
from settings import RAGFLOW_API_KEY, RAGFLOW_BASE_URL, RAGFLOW_DATASET_IDS, RAGFLOW_ENABLED, RAGFLOW_TOP_K


def ragflow_meta(error: str | None = None, applied: bool = False) -> Dict[str, Any]:
    return {
        "ragflow_enabled": RAGFLOW_ENABLED,
        "ragflow_applied": applied,
        "ragflow_endpoint": f"{RAGFLOW_BASE_URL}/api/v1/retrieval" if RAGFLOW_BASE_URL else "",
        "ragflow_dataset_ids": RAGFLOW_DATASET_IDS,
        "ragflow_error": error,
    }


def _normalize_chunks(payload: Any) -> List[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    chunks = data.get("chunks") or data.get("documents") or data.get("doc_aggs") or [] if isinstance(data, dict) else data
    if not isinstance(chunks, list):
        return []

    normalized = []
    for idx, item in enumerate(chunks, 1):
        if not isinstance(item, dict):
            continue
        document = item.get("document") if isinstance(item.get("document"), dict) else {}
        text = item.get("content") or item.get("text") or item.get("chunk_content") or document.get("content") or ""
        filename = item.get("document_name") or item.get("filename") or item.get("name") or document.get("name") or "RAGFlow"
        normalized.append({
            "text": text,
            "filename": filename,
            "file_type": item.get("file_type") or "ragflow",
            "page_number": item.get("page_number") or item.get("page") or 0,
            "chunk_id": item.get("id") or item.get("chunk_id") or f"ragflow_{idx}",
            "parent_chunk_id": "",
            "root_chunk_id": "",
            "chunk_level": 3,
            "chunk_idx": idx,
            "score": item.get("similarity") or item.get("score") or item.get("vector_similarity") or 0.0,
            "retrieval_source": "ragflow",
        })
    return normalized


def retrieve_from_ragflow(query: str, top_k: int) -> Tuple[List[dict], Dict[str, Any]]:
    if not RAGFLOW_ENABLED:
        return [], ragflow_meta()
    if not RAGFLOW_BASE_URL or not RAGFLOW_API_KEY or not RAGFLOW_DATASET_IDS:
        error = "ragflow_not_configured"
        record_tool_failure("ragflow_retrieval", error, {"query": query}, "Skipped RAGFlow; missing env config.")
        return [], ragflow_meta(error=error)

    endpoint = f"{RAGFLOW_BASE_URL}/api/v1/retrieval"
    payload = {
        "question": query,
        "query": query,
        "dataset_ids": RAGFLOW_DATASET_IDS,
        "top_k": min(RAGFLOW_TOP_K, top_k),
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {RAGFLOW_API_KEY}"}
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        if response.status_code >= 400:
            error = f"HTTP {response.status_code}: {response.text[:300]}"
            record_tool_failure("ragflow_retrieval", error, payload, "Falling back to local Milvus retrieval.")
            return [], ragflow_meta(error=error)
        chunks = _normalize_chunks(response.json())
        return chunks[:top_k], ragflow_meta(applied=bool(chunks))
    except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError) as exc:
        error = str(exc)
        record_tool_failure("ragflow_retrieval", error, payload, "Falling back to local Milvus retrieval.")
        return [], ragflow_meta(error=error)
