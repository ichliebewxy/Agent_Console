"""DashScope MCP tool loading and wrapping."""
import json
import re
from dataclasses import dataclass

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ops_store import record_tool_failure, tool_failure_store
from settings import AMAP_MCP_ENDPOINT, DASHSCOPE_MCP_API_KEY


@dataclass
class MCPInitResult:
    client: MultiServerMCPClient
    tools: list
    tool_count: int
    error: str = ""


def summarize_exception(exc: BaseException) -> str:
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        return "; ".join(f"{type(sub).__name__}: {sub}" for sub in sub_exceptions)
    return f"{type(exc).__name__}: {exc}"


def stringify_tool_result(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        texts = [
            item["text"]
            for item in result
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
        ]
        if texts:
            return "\n".join(texts)
    return json.dumps(result, ensure_ascii=False)


def _create_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "amap-maps": {
                "transport": "streamable_http",
                "url": AMAP_MCP_ENDPOINT,
                "headers": {"Authorization": f"Bearer {DASHSCOPE_MCP_API_KEY}"},
            }
        }
    )


def _wrap_tool(tool):
    new_name = re.sub(r"[^a-zA-Z0-9_-]", "_", tool.name)

    async def wrapped_ainvoke(**kwargs):
        try:
            result = await tool.ainvoke(kwargs)
            return stringify_tool_result(result)
        except Exception as exc:
            error = str(exc)
            record_tool_failure(
                tool.name,
                error,
                kwargs,
                "Returned a tool error summary to the model.",
            )
            return (
                f"TOOL_ERROR: {tool.name} failed with: {error}. "
                "Do not retry the same tool with the same arguments."
            )

    return StructuredTool.from_function(
        coroutine=wrapped_ainvoke,
        name=new_name,
        description=tool.description,
        args_schema=tool.args_schema,
    )


async def load_mcp_tools(record_init_failure: bool = True) -> MCPInitResult:
    client = _create_client()
    try:
        raw_tools = await client.get_tools()
    except Exception as exc:
        error = summarize_exception(exc)
        if record_init_failure:
            record_tool_failure(
                "amap_mcp_init",
                error,
                {"endpoint": AMAP_MCP_ENDPOINT},
                "Continue startup with local tools only.",
                dedupe=True,
            )
        return MCPInitResult(client=client, tools=[], tool_count=0, error=error)

    wrapped_tools = [_wrap_tool(tool) for tool in raw_tools]#对工具名字进行清洗
    if wrapped_tools:
        tool_failure_store.resolve_open_matching(
            {"tool_name": "amap_mcp_init"},
            f"MCP 初始化成功，已加载 {len(wrapped_tools)} 个工具。",
        )
    return MCPInitResult(client=client, tools=wrapped_tools, tool_count=len(wrapped_tools))
