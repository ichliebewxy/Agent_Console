"""Local command execution rooted in each chat session's backend/tmp directory."""
import asyncio
import os
import signal
import subprocess
from pathlib import Path

from ops_store import record_tool_failure
from runtime_context import current_runtime_context, session_async_lock, session_files_dir
from settings import (
    LOCAL_RUN_COMMAND_MAX_CHARS,
    LOCAL_RUN_OUTPUT_MAX_CHARS,
    LOCAL_RUN_TIMEOUT,
)

_INTERNAL_DIRS = {".cache", ".npm-cache", ".pycache", "__pycache__"}


def _snapshot(root: Path, limit: int = 5000) -> dict[str, tuple[int, int]]:
    rows = {}
    stack = [root]
    while stack and len(rows) < limit:
        directory = stack.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            for entry in entries:
                if len(rows) >= limit:
                    break
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in _INTERNAL_DIRS:
                            continue
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        stat = entry.stat(follow_symlinks=False)
                        relative = Path(entry.path).relative_to(root).as_posix()
                        rows[relative] = (stat.st_size, stat.st_mtime_ns)
                except OSError:
                    continue
    return rows


async def _drain(stream: asyncio.StreamReader, limit: int) -> bytes:
    captured = bytearray()
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        remaining = limit - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
    return bytes(captured)


def _local_environment(workspace: Path) -> dict[str, str]:
    """Keep normal runtimes available while withholding common credential variables."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(
            marker in key.upper()
            for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        )
    }
    workspace_text = str(workspace)
    environment.update(
        {
            "HOME": workspace_text,
            "TMP": workspace_text,
            "TEMP": workspace_text,
            "TMPDIR": workspace_text,
            "XDG_CACHE_HOME": str(workspace / ".cache"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "npm_config_cache": str(workspace / ".npm-cache"),
        }
    )
    return environment


async def _terminate_process_tree(process) -> None:
    if process is None or process.returncode is not None:
        return
    if os.name == "nt":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass


def _runtime_error(message: str, command: str, audit_message: str) -> str:
    record_tool_failure(
        "bash",
        audit_message,
        {"command_length": len(command)},
        "Returned local runtime failure to the skills specialist.",
    )
    return f"LOCAL_RUNTIME_ERROR: {message}"


async def run_local_command(command: str) -> str:
    """Run after the reviewed Bash tool has approved the command."""
    command = (command or "").strip()
    if not command:
        return "LOCAL_RUNTIME_ERROR: command cannot be empty."
    if len(command) > LOCAL_RUN_COMMAND_MAX_CHARS or "\x00" in command:
        return "LOCAL_RUNTIME_ERROR: command is invalid or exceeds the configured limit."

    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        workspace = session_files_dir(create=True)
        before = await asyncio.to_thread(_snapshot, workspace)
        process = None
        stdout_task = None
        stderr_task = None
        try:
            kwargs = {
                "cwd": str(workspace),
                "env": _local_environment(workspace),
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            process = await asyncio.create_subprocess_shell(command, **kwargs)
            stdout_task = asyncio.create_task(
                _drain(process.stdout, LOCAL_RUN_OUTPUT_MAX_CHARS)
            )
            stderr_task = asyncio.create_task(
                _drain(process.stderr, LOCAL_RUN_OUTPUT_MAX_CHARS)
            )
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=max(1, LOCAL_RUN_TIMEOUT),
                )
            except asyncio.TimeoutError:
                await _terminate_process_tree(process)
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                return _runtime_error(
                    f"Execution timed out after {LOCAL_RUN_TIMEOUT}s.",
                    command,
                    "Local tmp command timed out.",
                )
            stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        except asyncio.CancelledError:
            await _terminate_process_tree(process)
            raise
        except Exception as exc:
            await _terminate_process_tree(process)
            return _runtime_error(
                f"Failed to run command: {exc}",
                command,
                "Local tmp command failed to start or communicate.",
            )
        finally:
            pending = [
                task
                for task in (stdout_task, stderr_task)
                if task is not None and not task.done()
            ]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()
        after = await asyncio.to_thread(_snapshot, workspace)
        changed = sorted(path for path, state in after.items() if before.get(path) != state)
        sections = [f"LOCAL_RUNTIME_EXIT_CODE={process.returncode}"]
        if output:
            sections.append(f"stdout:\n{output}")
        if error:
            sections.append(f"stderr:\n{error}")
        if changed:
            sections.append("Generated or updated files:\n- " + "\n- ".join(changed[:100]))
        result = "\n\n".join(sections)
        if process.returncode != 0:
            return _runtime_error(
                result,
                command,
                f"Local tmp command exited with code {process.returncode}.",
            )
        return result
