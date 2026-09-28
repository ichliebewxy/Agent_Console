"""Step-scoped workspace staging, commit, rollback, and tool receipts."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import runtime_context
from runtime_context import _session_root_dir, session_files_dir, workflow_step_dir

_RESERVED_SESSION_DIRS = {"runs", ".versions", ".active_version.json"}


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


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _active_version(session_root: Path) -> str | None:
    return _read_json(session_root / ".active_version.json").get("version")


def _publish_version(session_root: Path, source: Path, version: str) -> None:
    """Build an invisible version, then atomically select it by one manifest replace."""
    versions = session_root / ".versions"
    if versions.is_symlink():
        raise RuntimeError("Refusing to use a linked workspace version directory.")
    versions.mkdir(parents=True, exist_ok=True)
    candidate = versions / version
    _reset_dir(candidate, versions)
    _copy_tree_contents(source, candidate, skip_reserved=False)
    _write_json(session_root / ".active_version.json", {"version": version})


def _recover_incomplete_commit(session_root: Path, step_root: Path) -> dict:
    metadata_path = step_root / "transaction.json"
    metadata = _read_json(metadata_path)
    if metadata.get("status") != "committing":
        return metadata
    version = metadata.get("candidate_version")
    if not isinstance(version, str) or len(version) != 32 or any(c not in "0123456789abcdef" for c in version):
        raise RuntimeError("Invalid pending workspace version.")
    if _active_version(session_root) == version:
        # Manifest replacement was the commit point; a crash after it must be
        # finalized, never silently rolled back to a partially changed tree.
        metadata["status"] = "committed"
        metadata["receipt"] = metadata["pending_receipt"]
    else:
        candidate = session_root / ".versions" / version
        if candidate.exists():
            shutil.rmtree(_ensure_internal(candidate, session_root / ".versions"))
        committed = step_root / "committed"
        if committed.exists():
            shutil.rmtree(_ensure_internal(committed, step_root))
        metadata["status"] = "begun"
    metadata.pop("candidate_version", None)
    metadata.pop("pending_receipt", None)
    _write_json(metadata_path, metadata)
    return metadata


def recover_workspace_transactions() -> None:
    """Resolve interrupted commits before the API begins serving workspaces."""
    base = runtime_context.BACKEND_TMP_DIR
    if not base.exists():
        return
    for session_root in base.iterdir():
        if not session_root.is_dir() or session_root.is_symlink():
            continue
        runs = session_root / "runs"
        if not runs.is_dir():
            continue
        for metadata_path in runs.glob("*/steps/*/transaction.json"):
            step_root = metadata_path.parent
            if not step_root.resolve().is_relative_to(runs.resolve()):
                continue
            if _read_json(metadata_path).get("status") == "committing":
                _recover_incomplete_commit(session_root, step_root)


def begin_step_transaction(user_id: str, session_id: str, run_id: str, step_id: str) -> dict:
    session_root = session_files_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    metadata_path = step_root / "transaction.json"
    existing = _recover_incomplete_commit(
        _session_root_dir(user_id, session_id), step_root
    )
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
    session_root = _session_root_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    metadata_path = step_root / "transaction.json"
    metadata = _recover_incomplete_commit(session_root, step_root)
    if metadata.get("status") == "committed":
        return metadata.get("receipt") or {}

    staging = step_root / "staging"
    if not staging.exists():
        raise RuntimeError("Workflow staging directory is missing.")
    version = uuid4().hex
    receipt = {
        "operation_key": f"{run_id}:{step_id}:workspace_commit",
        "kind": "workspace_commit",
        "status": "committed",
        "committed_at": _utc_now(),
        "snapshot_id": metadata.get("snapshot_id"),
    }
    metadata.update({"status": "committing", "candidate_version": version, "pending_receipt": receipt})
    _write_json(metadata_path, metadata)
    try:
        committed = step_root / "committed"
        _reset_dir(committed, step_root)
        _copy_tree_contents(staging, committed, skip_reserved=False)
        _publish_version(session_root, committed, version)
    except Exception:
        _recover_incomplete_commit(session_root, step_root)
        raise
    metadata.update({"status": "committed", "receipt": receipt})
    metadata.pop("candidate_version", None)
    metadata.pop("pending_receipt", None)
    try:
        _write_json(metadata_path, metadata)
    except OSError:
        # The manifest already selected the complete version. Finish the
        # journal from its durable committing record before returning.
        _recover_incomplete_commit(session_root, step_root)
    return receipt


def rollback_step_transaction(user_id: str, session_id: str, run_id: str, step_id: str) -> dict:
    session_root = _session_root_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=True)
    metadata_path = step_root / "transaction.json"
    metadata = _recover_incomplete_commit(session_root, step_root)
    if metadata.get("status") == "committed":
        snapshot = step_root / "snapshot"
        _publish_version(session_root, snapshot, uuid4().hex)
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
    session_root = _session_root_dir(user_id, session_id, create=True)
    step_root = workflow_step_dir(user_id, session_id, run_id, step_id, create=False)
    source = step_root / ("committed" if committed else "snapshot")
    if not source.exists():
        raise FileNotFoundError(f"Workspace version is unavailable for step {step_id}.")
    _publish_version(session_root, source, uuid4().hex)


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
