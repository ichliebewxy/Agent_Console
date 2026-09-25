"""Lifecycle and API helpers for durable workflow checkpoints."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from settings import PROJECT_ROOT, WORKFLOW_CHECKPOINT_PATH
from workflow_graph import build_workflow_graph
from workflow_state import public_workflow_state, utc_now
from workspace_transaction import restore_step_version

_SAVER_CONTEXT = None
_CHECKPOINTER = None
_WORKFLOW = None
_RUN_INDEX_PATH = PROJECT_ROOT / "data" / "workflow_runs.json"
_RUN_INDEX_LOCK = asyncio.Lock()


def workflow_config(run_id: str, checkpoint_id: str | None = None) -> dict:
    # LangGraph can infer the root namespace for invoke(), but update_state()
    # requires it to be explicit when restoring a historical snapshot.
    configurable = {"thread_id": run_id, "checkpoint_ns": ""}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


async def initialize_checkpoint_service(execute_step) -> None:
    global _SAVER_CONTEXT, _CHECKPOINTER, _WORKFLOW
    if _WORKFLOW is not None:
        return
    WORKFLOW_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SAVER_CONTEXT = AsyncSqliteSaver.from_conn_string(str(WORKFLOW_CHECKPOINT_PATH))
    _CHECKPOINTER = await _SAVER_CONTEXT.__aenter__()
    await _CHECKPOINTER.setup()
    _WORKFLOW = build_workflow_graph(_CHECKPOINTER, execute_step)


async def close_checkpoint_service() -> None:
    global _SAVER_CONTEXT, _CHECKPOINTER, _WORKFLOW
    context = _SAVER_CONTEXT
    _WORKFLOW = None
    _CHECKPOINTER = None
    _SAVER_CONTEXT = None
    if context is not None:
        await context.__aexit__(None, None, None)


def get_workflow():
    if _WORKFLOW is None:
        raise RuntimeError("Workflow checkpoint service is not initialized.")
    return _WORKFLOW


def get_checkpointer():
    if _CHECKPOINTER is None:
        raise RuntimeError("Workflow checkpoint service is not initialized.")
    return _CHECKPOINTER


def _read_run_index() -> dict:
    try:
        value = json.loads(_RUN_INDEX_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_run_index(value: dict) -> None:
    _RUN_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _RUN_INDEX_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, _RUN_INDEX_PATH)


async def register_run(state: dict) -> None:
    run_id = state.get("run_id")
    if not run_id:
        return
    async with _RUN_INDEX_LOCK:
        index = await asyncio.to_thread(_read_run_index)
        previous = index.get(run_id) if isinstance(index.get(run_id), dict) else {}
        index[run_id] = {
            **previous,
            "run_id": run_id,
            "user_id": state.get("user_id", previous.get("user_id", "")),
            "session_id": state.get("session_id", previous.get("session_id", "")),
            "request": state.get("request", previous.get("request", "")),
            "run_status": state.get("run_status", previous.get("run_status", "planning")),
            "updated_at": utc_now(),
            "created_at": previous.get("created_at") or state.get("created_at") or utc_now(),
        }
        await asyncio.to_thread(_write_run_index, index)


async def list_runs(user_id: str | None = None, session_id: str | None = None) -> list[dict]:
    async with _RUN_INDEX_LOCK:
        index = await asyncio.to_thread(_read_run_index)
    rows = [value for value in index.values() if isinstance(value, dict)]
    if user_id is not None:
        rows = [row for row in rows if row.get("user_id") == user_id]
    if session_id is not None:
        rows = [row for row in rows if row.get("session_id") == session_id]
    return sorted(rows, key=lambda row: row.get("updated_at", ""), reverse=True)


def _checkpoint_id(config: dict | None) -> str | None:
    return ((config or {}).get("configurable") or {}).get("checkpoint_id")


def serialize_snapshot(snapshot) -> dict[str, Any]:
    values = dict(snapshot.values or {})
    interrupts = []
    task_errors = []
    for task in snapshot.tasks or ():
        interrupts.extend(
            getattr(item, "value", item) for item in (getattr(task, "interrupts", None) or ())
        )
        if getattr(task, "error", None):
            task_errors.append(str(task.error))
    public = public_workflow_state(values)
    public.update(
        {
            "checkpoint_id": _checkpoint_id(snapshot.config),
            "parent_checkpoint_id": _checkpoint_id(snapshot.parent_config),
            "created_at": snapshot.created_at or public.get("created_at", ""),
            "next": list(snapshot.next or ()),
            "interrupts": interrupts,
            "task_errors": task_errors,
            "metadata": dict(snapshot.metadata or {}),
        }
    )
    if interrupts and public.get("run_status") != "completed":
        public["run_status"] = "waiting_user"
    return public


async def get_run_state(run_id: str) -> dict:
    snapshot = await get_workflow().aget_state(workflow_config(run_id))
    if not snapshot.values:
        raise KeyError(run_id)
    state = serialize_snapshot(snapshot)
    await register_run(state)
    return state


async def get_run_history(run_id: str, limit: int = 100) -> list[dict]:
    rows = []
    async for snapshot in get_workflow().aget_state_history(
        workflow_config(run_id),
        limit=max(1, min(limit, 500)),
    ):
        rows.append(serialize_snapshot(snapshot))
    return rows


async def resume_run(run_id: str, payload: dict) -> dict:
    workflow = get_workflow()
    snapshot = await workflow.aget_state(workflow_config(run_id))
    if not snapshot.values:
        raise KeyError(run_id)
    has_interrupt = any(getattr(task, "interrupts", None) for task in snapshot.tasks or ())
    if has_interrupt:
        result = await workflow.ainvoke(
            Command(resume=payload),
            workflow_config(run_id),
            durability="sync",
        )
    else:
        if snapshot.values.get("run_status") in {"completed", "failed"}:
            raise ValueError("该工作流已经结束，无法继续恢复。")
        action = str(payload.get("action") or "retry")
        config = snapshot.config
        if action == "abort":
            config = await workflow.aupdate_state(
                config,
                {"run_status": "failed", "last_error": {"kind": "aborted", "message": "用户终止任务。"}},
            )
        result = await workflow.ainvoke(None, config, durability="sync")
    state = public_workflow_state(result)
    await register_run(state)
    return await get_run_state(run_id)


def _state_patch(values: dict) -> dict:
    allowed = {
        "objective",
        "steps",
        "step_order",
        "current_step_id",
        "last_committed_step_id",
        "attempts",
        "results",
        "last_error",
        "run_status",
        "workspace_snapshot_id",
        "effect_receipts",
        "final_response",
    }
    return {key: value for key, value in values.items() if key in allowed}


async def fork_run(
    run_id: str,
    checkpoint_id: str,
    patch: dict | None = None,
    *,
    continue_run: bool = False,
) -> dict:
    workflow = get_workflow()
    source_config = workflow_config(run_id, checkpoint_id)
    source = await workflow.aget_state(source_config)
    if not source.values:
        raise KeyError(checkpoint_id)
    values = dict(source.values)
    last_step = values.get("last_committed_step_id")
    snapshot_step = values.get("current_step_id")
    if last_step:
        await asyncio.to_thread(
            restore_step_version,
            values["user_id"],
            values["session_id"],
            run_id,
            last_step,
            committed=True,
        )
    elif snapshot_step:
        await asyncio.to_thread(
            restore_step_version,
            values["user_id"],
            values["session_id"],
            run_id,
            snapshot_step,
            committed=False,
        )
    source_has_next = bool(source.next)
    update = {
        "last_error": None,
        "run_status": "running" if source_has_next else values.get("run_status", "completed"),
        **_state_patch(patch or {}),
    }
    source_config = dict(source.config or {})
    configurable = dict(source_config.get("configurable") or {})
    configurable.setdefault("thread_id", run_id)
    configurable.setdefault("checkpoint_ns", "")
    source_config["configurable"] = configurable
    fork_config = await workflow.aupdate_state(source_config, update)
    if continue_run and source_has_next:
        await workflow.ainvoke(None, fork_config, durability="sync")
    return await get_run_state(run_id)
