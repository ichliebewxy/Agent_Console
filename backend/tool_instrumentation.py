"""Tool wrappers for streaming user-visible execution steps."""
import json
import hashlib
from uuid import uuid4

from langchain_core.tools import StructuredTool

from agent_state import consume_tool_call_budget, record_tool_event
from event_stream import emit_tool_step
from runtime_context import current_runtime_context
from settings import AGENT_TOOL_CALL_LIMIT
from workspace_transaction import load_tool_receipt, save_tool_receipt


_REPLAY_SAFE_TOOLS = {
    "read_file",
    "glob",
    "review",
    "search_knowledge_base",
    "load_subagent",
    "load_skill",
    "read_skill_resource",
}


def _compact_json(value, max_length: int = 520) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}...（已截断）"


def _tool_step(
    phase: str,
    tool_name: str,
    call_id: str,
    args=None,
    result=None,
    operation_key: str | None = None,
    replayed: bool = False,
) -> dict:
    labels = {
        "start": f"调用工具：{tool_name}",
        "result": f"工具返回：{tool_name}",
        "error": f"工具错误：{tool_name}",
        "limit": f"工具调用已达上限：{tool_name}",
    }
    icons = {"start": ">", "result": "OK", "error": "!", "limit": "!"}
    step = {
        "icon": icons.get(phase, "•"),
        "phase": phase,
        "tool_name": tool_name,
        "call_id": call_id,
        "label": labels.get(phase, tool_name),
        "detail": f"参数：{_compact_json(args, 260)}" if args else "",
    }
    if result is not None:
        step["result"] = _compact_json(result, 900)
    if operation_key:
        step["operation_key"] = operation_key
    if replayed:
        step["replayed"] = True
    return step


def _emit(step: dict) -> None:
    record_tool_event(step)
    emit_tool_step(step)


def _operation_key(tool_name: str, index: int, args: dict) -> str | None:
    try:
        context = current_runtime_context()
    except RuntimeError:
        return None
    if not context.run_id or not context.step_id:
        return None
    payload = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{context.run_id}:{context.step_id}:{index}:{tool_name}:{digest}"


def _receipt_target(operation_key: str | None):
    if not operation_key:
        return None
    context = current_runtime_context()
    return (
        context.user_id,
        context.session_id,
        context.run_id,
        context.step_id,
        operation_key,
    )


def _load_receipt(target):
    return load_tool_receipt(*target) if target else None


def _save_receipt(target, value: dict) -> None:
    if target:
        save_tool_receipt(*target, value)


def _replay_or_unknown(tool_name: str, call_id: str, kwargs: dict, operation_key: str | None):
    target = _receipt_target(operation_key)
    receipt = _load_receipt(target)
    if receipt and receipt.get("status") == "completed":
        result = receipt.get("result")
        _emit(
            _tool_step(
                "result",
                tool_name,
                call_id,
                args=kwargs,
                result=result,
                operation_key=operation_key,
                replayed=True,
            )
        )
        return True, result, target
    if (
        receipt
        and receipt.get("status") == "started"
        and tool_name not in _REPLAY_SAFE_TOOLS
    ):
        result = (
            "UNKNOWN_EFFECT: 上次执行在产生工具回执前中断；"
            "为避免重复副作用，需要人工确认后再继续。"
        )
        _emit(
            _tool_step(
                "error",
                tool_name,
                call_id,
                args=kwargs,
                result=result,
                operation_key=operation_key,
            )
        )
        return True, result, target
    _save_receipt(
        target,
        {
            "status": "started",
            "tool_name": tool_name,
            "args": kwargs,
        },
    )
    return False, None, target


def _result_phase(result) -> str:
    error_prefixes = (
        "TOOL_ERROR:",
        "OPENCLI_ERROR:",
        "SPECIALIST_ERROR:",
        "SKILL_ERROR:",
        "WORKSPACE_ERROR:",
        "LOCAL_RUNTIME_ERROR:",
        "PERMISSION_DENIED:",
    )
    if isinstance(result, str) and result.startswith(error_prefixes):
        return "error"
    return "result"


def instrument_tool(tool_obj):
    async def wrapped_ainvoke(**kwargs):
        call_id = uuid4().hex
        allowed, call_index = consume_tool_call_budget()
        operation_key = _operation_key(tool_obj.name, call_index, kwargs)
        if not allowed:
            _emit(
                _tool_step(
                    "limit",
                    tool_obj.name,
                    call_id,
                    args=kwargs,
                    result=f"本轮工具调用已达到 {AGENT_TOOL_CALL_LIMIT} 次上限",
                    operation_key=operation_key,
                )
            )
            return f"TOOL_CALL_LIMIT_REACHED: 本轮工具调用已达到 {AGENT_TOOL_CALL_LIMIT} 次上限，请直接整理已有结果并回答。"
        handled, cached, receipt_target = _replay_or_unknown(
            tool_obj.name, call_id, kwargs, operation_key
        )
        if handled:
            return cached
        _emit(_tool_step("start", tool_obj.name, call_id, args=kwargs, operation_key=operation_key))
        try:
            result = await tool_obj.ainvoke(kwargs)
        except Exception as exc:
            _save_receipt(receipt_target, {"status": "error", "error": str(exc)})
            _emit(
                _tool_step(
                    "error",
                    tool_obj.name,
                    call_id,
                    args=kwargs,
                    result=str(exc),
                    operation_key=operation_key,
                )
            )
            raise
        phase = _result_phase(result)
        _save_receipt(
            receipt_target,
            {"status": "completed" if phase == "result" else "error", "result": result},
        )
        _emit(
            _tool_step(
                phase,
                tool_obj.name,
                call_id,
                args=kwargs,
                result=result,
                operation_key=operation_key,
            )
        )
        return result

    def wrapped_invoke(**kwargs):
        call_id = uuid4().hex
        allowed, call_index = consume_tool_call_budget()
        operation_key = _operation_key(tool_obj.name, call_index, kwargs)
        if not allowed:
            _emit(
                _tool_step(
                    "limit",
                    tool_obj.name,
                    call_id,
                    args=kwargs,
                    result=f"本轮工具调用已达到 {AGENT_TOOL_CALL_LIMIT} 次上限",
                    operation_key=operation_key,
                )
            )
            return f"TOOL_CALL_LIMIT_REACHED: 本轮工具调用已达到 {AGENT_TOOL_CALL_LIMIT} 次上限，请直接整理已有结果并回答。"
        handled, cached, receipt_target = _replay_or_unknown(
            tool_obj.name, call_id, kwargs, operation_key
        )
        if handled:
            return cached
        _emit(_tool_step("start", tool_obj.name, call_id, args=kwargs, operation_key=operation_key))
        try:
            result = tool_obj.invoke(kwargs)
        except Exception as exc:
            _save_receipt(receipt_target, {"status": "error", "error": str(exc)})
            _emit(
                _tool_step(
                    "error",
                    tool_obj.name,
                    call_id,
                    args=kwargs,
                    result=str(exc),
                    operation_key=operation_key,
                )
            )
            raise
        phase = _result_phase(result)
        _save_receipt(
            receipt_target,
            {"status": "completed" if phase == "result" else "error", "result": result},
        )
        _emit(
            _tool_step(
                phase,
                tool_obj.name,
                call_id,
                args=kwargs,
                result=result,
                operation_key=operation_key,
            )
        )
        return result

    return StructuredTool.from_function(
        func=wrapped_invoke,
        coroutine=wrapped_ainvoke,
        name=tool_obj.name,
        description=tool_obj.description,
        return_direct=getattr(tool_obj, "return_direct", False),
        args_schema=getattr(tool_obj, "args_schema", None),
        infer_schema=getattr(tool_obj, "args_schema", None) is None,
        response_format=getattr(tool_obj, "response_format", "content"),
        tags=getattr(tool_obj, "tags", None),
        metadata=getattr(tool_obj, "metadata", None),
        handle_tool_error=getattr(tool_obj, "handle_tool_error", False),
        handle_validation_error=getattr(tool_obj, "handle_validation_error", False),
    )


def instrument_tools(tools: list) -> list:
    return [instrument_tool(tool_obj) for tool_obj in tools]
