"""Per-request identity and isolated session workspace resolution."""
import hashlib
import re
import shutil
import threading
import weakref
import asyncio
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


def session_workspace_key(user_id: str, session_id: str) -> str:
    raw = f"{user_id}\0{session_id}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def session_async_lock(user_id: str, session_id: str) -> asyncio.Lock:
    """Return the in-process lock that serializes one session's file mutations."""
    key = session_workspace_key(user_id, session_id)
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_LOCKS[key] = lock
        return lock


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
    key = session_workspace_key(user_id, session_id)
    root = (BACKEND_TMP_DIR / key).resolve()
    tmp_root = BACKEND_TMP_DIR.resolve()
    if not root.is_relative_to(tmp_root):
        raise RuntimeError("Resolved session workspace escaped its configured root.")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


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
    session_root = session_files_dir(user_id, session_id, create=create)
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
    root = session_files_dir(user_id, session_id, create=False)
    tmp_root = BACKEND_TMP_DIR.resolve()
    if root.parent != tmp_root:
        raise RuntimeError("Refusing to remove a path outside agent_workspace/sessions.")
    if root.exists():
        shutil.rmtree(root)
