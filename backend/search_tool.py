"""Knowledge-base retrieval tool exposed to the LangChain main Agent."""

from langchain_core.tools import tool

from agent_state import current_tool_call_state, set_last_rag_context
from ops_store import record_tool_failure


def _format_search_status(rag_trace: dict, docs_count: int) -> str:
    status = {
        "tool": rag_trace.get("tool_name", "search_knowledge_base"),
        "query": rag_trace.get("query"),
        "retrieval_stage": rag_trace.get("retrieval_stage"),
        "retrieval_mode": rag_trace.get("retrieval_mode"),
        "retrieved_chunks": docs_count,
        "candidate_k": rag_trace.get("candidate_k"),
        "candidate_count": rag_trace.get("candidate_count"),
        "leaf_retrieve_level": rag_trace.get("leaf_retrieve_level"),
        "auto_merge_enabled": rag_trace.get("auto_merge_enabled"),
        "auto_merge_applied": rag_trace.get("auto_merge_applied"),
        "auto_merge_replaced_chunks": rag_trace.get("auto_merge_replaced_chunks"),
        "rerank_enabled": rag_trace.get("rerank_enabled"),
        "rerank_applied": rag_trace.get("rerank_applied"),
        "rerank_model": rag_trace.get("rerank_model"),
        "rerank_endpoint": rag_trace.get("rerank_endpoint"),
        "rerank_error": rag_trace.get("rerank_error"),
        "grade_model": rag_trace.get("grade_model"),
        "grade_score": rag_trace.get("grade_score"),
        "grade_route": rag_trace.get("grade_route"),
        "grade_error": rag_trace.get("grade_error"),
    }
    lines = ["Search Status:"]
    for key, value in status.items():
        if value is not None and value != "":
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


@tool("search_knowledge_base")
def search_knowledge_base(query: str) -> str:
    """Search for information in the knowledge base using hybrid retrieval."""
    state = current_tool_call_state()
    if int(state.get("knowledge_count", 0)) >= 1:
        return (
            "TOOL_CALL_LIMIT_REACHED: search_knowledge_base has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )
    state["knowledge_count"] = 1

    from rag_pipeline import run_rag_graph

    try:
        rag_result = run_rag_graph(query)
    except Exception as e:
        fallback = "知识库检索失败，已写入服务端日志；请根据已有上下文谨慎回答，并说明检索不可用。"
        record_tool_failure("search_knowledge_base", str(e), {"query": query}, fallback)
        return fallback

    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}
    if rag_trace:
        set_last_rag_context({"rag_trace": rag_trace})

    status_text = _format_search_status(rag_trace, len(docs))
    if not docs:
        return f"{status_text}\n\nNo relevant documents found in the knowledge base."

    formatted = []
    for i, result in enumerate(docs, 1):
        source = result.get("filename", "Unknown")
        page = result.get("page_number", "N/A")
        text = result.get("text", "")
        retrieval_source = result.get("retrieval_source", "local")
        formatted.append(f"[{i}] {source} (Page {page}, Source {retrieval_source}):\n{text}")

    return f"{status_text}\n\nRetrieved Chunks:\n" + "\n\n---\n\n".join(formatted)
