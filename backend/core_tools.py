"""The fixed LangChain tool surface for the main coding agent.

The surface mirrors the five tools from ``s02_tool_use`` while keeping all file
operations inside the current session workspace.  MCP tools are intentionally
not declared here: they are discovered at startup from ``mcp_servers.json``.
"""

from __future__ import annotations

import asyncio
import glob as glob_module
import json
import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

from bash_tool import bash
from bash_tool import review_bash_command
from runtime_context import current_runtime_context, session_async_lock, session_files_dir
from settings import WORKSPACE_FILE_MAX_CHARS


def _safe_path(relative_path: str, root: Path | None = None) -> Path:
    workspace = (root or session_files_dir(create=True)).resolve()
    target = (workspace / relative_path).resolve()
    if not target.is_relative_to(workspace):
        raise ValueError("Path escapes the current session workspace.")
    return target


def _workspace() -> Path:
    return session_files_dir(create=True).resolve()


def _read(path: str, limit: int | None, workspace: Path) -> str:
    try:
        target = _safe_path(path, workspace)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(WORKSPACE_FILE_MAX_CHARS + 1)
        if limit is not None and limit >= 0:
            lines = text.splitlines()
            if len(lines) > limit:
                text = "\n".join(lines[:limit]) + f"\n... ({len(lines) - limit} more lines)"
        if len(text) > WORKSPACE_FILE_MAX_CHARS:
            return f"{text[:WORKSPACE_FILE_MAX_CHARS]}\n\n...[truncated]"
        return text
    except FileNotFoundError:
        return f"TOOL_ERROR: File not found: {path}"
    except (OSError, ValueError) as exc:
        return f"TOOL_ERROR: {exc}"


@tool("read_file")
async def read_file(path: str, limit: int | None = None) -> str:
    """Read a UTF-8 text file from the current session workspace."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        return await asyncio.to_thread(_read, path, limit, _workspace())


def _write(path: str, content: str, workspace: Path) -> str:
    try:
        if len(content) > WORKSPACE_FILE_MAX_CHARS:
            return f"TOOL_ERROR: Content exceeds {WORKSPACE_FILE_MAX_CHARS} characters."
        target = _safe_path(path, workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        return f"Wrote {len(content)} characters to {Path(path).as_posix()}"
    except (OSError, ValueError) as exc:
        return f"TOOL_ERROR: {exc}"


@tool("write_file")
async def write_file(path: str, content: str) -> str:
    """Write UTF-8 content to a file in the current session workspace."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        return await asyncio.to_thread(_write, path, content, _workspace())


def _edit(path: str, old_text: str, new_text: str, workspace: Path) -> str:
    try:
        target = _safe_path(path, workspace)
        text = target.read_text(encoding="utf-8", errors="replace")
        if old_text not in text:
            return f"TOOL_ERROR: Text not found in {path}"
        target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {Path(path).as_posix()} once"
    except (OSError, ValueError) as exc:
        return f"TOOL_ERROR: {exc}"


@tool("edit_file")
async def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace the first exact occurrence of old_text in a session file."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        return await asyncio.to_thread(_edit, path, old_text, new_text, _workspace())


def _glob(pattern: str, workspace: Path) -> str:
    try:
        matches = []
        for value in glob_module.glob(pattern, root_dir=workspace, recursive=True):
            target = _safe_path(value, workspace)
            if target.is_file():
                matches.append(Path(value).as_posix())
        matches = sorted(set(matches))
        return "\n".join(matches[:200]) if matches else "(no matches)"
    except (OSError, ValueError) as exc:
        return f"TOOL_ERROR: {exc}"


@tool("glob")
async def glob(pattern: str) -> str:
    """Find files by a relative glob pattern in the current session workspace."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        return await asyncio.to_thread(_glob, pattern, _workspace())


@tool("review")
def review(
    command: str,
    user_authorized_side_effect: bool = False,
    opencli_access: Literal["unknown", "read", "write", "p4"] = "unknown",
) -> str:
    """Review a shell command without executing it and return the policy decision."""
    decision = review_bash_command(
        command,
        user_authorized_side_effect=user_authorized_side_effect,
        opencli_access=opencli_access,
    )
    return json.dumps(
        {
            "behavior": decision.behavior,
            "rule_id": decision.rule_id,
            "reason": decision.reason,
            "command": command,
        },
        ensure_ascii=False,
    )


FILE_TOOLS = [read_file, write_file, edit_file, glob]
CORE_TOOLS = [bash, *FILE_TOOLS]
REVIEW_TOOLS = [review]
# Keep the s02-style name available for callers that want the fixed five-tool
# dispatch table without any dynamically discovered MCP entries.
TOOLS = CORE_TOOLS
TOOL_HANDLERS = {item.name: item for item in TOOLS}
