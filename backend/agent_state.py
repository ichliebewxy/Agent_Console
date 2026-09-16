"""Per-turn mutable state shared across the Agent, tools, instrumentation.

Keeping the tool-call budget and the latest RAG trace here decouples the search
tool, the tool wrappers, and the chat runner: they all read one budget and one
trace capture without importing each other.
"""

from contextvars import ContextVar
from typing import Optional

from settings import AGENT_TOOL_CALL_LIMIT

_LAST_RAG_CONTEXT: ContextVar[Optional[dict]] = ContextVar(
    "agent_last_rag_context",
    default=None,
)
_TOOL_CALL_STATE: ContextVar[dict | None] = ContextVar("agent_tool_call_state", default=None)
_TOOL_EVENT_LOG: ContextVar[list[dict] | None] = ContextVar(
    "agent_tool_event_log",
    default=None,
)


def set_last_rag_context(context: dict) -> None:
    _LAST_RAG_CONTEXT.set(context)


def get_last_rag_context(clear: bool = True) -> Optional[dict]:
    context = _LAST_RAG_CONTEXT.get()
    if clear:
        _LAST_RAG_CONTEXT.set(None)
    return context


def reset_tool_call_guards() -> None:
    _TOOL_CALL_STATE.set({"count": 0, "knowledge_count": 0})
    _TOOL_EVENT_LOG.set([])


def record_tool_event(event: dict) -> None:
    events = _TOOL_EVENT_LOG.get()
    if events is None:
        events = []
        _TOOL_EVENT_LOG.set(events)
    events.append(dict(event))


def consume_tool_events() -> list[dict]:
    events = list(_TOOL_EVENT_LOG.get() or [])
    _TOOL_EVENT_LOG.set([])
    return events


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


_CONVERSATION_HISTORY: ContextVar[list | None] = ContextVar(
    "agent_conversation_history",
    default=None,
)


def set_conversation_history(history: list) -> None:
    """记住当前会话到目前为止的对话消息，供工作流的每一步执行器读取。

    工作流（plan-and-execute）把每个子任务作为独立的一次 agent 调用执行，
    若不显式携带这段历史，执行器就会丢失本轮之前确定的起点、目的地等上下文。
    """
    _CONVERSATION_HISTORY.set(history)


def get_conversation_history() -> list:
    return _CONVERSATION_HISTORY.get() or []
