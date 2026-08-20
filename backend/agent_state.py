"""Per-turn mutable state shared across the Agent, tools, instrumentation.

Keeping the tool-call budget and the latest RAG trace here decouples the search
tool, the tool wrappers, and the chat runner: they all read one budget and one
trace capture without importing each other.
"""

from contextvars import ContextVar
from typing import Optional

from settings import AGENT_TOOL_CALL_LIMIT

_LAST_RAG_CONTEXT: Optional[dict] = None
_TOOL_CALL_STATE: ContextVar[dict | None] = ContextVar("agent_tool_call_state", default=None)


def set_last_rag_context(context: dict) -> None:
    global _LAST_RAG_CONTEXT
    _LAST_RAG_CONTEXT = context


def get_last_rag_context(clear: bool = True) -> Optional[dict]:
    global _LAST_RAG_CONTEXT
    context = _LAST_RAG_CONTEXT
    if clear:
        _LAST_RAG_CONTEXT = None
    return context


def reset_tool_call_guards() -> None:
    _TOOL_CALL_STATE.set({"count": 0, "knowledge_count": 0})


def current_tool_call_state() -> dict:
    state = _TOOL_CALL_STATE.get()
    if state is None:
        state = {"count": 0, "knowledge_count": 0}
        _TOOL_CALL_STATE.set(state)
    return state


def consume_tool_call_budget() -> tuple[bool, int]:
    """Reserve one tool call for the current user turn."""
    state = current_tool_call_state()
    count = int(state.get("count", 0))
    if count >= AGENT_TOOL_CALL_LIMIT:
        return False, count
    count += 1
    state["count"] = count
    return True, count
