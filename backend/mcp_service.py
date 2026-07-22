"""Startup discovery and wrapping for MCP servers declared in config.json."""
import asyncio
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config_service import CONFIG_STORE
from ops_store import record_tool_failure
from settings import DASHSCOPE_MCP_API_KEY, MCP_DISCOVERY_TIMEOUT


@dataclass
class MCPDiscoveryResult:
    tools: list
    server_count: int
    tool_count: int
    errors: dict[str, str]


_DISCOVERY_LOCK = asyncio.Lock()
_DISCOVERED_TOOLS: list = []
_MCP_CLIENTS: list[MultiServerMCPClient] = []
_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


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
    return json.dumps(result, ensure_ascii=False, default=str)


def _expand_env(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return _ENV_PLACEHOLDER.sub(lambda match: os.getenv(match.group(1), ""), value)


def _adapter_config(name: str, server: dict) -> dict:
    transport = str(server.get("transport") or "streamable_http")
    if transport == "stdio":
        from bash_tool import review_bash_command

        command = str(server.get("command") or "").strip()
        args = [str(value) for value in server.get("args") or []]
        executable = os.path.basename(command).lower()
        executable = re.sub(r"\.(?:exe|cmd|bat)$", "", executable)
        lowered_args = [value.lower() for value in args]
        inline_code_flags = {
            "python": {"-c"},
            "python3": {"-c"},
            "py": {"-c"},
            "node": {"-e", "--eval", "-p", "--print"},
            "powershell": {"-command", "-encodedcommand", "-enc"},
            "pwsh": {"-command", "-encodedcommand", "-enc"},
            "cmd": {"/c", "/k"},
            "bash": {"-c"},
            "sh": {"-c"},
        }
        if set(lowered_args) & inline_code_flags.get(executable, set()):
            raise PermissionError("stdio MCP cannot execute inline interpreter code")
        if executable == "npx" and "--no-install" not in lowered_args:
            raise PermissionError(
                "stdio MCP npx commands require --no-install; install a trusted server first"
            )
        if executable == "npm" and any(
            value in {"install", "i", "exec"} for value in lowered_args
        ):
            raise PermissionError(
                "stdio MCP cannot install or remotely execute packages; install a trusted server first"
            )
        command_line = subprocess.list2cmdline([command, *args])
        decision = review_bash_command(command_line)
        if decision.behavior != "allow":
            raise PermissionError(
                f"stdio MCP command rejected by {decision.rule_id}: {decision.reason}"
            )
        config = {
            "transport": "stdio",
            "command": command,
            "args": args,
        }
        if isinstance(server.get("env"), dict):
            config["env"] = {
                key: str(_expand_env(value)) for key, value in server["env"].items()
            }
        return config

    headers = {
        key: str(_expand_env(value))
        for key, value in (server.get("headers") or {}).items()
    }
    url = str(server.get("url") or "")
    if "dashscope.aliyuncs.com" in url and DASHSCOPE_MCP_API_KEY:
        headers.setdefault("Authorization", f"Bearer {DASHSCOPE_MCP_API_KEY}")
    return {
        "transport": transport,
        "url": url,
        "headers": headers,
    }


def _tool_schema(tool) -> dict:
    schema = getattr(tool, "args_schema", None)
    if schema is None:
        return {}
    if isinstance(schema, dict):
        return schema
    try:
        return schema.model_json_schema()
    except (AttributeError, TypeError):
        return {}


def _runtime_tool_name(server_name: str, tool_name: str, used_names: set[str]) -> str:
    safe_server = re.sub(r"[^a-zA-Z0-9_-]", "_", server_name)
    safe_tool = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)
    raw_name = f"mcp_{safe_server}_{safe_tool}"
    runtime_name = raw_name
    if len(runtime_name) > 120 or runtime_name in used_names:
        digest = hashlib.sha256(
            f"{server_name}\x00{tool_name}".encode("utf-8")
        ).hexdigest()[:8]
        runtime_name = f"{raw_name[:111]}_{digest}"
    counter = 2
    candidate = runtime_name
    while candidate in used_names:
        suffix = f"_{counter}"
        candidate = f"{runtime_name[:120 - len(suffix)]}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


def _wrap_tool(tool, server_name: str, used_names: set[str]):
    runtime_name = _runtime_tool_name(server_name, tool.name, used_names)

    async def wrapped_ainvoke(**kwargs):
        try:
            result = await tool.ainvoke(kwargs)
            return stringify_tool_result(result)
        except Exception as exc:
            error = summarize_exception(exc)
            record_tool_failure(
                runtime_name,
                error,
                kwargs,
                "Returned an MCP tool error summary to the main Agent.",
            )
            return (
                f"TOOL_ERROR: {runtime_name} failed with: {error}. "
                "Do not retry the same tool with the same arguments."
            )

    return StructuredTool.from_function(
        coroutine=wrapped_ainvoke,
        name=runtime_name,
        description=f"[{server_name}] {tool.description or tool.name}",
        args_schema=tool.args_schema,
    )


async def discover_configured_mcp_tools(
    *,
    record_init_failure: bool = True,
) -> MCPDiscoveryResult:
    """Discover every enabled server and persist the tool catalog to config.json."""
    global _DISCOVERED_TOOLS, _MCP_CLIENTS
    async with _DISCOVERY_LOCK:
        configured = CONFIG_STORE.snapshot().get("mcpServers", {})
        discovered_tools = []
        clients = []
        errors = {}
        metadata = {}
        enabled_count = 0
        used_names: set[str] = set()

        for name, server in configured.items():
            if not server.get("enabled", True):
                metadata[name] = {"tools": [], "error": "disabled"}
                continue
            enabled_count += 1
            try:
                client = MultiServerMCPClient({name: _adapter_config(name, server)})
                raw_tools = await asyncio.wait_for(
                    client.get_tools(),
                    timeout=max(1, MCP_DISCOVERY_TIMEOUT),
                )
                clients.append(client)
                rows = []
                for raw_tool in raw_tools:
                    wrapped = _wrap_tool(raw_tool, name, used_names)
                    discovered_tools.append(wrapped)
                    rows.append(
                        {
                            "name": raw_tool.name,
                            "runtime_name": wrapped.name,
                            "description": str(raw_tool.description or "")[:1200],
                            "input_schema": _tool_schema(raw_tool),
                        }
                    )
                metadata[name] = {"tools": rows, "error": ""}
            except Exception as exc:
                error = summarize_exception(exc)
                errors[name] = error
                metadata[name] = {"tools": [], "error": error}
                if record_init_failure:
                    record_tool_failure(
                        f"mcp_init:{name}",
                        error,
                        {"server": name},
                        "MCP server remains visible in config with its discovery error.",
                        dedupe=True,
                    )

        CONFIG_STORE.update_mcp_discovery(metadata)
        _DISCOVERED_TOOLS = discovered_tools
        _MCP_CLIENTS = clients
        return MCPDiscoveryResult(
            tools=list(discovered_tools),
            server_count=enabled_count,
            tool_count=len(discovered_tools),
            errors=errors,
        )


def get_discovered_mcp_tools() -> list:
    return list(_DISCOVERED_TOOLS)
