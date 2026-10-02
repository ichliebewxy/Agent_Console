"""Per-request identity and isolated session workspace resolution."""
import asyncio
import hashlib
import json
import re
import shutil
import threading
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from settings import BACKEND_TMP_DIR


@dataclass(frozen=True)
class AgentRuntimeContext:
    user_id: str
    session_id: str
    run_id: str | None = None
    step_id: str | None = None


_RUNTIME_CONTEXT: ContextVar[AgentRuntimeContext | None] = ContextVar(
    "agent_runtime_context",
    default=None,
)
_SESSION_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)
_FILE_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)
_SESSION_LOCKS_GUARD = threading.Lock()


@contextmanager
def bind_runtime_context(
    user_id: str,
    session_id: str,
    run_id: str | None = None,
    step_id: str | None = None,
):
    token = _RUNTIME_CONTEXT.set(
        AgentRuntimeContext(
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            step_id=step_id,
        )
    )
    try:
        yield
    finally:
        _RUNTIME_CONTEXT.reset(token)


def current_runtime_context() -> AgentRuntimeContext:
    context = _RUNTIME_CONTEXT.get()
    if context is None:
        raise RuntimeError("No active agent session context.")
    return context


def current_permission_mode() -> str:
    """Startup/MCP checks stay restricted; chats use their saved session policy."""
    context = _RUNTIME_CONTEXT.get()
    if context is None:
        return "restricted"
    from session_resources import SESSION_RESOURCES

    return SESSION_RESOURCES.get(context.user_id, context.session_id).permission_mode


def workspace_directory(user_id: str, session_id: str, *, create: bool = True) -> Path:
    """The selected local folder, or the managed folder for a folderless chat."""
    from session_resources import SESSION_RESOURCES

    selected = SESSION_RESOURCES.get(user_id, session_id).workspace_dir
    if selected:
        root = Path(selected).resolve()
        if not root.is_dir():
            raise ValueError("所选工作文件夹不存在或无法访问，请重新选择或不选文件夹运行。")
        return root
    return session_files_dir(user_id, session_id, create=create).resolve()


def resolve_workspace_path(path: str, root: Path | None = None) -> Path:
    workspace = (root or active_workspace_dir()).resolve()
    target = (workspace / path).resolve()
    if current_permission_mode() == "restricted" and not target.is_relative_to(workspace):
        raise ValueError("Path escapes the current session workspace.")
    return target


def session_workspace_key(user_id: str, session_id: str) -> str:
    raw = f"{user_id}\0{session_id}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def session_async_lock(user_id: str, session_id: str) -> asyncio.Lock:
    """Serialize whole conversation turns and workflow runs for one session."""
    key = session_workspace_key(user_id, session_id)
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_LOCKS[key] = lock
        return lock


def session_file_lock(user_id: str, session_id: str) -> asyncio.Lock:
    """Serialize file tools without re-acquiring the outer conversation lock."""
    key = session_workspace_key(user_id, session_id)
    with _SESSION_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _FILE_LOCKS[key] = lock
        return lock


def _session_root_dir(user_id: str, session_id: str, *, create: bool = True) -> Path:
    """Physical session container for versions and durable workflow records."""
    key = session_workspace_key(user_id, session_id)
    root = (BACKEND_TMP_DIR / key).resolve()
    tmp_root = BACKEND_TMP_DIR.resolve()
    if not root.is_relative_to(tmp_root):
        raise RuntimeError("Resolved session workspace escaped its configured root.")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def session_files_dir(
    user_id: str | None = None,
    session_id: str | None = None,
    *,
    create: bool = True,
) -> Path:
    if user_id is None or session_id is None:
        context = current_runtime_context()
        user_id = context.user_id
        session_id = context.session_id
    root = _session_root_dir(user_id, session_id, create=create)
    manifest = root / ".active_version.json"
    if not manifest.exists():
        return root  # Existing sessions remain readable until their first commit.
    try:
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Session workspace version manifest is invalid.") from exc
    if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{32}", version):
        raise RuntimeError("Session workspace version manifest is invalid.")
    visible = root / ".versions" / version
    if (
        not visible.is_dir()
        or visible.is_symlink()
        or not visible.resolve().is_relative_to(root)
    ):
        raise RuntimeError("Active session workspace version is missing.")
    return visible


def _safe_workflow_segment(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value or ""):
        raise ValueError(f"Invalid workflow {label}.")
    return value


def workflow_step_dir(
    user_id: str,
    session_id: str,
    run_id: str,
    step_id: str,
    *,
    create: bool = True,
) -> Path:
    session_root = _session_root_dir(user_id, session_id, create=create)
    run_segment = _safe_workflow_segment(run_id, "run id")
    step_segment = _safe_workflow_segment(step_id, "step id")
    root = (session_root / "runs" / run_segment / "steps" / step_segment).resolve()
    runs_root = (session_root / "runs").resolve()
    if not root.is_relative_to(runs_root):
        raise RuntimeError("Resolved workflow step escaped its session workspace.")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def active_workspace_dir(*, create: bool = True) -> Path:
    context = current_runtime_context()
    from session_resources import SESSION_RESOURCES

    if SESSION_RESOURCES.get(context.user_id, context.session_id).workspace_dir:
        return workspace_directory(context.user_id, context.session_id, create=create)
    if context.run_id and context.step_id:
        root = workflow_step_dir(
            context.user_id,
            context.session_id,
            context.run_id,
            context.step_id,
            create=create,
        ) / "staging"
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root.resolve()
    return session_files_dir(context.user_id, context.session_id, create=create).resolve()


def delete_session_files(user_id: str, session_id: str) -> None:
    """Remove only the hashed file directory belonging to one deleted session."""
    root = _session_root_dir(user_id, session_id, create=False)
    tmp_root = BACKEND_TMP_DIR.resolve()
    if root.parent != tmp_root:
        raise RuntimeError("Refusing to remove a path outside agent_workspace/sessions.")
    if root.exists():
        shutil.rmtree(root)
