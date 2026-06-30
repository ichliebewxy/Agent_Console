"""Tool wrappers for streaming user-visible execution steps."""
import json
from uuid import uuid4

from langchain_core.tools import StructuredTool

from tools import emit_tool_step


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


def _tool_step(phase: str, tool_name: str, call_id: str, args=None, result=None) -> dict:
    labels = {
        "start": f"调用工具：{tool_name}",
        "result": f"工具返回：{tool_name}",
        "error": f"工具错误：{tool_name}",
    }
    icons = {"start": ">", "result": "OK", "error": "!"}
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
    return step


def _result_phase(result) -> str:
    if isinstance(result, str) and result.startswith("TOOL_ERROR:"):
        return "error"
    return "result"


def instrument_tool(tool_obj):
    async def wrapped_ainvoke(**kwargs):
        call_id = uuid4().hex
        emit_tool_step(_tool_step("start", tool_obj.name, call_id, args=kwargs))
        try:
            result = await tool_obj.ainvoke(kwargs)
        except Exception as exc:
            emit_tool_step(
                _tool_step("error", tool_obj.name, call_id, args=kwargs, result=str(exc))
            )
            raise
        emit_tool_step(
            _tool_step(_result_phase(result), tool_obj.name, call_id, args=kwargs, result=result)
        )
        return result

    def wrapped_invoke(**kwargs):
        call_id = uuid4().hex
        emit_tool_step(_tool_step("start", tool_obj.name, call_id, args=kwargs))
        try:
            result = tool_obj.invoke(kwargs)
        except Exception as exc:
            emit_tool_step(
                _tool_step("error", tool_obj.name, call_id, args=kwargs, result=str(exc))
            )
            raise
        emit_tool_step(
            _tool_step(_result_phase(result), tool_obj.name, call_id, args=kwargs, result=result)
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
