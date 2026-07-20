"""Ephemeral Docker sandbox for all agent-requested program execution."""
import asyncio
import os
import shutil
from pathlib import Path
from uuid import uuid4

from langchain_core.tools import tool

from ops_store import record_tool_failure
from runtime_context import current_runtime_context, session_async_lock, session_files_dir
from settings import (
    SANDBOX_COMMAND_MAX_CHARS,
    SANDBOX_CPUS,
    SANDBOX_DOCKER_CLEANUP_TIMEOUT,
    SANDBOX_DOCKER_BIN,
    SANDBOX_ENABLED,
    SANDBOX_FILE_MAX_MB,
    SANDBOX_GID,
    SANDBOX_IMAGE,
    SANDBOX_MAX_FILES,
    SANDBOX_MEMORY_MB,
    SANDBOX_OUTPUT_MAX_CHARS,
    SANDBOX_PIDS_LIMIT,
    SANDBOX_TIMEOUT,
    SANDBOX_UID,
    SANDBOX_WORKSPACE_MAX_MB,
)


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    rows = {}
    for candidate in root.rglob("*"):
        try:
            path = candidate.resolve()
            if path.is_relative_to(root) and path.is_file():
                stat = path.stat()
                rows[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
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


async def _docker_cleanup(container_name: str) -> None:
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            SANDBOX_DOCKER_BIN,
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=max(1, SANDBOX_DOCKER_CLEANUP_TIMEOUT),
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
    except (OSError, ProcessLookupError):
        pass


def _terminate_process(process) -> None:
    if process is None or process.returncode is not None:
        return
    try:
        process.kill()
    except ProcessLookupError:
        pass


async def _bounded_process_wait(process) -> None:
    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=max(1, SANDBOX_DOCKER_CLEANUP_TIMEOUT),
        )
    except asyncio.TimeoutError:
        pass


def _workspace_usage(root: Path) -> tuple[int, int, int]:
    """Return total bytes, regular-file count, and largest file without following links."""
    total = 0
    count = 0
    largest = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        count += 1
                        total += size
                        largest = max(largest, size)
                except OSError:
                    continue
                if count > max(1, SANDBOX_MAX_FILES):
                    return total, count, largest
                if total > max(1, SANDBOX_WORKSPACE_MAX_MB) * 1024 * 1024:
                    return total, count, largest
    return total, count, largest


def _workspace_limit_error(root: Path) -> str | None:
    total, count, largest = _workspace_usage(root)
    total_limit = max(1, SANDBOX_WORKSPACE_MAX_MB) * 1024 * 1024
    file_limit = max(1, SANDBOX_FILE_MAX_MB) * 1024 * 1024
    if count > max(1, SANDBOX_MAX_FILES):
        return f"Workspace file limit exceeded ({count} > {SANDBOX_MAX_FILES})."
    if largest > file_limit:
        return f"Single-file limit exceeded ({largest} > {file_limit} bytes)."
    if total > total_limit:
        return f"Workspace size limit exceeded ({total} > {total_limit} bytes)."
    return None


def _prepare_workspace_owner(root: Path) -> None:
    """Make native-Linux bind-mounted files writable by the configured container UID."""
    if os.name == "nt":
        return
    uid = max(1, SANDBOX_UID)
    gid = max(1, SANDBOX_GID)
    if hasattr(os, "getuid") and os.getuid() == uid and os.getgid() == gid:
        return
    candidates = [root]
    candidates.extend(root.rglob("*"))
    for candidate in candidates:
        os.chown(candidate, uid, gid, follow_symlinks=False)


async def _monitor_workspace(root: Path, process) -> str | None:
    while True:
        violation = await asyncio.to_thread(_workspace_limit_error, root)
        if violation:
            _terminate_process(process)
            return violation
        if process.returncode is not None:
            return None
        await asyncio.sleep(0.1)


def _docker_args(container_name: str, workspace: Path, command: str) -> list[str]:
    memory = max(64, SANDBOX_MEMORY_MB)
    file_size_bytes = max(1, SANDBOX_FILE_MAX_MB) * 1024 * 1024
    return [
        SANDBOX_DOCKER_BIN,
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(max(16, SANDBOX_PIDS_LIMIT)),
        "--memory",
        f"{memory}m",
        "--memory-swap",
        f"{memory}m",
        "--cpus",
        str(max(0.1, SANDBOX_CPUS)),
        "--ulimit",
        "nofile=256:256",
        "--ulimit",
        f"fsize={file_size_bytes}:{file_size_bytes}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--user",
        f"{max(1, SANDBOX_UID)}:{max(1, SANDBOX_GID)}",
        "--env",
        "HOME=/tmp",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--volume",
        f"{workspace}:/workspace:rw",
        "--workdir",
        "/workspace",
        SANDBOX_IMAGE,
        "/bin/sh",
        "-lc",
        command,
    ]


def _sandbox_error(message: str, command: str, audit_message: str | None = None) -> str:
    record_tool_failure(
        "run_in_sandbox",
        audit_message or message,
        {"command_length": len(command), "image": SANDBOX_IMAGE},
        "Returned sandbox failure to the skills specialist.",
    )
    return f"SANDBOX_ERROR: {message}"


@tool
async def sandbox_status() -> str:
    """Check whether Docker and the configured immutable sandbox image are ready."""
    if not SANDBOX_ENABLED:
        return "SANDBOX_ERROR: Sandbox execution is disabled by configuration."
    if not shutil.which(SANDBOX_DOCKER_BIN):
        return f"SANDBOX_ERROR: Docker executable not found: {SANDBOX_DOCKER_BIN}"
    process = await asyncio.create_subprocess_exec(
        SANDBOX_DOCKER_BIN,
        "image",
        "inspect",
        SANDBOX_IMAGE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=max(1, SANDBOX_DOCKER_CLEANUP_TIMEOUT),
        )
    except asyncio.TimeoutError:
        _terminate_process(process)
        await _bounded_process_wait(process)
        return "SANDBOX_ERROR: Docker image inspection timed out."
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        return f"SANDBOX_ERROR: Image '{SANDBOX_IMAGE}' is unavailable. {detail}"
    return f"Sandbox ready: image={SANDBOX_IMAGE}, network=none, rootfs=read-only"


@tool
async def run_in_sandbox(command: str) -> str:
    """Run a shell command only inside the isolated session Docker sandbox."""
    command = (command or "").strip()
    if not SANDBOX_ENABLED:
        return _sandbox_error("Sandbox execution is disabled.", command)
    if not command:
        return "SANDBOX_ERROR: command cannot be empty."
    if len(command) > SANDBOX_COMMAND_MAX_CHARS or "\x00" in command:
        return "SANDBOX_ERROR: command is invalid or exceeds the configured limit."
    if not shutil.which(SANDBOX_DOCKER_BIN):
        return _sandbox_error(f"Docker executable not found: {SANDBOX_DOCKER_BIN}", command)

    context = current_runtime_context()
    async with session_async_lock(context.user_id, context.session_id):
        return await _run_in_sandbox_locked(command)


async def _run_in_sandbox_locked(command: str) -> str:
    """Execute after the caller has acquired the per-session mutation lock."""

    workspace = session_files_dir(create=True)
    existing_violation = await asyncio.to_thread(_workspace_limit_error, workspace)
    if existing_violation:
        return _sandbox_error(
            f"Execution refused: {existing_violation}",
            command,
            "Sandbox execution refused because the session workspace exceeded quota.",
        )
    try:
        await asyncio.to_thread(_prepare_workspace_owner, workspace)
    except OSError as exc:
        return _sandbox_error(
            f"Cannot prepare workspace ownership for sandbox UID/GID: {exc}",
            command,
            "Sandbox workspace ownership preparation failed.",
        )
    before = await asyncio.to_thread(_snapshot, workspace)
    container_name = f"agent-sbx-{uuid4().hex[:16]}"
    args = _docker_args(container_name, workspace, command)
    process = None
    stdout_task = None
    stderr_task = None
    monitor_task = None
    cleaned = False
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_task = asyncio.create_task(_drain(process.stdout, SANDBOX_OUTPUT_MAX_CHARS))
        stderr_task = asyncio.create_task(_drain(process.stderr, SANDBOX_OUTPUT_MAX_CHARS))
        monitor_task = asyncio.create_task(_monitor_workspace(workspace, process))
        try:
            await asyncio.wait_for(process.wait(), timeout=max(1, SANDBOX_TIMEOUT))
        except asyncio.TimeoutError:
            _terminate_process(process)
            await _bounded_process_wait(process)
            return _sandbox_error(
                f"Execution timed out after {SANDBOX_TIMEOUT}s.",
                command,
                "Sandbox execution timed out.",
            )

        quota_error = await monitor_task
        if quota_error:
            _terminate_process(process)
            await _bounded_process_wait(process)
            return _sandbox_error(
                quota_error,
                command,
                "Sandbox workspace quota was exceeded.",
            )
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    except asyncio.CancelledError:
        _terminate_process(process)
        raise
    except Exception as exc:
        return _sandbox_error(
            f"Failed to start sandbox: {exc}",
            command,
            "Sandbox process failed to start or communicate with Docker.",
        )
    finally:
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        if process and process.returncode is None:
            _terminate_process(process)
            await _bounded_process_wait(process)
        cleanup_task = asyncio.create_task(_docker_cleanup(container_name))
        try:
            await asyncio.shield(cleanup_task)
            cleaned = True
        except asyncio.CancelledError:
            await cleanup_task
            raise
        if not cleaned:
            await _docker_cleanup(container_name)
        pending_drains = [
            task
            for task in (stdout_task, stderr_task)
            if task is not None and not task.done()
        ]
        if pending_drains:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending_drains, return_exceptions=True),
                    timeout=max(1, SANDBOX_DOCKER_CLEANUP_TIMEOUT),
                )
            except asyncio.TimeoutError:
                for task in pending_drains:
                    task.cancel()

    output = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace").strip()
    after = await asyncio.to_thread(_snapshot, workspace)
    changed = sorted(path for path, state in after.items() if before.get(path) != state)
    sections = [f"SANDBOX_EXIT_CODE={process.returncode}"]
    if output:
        sections.append(f"stdout:\n{output}")
    if error:
        sections.append(f"stderr:\n{error}")
    if changed:
        sections.append("Generated or updated files:\n- " + "\n- ".join(changed[:100]))
    result = "\n\n".join(sections)
    if process.returncode != 0:
        return _sandbox_error(
            result,
            command,
            f"Sandboxed command exited with code {process.returncode}.",
        )
    return result


SANDBOX_TOOLS = [sandbox_status, run_in_sandbox]
