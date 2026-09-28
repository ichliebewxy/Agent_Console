"""Per-turn mutable state shared across the Agent, tools, instrumentation.

Keeping the tool-call budget and the latest RAG trace here decouples the search
tool, the tool wrappers, and the chat runner: they all read one budget and one
trace capture without importing each other.
"""

import copy
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from settings import AGENT_TOOL_CALL_LIMIT


class RagTraceCapture:
    """A per-turn sink shared by copied task and worker-thread contexts."""

    def __init__(self):
        self._lock = threading.Lock()
        self._traces: dict[str, dict] = {}

    def record(self, trace: dict, call_id: str | None) -> None:
        with self._lock:
            self._traces[call_id or uuid4().hex] = copy.deepcopy(trace)

    def snapshot(self) -> dict | None:
        with self._lock:
            calls = list(self._traces.items())
        if not calls:
            return None
        call_id, latest = calls[-1]
        result = {**latest, "tool_call_id": call_id}
        if len(calls) > 1:
            result["tool_calls"] = [
                {"tool_call_id": item_id, "rag_trace": item_trace}
                for item_id, item_trace in calls
            ]
        return {"rag_trace": result}


_RAG_CAPTURE: ContextVar[RagTraceCapture | None] = ContextVar(
    "agent_rag_trace_capture", default=None
)
_TOOL_CALL_ID: ContextVar[str | None] = ContextVar("agent_tool_call_id", default=None)
_TOOL_CALL_STATE: ContextVar[dict | None] = ContextVar("agent_tool_call_state", default=None)
_TOOL_EVENT_LOG: ContextVar[list[dict] | None] = ContextVar(
    "agent_tool_event_log",
    default=None,
)


def begin_rag_trace_capture() -> None:
    _RAG_CAPTURE.set(RagTraceCapture())


@contextmanager
def bind_tool_call_id(call_id: str):
    token = _TOOL_CALL_ID.set(call_id)
    try:
        yield
    finally:
        _TOOL_CALL_ID.reset(token)


def record_rag_trace(trace: dict) -> None:
    capture = _RAG_CAPTURE.get()
    if capture is None:
        capture = RagTraceCapture()
        _RAG_CAPTURE.set(capture)
    capture.record(trace, _TOOL_CALL_ID.get())


def get_last_rag_context(clear: bool = True) -> dict | None:
    capture = _RAG_CAPTURE.get()
    context = capture.snapshot() if capture else None
    if clear:
        _RAG_CAPTURE.set(None)
    return context


def merge_rag_traces(previous: dict | None, current: dict | None) -> dict | None:
    if not current:
        return previous
    if not previous:
        return current
    calls = []
    seen = set()
    for trace in (previous, current):
        entries = trace.get("tool_calls") or [
            {"tool_call_id": trace.get("tool_call_id"), "rag_trace": trace}
        ]
        for entry in entries:
            call_id = entry.get("tool_call_id")
            if call_id is None or call_id not in seen:
                calls.append(entry)
                if call_id is not None:
                    seen.add(call_id)
    return {**current, "tool_calls": calls}


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
