"""Constrained text-file tools for the skills agent workspace."""
import asyncio
import glob
import os
from pathlib import Path

from langchain_core.tools import tool

from runtime_context import current_runtime_context, session_async_lock, session_files_dir
from settings import WORKSPACE_FILE_MAX_CHARS


def _safe_path(relative_path: str, root: Path | None = None) -> Path:
    workspace = (root or session_files_dir(create=True)).resolve()
    target = (workspace / relative_path).resolve()
    if not target.is_relative_to(workspace):
        raise ValueError("Path escapes the current session workspace.")
    return target


def _list_workspace_files(pattern: str, workspace: Path) -> str:
    try:
        matches = []
        for relative in glob.glob(pattern, root_dir=workspace, recursive=True):
            target = _safe_path(relative, workspace)
            if target.is_file():
                matches.append(Path(relative).as_posix())
        matches = sorted(set(matches))
        if not matches:
            return "(no workspace files)"
        suffix = f"\n... ({len(matches) - 200} more)" if len(matches) > 200 else ""
        return "\n".join(matches[:200]) + suffix
    except (OSError, ValueError) as exc:
        return f"WORKSPACE_ERROR: {exc}"


@tool
async def list_workspace_files(pattern: str = "**/*") -> str:
    """List up to 200 files in the current backend/tmp session using a relative glob."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        workspace = session_files_dir(create=True)
        return await asyncio.to_thread(_list_workspace_files, pattern, workspace)


def _read_workspace_file(path: str, workspace: Path) -> str:
    handle = None
    try:
        target = _safe_path(path, workspace)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags)
        handle = os.fdopen(descriptor, "r", encoding="utf-8", errors="replace")
        text = handle.read(WORKSPACE_FILE_MAX_CHARS + 1)
        if len(text) > WORKSPACE_FILE_MAX_CHARS:
            return f"{text[:WORKSPACE_FILE_MAX_CHARS]}\n\n...[truncated]"
        return text
    except FileNotFoundError:
        return f"WORKSPACE_ERROR: File not found: {path}"
    except (OSError, ValueError) as exc:
        return f"WORKSPACE_ERROR: {exc}"
    finally:
        if handle is not None:
            handle.close()


@tool
async def read_workspace_file(path: str) -> str:
    """Read a UTF-8 text file from the current backend/tmp session by relative path."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        workspace = session_files_dir(create=True)
        return await asyncio.to_thread(_read_workspace_file, path, workspace)


def _write_workspace_file(
    path: str,
    content: str,
    overwrite: bool,
    workspace: Path,
) -> str:
    try:
        if len(content) > WORKSPACE_FILE_MAX_CHARS:
            return (
                "WORKSPACE_ERROR: Content exceeds the configured limit of "
                f"{WORKSPACE_FILE_MAX_CHARS} characters."
            )
        target = _safe_path(path, workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        flags |= os.O_TRUNC if overwrite else os.O_EXCL
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        return f"Wrote {len(content)} characters to {Path(path).as_posix()}"
    except FileExistsError:
        return f"WORKSPACE_ERROR: File exists; set overwrite=true to replace: {path}"
    except (OSError, ValueError) as exc:
        return f"WORKSPACE_ERROR: {exc}"


@tool
async def write_workspace_file(path: str, content: str, overwrite: bool = False) -> str:
    """Write a UTF-8 text artifact under the current backend/tmp session; overwrite must be explicit."""
    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        workspace = session_files_dir(create=True)
        return await asyncio.to_thread(
            _write_workspace_file,
            path,
            content,
            overwrite,
            workspace,
        )


WORKSPACE_TOOLS = [list_workspace_files, read_workspace_file, write_workspace_file]
