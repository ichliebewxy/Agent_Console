"""In-process event bus for streaming RAG and tool steps to the chat SSE loop.

The chat runner installs queues before invoking the Agent; RAG nodes and tool
instrumentation push lightweight step dicts into those queues, which the SSE
generator drains. Keeping this isolated lets the RAG graph and tool wrappers
emit progress without depending on the chat layer.
"""

import asyncio
from contextvars import ContextVar

_RAG_STEP_TARGET: ContextVar[tuple | None] = ContextVar("rag_step_target", default=None)
_TOOL_STEP_TARGET: ContextVar[tuple | None] = ContextVar("tool_step_target", default=None)


def set_rag_step_queue(queue):
    if queue:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        _RAG_STEP_TARGET.set((queue, loop))
    else:
        _RAG_STEP_TARGET.set(None)


def emit_rag_step(icon: str, label: str, detail: str = ""):
    target = _RAG_STEP_TARGET.get()
    if target is None:
        return
    queue, loop = target
    step = {"icon": icon, "label": label, "detail": detail}
    try:
        if not loop.is_closed():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is loop:
                queue.put_nowait(step)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, step)
    except Exception:
        pass


def set_tool_step_queue(queue):
    if queue:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        _TOOL_STEP_TARGET.set((queue, loop))
    else:
        _TOOL_STEP_TARGET.set(None)


def emit_tool_step(step: dict):
    target = _TOOL_STEP_TARGET.get()
    if target is None:
        return
    queue, loop = target
    try:
        if not loop.is_closed():
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is loop:
                queue.put_nowait(step)
            else:
                loop.call_soon_threadsafe(queue.put_nowait, step)
    except Exception:
        pass
