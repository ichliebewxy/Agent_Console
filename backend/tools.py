import asyncio
from contextvars import ContextVar
from typing import Optional

from langchain_core.tools import tool

from ops_store import record_tool_failure
from settings import AGENT_TOOL_CALL_LIMIT

_LAST_RAG_CONTEXT = None
_TOOL_CALL_STATE: ContextVar[dict | None] = ContextVar("agent_tool_call_state", default=None)
_RAG_STEP_QUEUE = None
_RAG_STEP_LOOP = None
_TOOL_STEP_QUEUE = None
_TOOL_STEP_LOOP = None


def _set_last_rag_context(context: dict):
    global _LAST_RAG_CONTEXT
    _LAST_RAG_CONTEXT = context


def get_last_rag_context(clear: bool = True) -> Optional[dict]:
    global _LAST_RAG_CONTEXT
    context = _LAST_RAG_CONTEXT
    if clear:
        _LAST_RAG_CONTEXT = None
    return context


def reset_tool_call_guards():
    _TOOL_CALL_STATE.set({"count": 0, "knowledge_count": 0})


def _current_tool_call_state() -> dict:
    state = _TOOL_CALL_STATE.get()
    if state is None:
        state = {"count": 0, "knowledge_count": 0}
        _TOOL_CALL_STATE.set(state)
    return state


def consume_tool_call_budget() -> tuple[bool, int]:
    """Reserve one tool call for the current user turn."""
    state = _current_tool_call_state()
    count = int(state.get("count", 0))
    if count >= AGENT_TOOL_CALL_LIMIT:
        return False, count
    count += 1
    state["count"] = count
    return True, count


def set_rag_step_queue(queue):
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    _RAG_STEP_QUEUE = queue
    if queue:
        try:
            _RAG_STEP_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            _RAG_STEP_LOOP = asyncio.get_event_loop()
    else:
        _RAG_STEP_LOOP = None


def emit_rag_step(icon: str, label: str, detail: str = ""):
    global _RAG_STEP_QUEUE, _RAG_STEP_LOOP
    if _RAG_STEP_QUEUE is None or _RAG_STEP_LOOP is None:
        return
    step = {"icon": icon, "label": label, "detail": detail}
    try:
        if not _RAG_STEP_LOOP.is_closed():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is _RAG_STEP_LOOP:
                _RAG_STEP_QUEUE.put_nowait(step)
            else:
                _RAG_STEP_LOOP.call_soon_threadsafe(_RAG_STEP_QUEUE.put_nowait, step)
    except Exception:
        pass


def set_tool_step_queue(queue):
    global _TOOL_STEP_QUEUE, _TOOL_STEP_LOOP
    _TOOL_STEP_QUEUE = queue
    if queue:
        try:
            _TOOL_STEP_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            _TOOL_STEP_LOOP = asyncio.get_event_loop()
    else:
        _TOOL_STEP_LOOP = None


def emit_tool_step(step: dict):
    global _TOOL_STEP_QUEUE, _TOOL_STEP_LOOP
    if _TOOL_STEP_QUEUE is None or _TOOL_STEP_LOOP is None:
        return
    try:
        if not _TOOL_STEP_LOOP.is_closed():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is _TOOL_STEP_LOOP:
                _TOOL_STEP_QUEUE.put_nowait(step)
            else:
                _TOOL_STEP_LOOP.call_soon_threadsafe(_TOOL_STEP_QUEUE.put_nowait, step)
    except Exception:
        pass


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
    state = _current_tool_call_state()
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
        _set_last_rag_context({"rag_trace": rag_trace})

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


# s02-compatible export: the fixed local tool dispatch table is maintained in
# core_tools.py and deliberately excludes knowledge-base/MCP dynamic tools.
from core_tools import TOOLS  # noqa: E402  (late import avoids tool-module cycles)
