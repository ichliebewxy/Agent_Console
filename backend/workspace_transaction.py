"""Step-scoped workspace staging, commit, rollback, and tool receipts."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from runtime_context import session_files_dir, workflow_step_dir

_RESERVED_SESSION_DIRS = {"runs"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_internal(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    allowed = root.resolve()
    if resolved == allowed or not resolved.is_relative_to(allowed):
        raise RuntimeError("Refusing to mutate a path outside the workflow transaction root.")
    return resolved


def _reset_dir(path: Path, allowed_root: Path) -> None:
    target = _ensure_internal(path, allowed_root)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def _copy_tree_contents(source: Path, destination: Path, *, skip_reserved: bool) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        return
    for child in source.iterdir():
        if skip_reserved and child.name in _RESERVED_SESSION_DIRS:
            continue
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        elif child.is_file():
            shutil.copy2(child, target)


def _clear_visible_workspace(root: Path) -> None:
    for child in root.iterdir():
        if child.name in _RESERVED_SESSION_DIRS:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def begin_step_transaction(user_id: str, session_id: str, run_id: str, step_id: str) -> dict:
    session_root = session_files_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    metadata_path = step_root / "transaction.json"
    existing = _read_json(metadata_path)
    # A compensated, uncommitted step keeps its private staging tree. Reusing
    # it on recovery keeps persisted tool receipts consistent with the files
    # they describe and avoids replaying already-completed side effects.
    if existing.get("status") in {"begun", "committed", "rolled_back"} and (step_root / "staging").exists():
        return existing

    staging = step_root / "staging"
    snapshot = step_root / "snapshot"
    _reset_dir(staging, step_root)
    _reset_dir(snapshot, step_root)
    _copy_tree_contents(session_root, staging, skip_reserved=True)
    _copy_tree_contents(session_root, snapshot, skip_reserved=True)
    metadata = {
        "snapshot_id": uuid4().hex,
        "status": "begun",
        "started_at": _utc_now(),
        "run_id": run_id,
        "step_id": step_id,
    }
    _write_json(metadata_path, metadata)
    return metadata


def commit_step_transaction(user_id: str, session_id: str, run_id: str, step_id: str) -> dict:
    session_root = session_files_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    metadata_path = step_root / "transaction.json"
    metadata = _read_json(metadata_path)
    if metadata.get("status") == "committed":
        return metadata.get("receipt") or {}

    staging = step_root / "staging"
    if not staging.exists():
        raise RuntimeError("Workflow staging directory is missing.")
    _clear_visible_workspace(session_root)
    _copy_tree_contents(staging, session_root, skip_reserved=False)

    committed = step_root / "committed"
    _reset_dir(committed, step_root)
    _copy_tree_contents(staging, committed, skip_reserved=False)
    receipt = {
        "operation_key": f"{run_id}:{step_id}:workspace_commit",
        "kind": "workspace_commit",
        "status": "committed",
        "committed_at": _utc_now(),
        "snapshot_id": metadata.get("snapshot_id"),
    }
    metadata.update({"status": "committed", "receipt": receipt})
    _write_json(metadata_path, metadata)
    return receipt


def rollback_step_transaction(user_id: str, session_id: str, run_id: str, step_id: str) -> dict:
    session_root = session_files_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    metadata_path = step_root / "transaction.json"
    metadata = _read_json(metadata_path)
    if metadata.get("status") == "committed":
        snapshot = step_root / "snapshot"
        _clear_visible_workspace(session_root)
        _copy_tree_contents(snapshot, session_root, skip_reserved=False)
    metadata.update({"status": "rolled_back", "rolled_back_at": _utc_now()})
    _write_json(metadata_path, metadata)
    return {
        "operation_key": f"{run_id}:{step_id}:workspace_rollback",
        "kind": "workspace_rollback",
        "status": "rolled_back",
        "rolled_back_at": metadata["rolled_back_at"],
    }


def restore_step_version(
    user_id: str,
    session_id: str,
    run_id: str,
    step_id: str,
    *,
    committed: bool,
) -> None:
    session_root = session_files_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=False)
    source = step_root / ("committed" if committed else "snapshot")
    if not source.exists():
        raise FileNotFoundError(f"Workspace version is unavailable for step {step_id}.")
    _clear_visible_workspace(session_root)
    _copy_tree_contents(source, session_root, skip_reserved=False)


def load_tool_receipt(user_id: str, session_id: str, run_id: str, step_id: str, operation_key: str) -> dict | None:
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    value = _read_json(step_root / "tool_receipts.json").get(operation_key)
    return value if isinstance(value, dict) else None


def save_tool_receipt(
    user_id: str,
    session_id: str,
    run_id: str,
    step_id: str,
    operation_key: str,
    receipt: dict,
) -> None:
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    path = step_root / "tool_receipts.json"
    receipts = _read_json(path)
    receipts[operation_key] = {**receipt, "updated_at": _utc_now()}
    _write_json(path, receipts)
