"""Serializable state contract for the durable plan-and-execute workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict


FLOW_VERSION = 1

RunStatus = Literal[
    "planning",
    "running",
    "waiting_user",
    "rolling_back",
    "failed",
    "completed",
]
StepStatus = Literal["pending", "in_progress", "done", "failed", "skipped"]


class StepState(TypedDict, total=False):
    id: str
    title: str
    detail: str
    status: StepStatus
    result: str


class StepResult(TypedDict, total=False):
    step_id: str
    output: str
    status: str
    validation: str
    tool_events: list[dict[str, Any]]
    rag_trace: dict[str, Any] | None
    completed_at: str


class ErrorInfo(TypedDict, total=False):
    kind: str
    message: str
    step_id: str | None
    retryable: bool
    unknown_effect: bool


class EffectReceipt(TypedDict, total=False):
    operation_key: str
    kind: str
    status: str
    committed_at: str
    snapshot_id: str | None


class WorkflowState(TypedDict, total=False):
    flow_version: int
    run_id: str
    user_id: str
    session_id: str
    request: str
    history: list[dict]
    created_at: str
    updated_at: str

    objective: str
    steps: dict[str, StepState]
    step_order: list[str]
    current_step_id: str | None
    last_committed_step_id: str | None

    attempts: dict[str, int]
    results: dict[str, StepResult]
    last_error: ErrorInfo | None
    run_status: RunStatus

    workspace_snapshot_id: str | None
    effect_receipts: dict[str, EffectReceipt]
    rag_trace: dict[str, Any] | None
    final_response: str

    validation_status: str
    reflection_decision: str
    reflection_reason: str
    reflection_notes: list[str]
    recovery_action: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initial_workflow_state(
    run_id: str,
    user_id: str,
    session_id: str,
    request: str,
    history: list[dict] | None = None,
) -> WorkflowState:
    now = utc_now()
    return {
        "flow_version": FLOW_VERSION,
        "run_id": run_id,
        "user_id": user_id,
        "session_id": session_id,
        "request": request,
        "history": history or [],
        "created_at": now,
        "updated_at": now,
        "objective": request,
        "steps": {},
        "step_order": [],
        "current_step_id": None,
        "last_committed_step_id": None,
        "attempts": {},
        "results": {},
        "last_error": None,
        "run_status": "planning",
        "workspace_snapshot_id": None,
        "effect_receipts": {},
        "rag_trace": None,
        "final_response": "",
        "validation_status": "",
        "reflection_decision": "continue",
        "reflection_reason": "",
        "reflection_notes": [],
        "recovery_action": "",
    }


def ordered_steps(state: WorkflowState) -> list[StepState]:
    steps = state.get("steps") or {}
    return [steps[step_id] for step_id in state.get("step_order") or [] if step_id in steps]


def plan_payload(state: WorkflowState) -> dict[str, Any]:
    return {
        "objective": state.get("objective") or state.get("request") or "",
        "steps": [dict(step) for step in ordered_steps(state)],
    }


def public_workflow_state(state: WorkflowState) -> dict[str, Any]:
    return {
        "flow_version": state.get("flow_version", FLOW_VERSION),
        "run_id": state.get("run_id", ""),
        "user_id": state.get("user_id", ""),
        "session_id": state.get("session_id", ""),
        "request": state.get("request", ""),
        "objective": state.get("objective", ""),
        "steps": [dict(step) for step in ordered_steps(state)],
        "current_step_id": state.get("current_step_id"),
        "last_committed_step_id": state.get("last_committed_step_id"),
        "attempts": dict(state.get("attempts") or {}),
        "last_error": state.get("last_error"),
        "run_status": state.get("run_status", "planning"),
        "workspace_snapshot_id": state.get("workspace_snapshot_id"),
        "effect_receipts": dict(state.get("effect_receipts") or {}),
        "rag_trace": state.get("rag_trace"),
        "final_response": state.get("final_response", ""),
        "created_at": state.get("created_at", ""),
        "updated_at": state.get("updated_at", ""),
    }
