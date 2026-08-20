"""In-process event bus for streaming RAG and tool steps to the chat SSE loop.

The chat runner installs queues before invoking the Agent; RAG nodes and tool
instrumentation push lightweight step dicts into those queues, which the SSE
generator drains. Keeping this isolated lets the RAG graph and tool wrappers
emit progress without depending on the chat layer.
"""

import asyncio

_RAG_STEP_QUEUE = None
_RAG_STEP_LOOP = None
_TOOL_STEP_QUEUE = None
_TOOL_STEP_LOOP = None


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
