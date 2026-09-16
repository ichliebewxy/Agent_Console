"""Durable LangGraph orchestration for plan-and-execute tasks."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import plan_execute
from agent_state import set_conversation_history
from runtime_context import bind_runtime_context
from settings import PLAN_EXECUTE_MAX_STEPS, WORKFLOW_MAX_RETRIES
from workflow_state import FLOW_VERSION, WorkflowState, utc_now
from workspace_transaction import (
    begin_step_transaction,
    commit_step_transaction,
    rollback_step_transaction,
)

StepExecutor = Callable[[str], Awaitable[dict]]

_ERROR_PREFIXES = (
    "TOOL_ERROR:",
    "OPENCLI_ERROR:",
    "SPECIALIST_ERROR:",
    "SKILL_ERROR:",
    "WORKSPACE_ERROR:",
    "LOCAL_RUNTIME_ERROR:",
    "PERMISSION_DENIED:",
    "TOOL_CALL_LIMIT_REACHED:",
    "UNKNOWN_EFFECT:",
)
_TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "429",
    "rate limit",
    "temporarily unavailable",
    "connection reset",
    "connection aborted",
    "连接超时",
    "限流",
    "暂时不可用",
)


def _plan_from_state(state: WorkflowState) -> plan_execute.Plan:
    steps = state.get("steps") or {}
    return plan_execute.Plan(
        objective=state.get("objective") or state.get("request") or "",
        steps=[
            plan_execute.PlanStep(**steps[step_id])
            for step_id in state.get("step_order") or []
            if step_id in steps
        ],
    )


def _plan_update(plan: plan_execute.Plan) -> dict:
    return {
        "objective": plan.objective,
        "steps": {step.id: step.to_dict() for step in plan.steps},
        "step_order": [step.id for step in plan.steps],
        "updated_at": utc_now(),
    }


def _current_step(state: WorkflowState) -> dict:
    step_id = state.get("current_step_id")
    step = (state.get("steps") or {}).get(step_id or "")
    if not step_id or not step:
        raise RuntimeError("Workflow has no current step.")
    return step


async def _init_run(state: WorkflowState) -> dict:
    if int(state.get("flow_version", FLOW_VERSION)) != FLOW_VERSION:
        raise RuntimeError("Unsupported workflow checkpoint version.")
    return {
        "flow_version": FLOW_VERSION,
        "run_status": "planning",
        "updated_at": utc_now(),
    }


async def _plan(state: WorkflowState) -> dict:
    plan = await plan_execute.generate_plan(
        state.get("request") or "",
        max_steps=PLAN_EXECUTE_MAX_STEPS,
        history=state.get("history") or [],
    )
    return {
        **_plan_update(plan),
        "run_status": "running",
        "last_error": None,
    }


async def _select_step(state: WorkflowState) -> dict:
    steps = state.get("steps") or {}
    current = next(
        (
            step_id
            for step_id in state.get("step_order") or []
            if steps.get(step_id, {}).get("status") == "pending"
        ),
        None,
    )
    return {
        "current_step_id": current,
        "run_status": "running" if current else state.get("run_status", "running"),
        "updated_at": utc_now(),
    }


def _after_select(state: WorkflowState) -> str:
    return "begin_step_transaction" if state.get("current_step_id") else "finalize_success"


async def _begin_step(state: WorkflowState) -> dict:
    step = dict(_current_step(state))
    step_id = step["id"]
    transaction = await asyncio.to_thread(
        begin_step_transaction,
        state["user_id"],
        state["session_id"],
        state["run_id"],
        step_id,
    )
    step["status"] = "in_progress"
    steps = dict(state.get("steps") or {})
    steps[step_id] = step
    return {
        "steps": steps,
        "workspace_snapshot_id": transaction.get("snapshot_id"),
        "validation_status": "",
        "recovery_action": "",
        "updated_at": utc_now(),
    }


def _build_instruction(state: WorkflowState) -> str:
    plan = _plan_from_state(state)
    step_id = state["current_step_id"]
    index = state.get("step_order", []).index(step_id)
    step = next(item for item in plan.steps if item.id == step_id)
    return plan_execute.build_step_instruction(plan, step, index + 1, len(plan.steps))


def _make_execute_node(execute_step: StepExecutor):
    async def _execute(state: WorkflowState) -> dict:
        step_id = state["current_step_id"]
        attempts = dict(state.get("attempts") or {})
        attempts[step_id] = int(attempts.get(step_id, 0)) + 1
        with bind_runtime_context(
            state["user_id"],
            state["session_id"],
            state["run_id"],
            step_id,
        ):
            # 把本轮之前积累的会话历史注入到步骤执行器里，否则每一步都以
            # 空白上下文执行，跨轮次的地点/选择等信息会全部丢失。
            set_conversation_history(state.get("history") or [])
            execution = await execute_step(_build_instruction(state))
        results = dict(state.get("results") or {})
        results[step_id] = {
            "step_id": step_id,
            "output": str(execution.get("response") or ""),
            "status": "executed",
            "tool_events": list(execution.get("tool_events") or []),
            "rag_trace": execution.get("rag_trace"),
        }
        return {
            "attempts": attempts,
            "results": results,
            "rag_trace": execution.get("rag_trace") or state.get("rag_trace"),
            "updated_at": utc_now(),
        }

    return _execute


async def _validate_step(state: WorkflowState) -> dict:
    step_id = state["current_step_id"]
    result = dict((state.get("results") or {}).get(step_id) or {})
    output = str(result.get("output") or "").strip()
    tool_events = result.get("tool_events") or []
    failed_events = [
        event for event in tool_events if event.get("phase") in {"error", "limit"}
    ]
    error_text = " ".join(
        [output, *[str(event.get("result") or "") for event in failed_events]]
    )
    has_error = (
        not output
        or bool(failed_events)
        or any(prefix in error_text for prefix in _ERROR_PREFIXES)
    )
    if not has_error:
        result["validation"] = "success"
        results = dict(state.get("results") or {})
        results[step_id] = result
        return {
            "results": results,
            "validation_status": "success",
            "last_error": None,
            "updated_at": utc_now(),
        }

    lowered = error_text.lower()
    unknown = "UNKNOWN_EFFECT:" in error_text
    retryable = any(marker in lowered for marker in _TRANSIENT_MARKERS)
    attempts = int((state.get("attempts") or {}).get(step_id, 0))
    validation = "retry" if retryable and attempts <= WORKFLOW_MAX_RETRIES else "recover"
    result["validation"] = validation
    result["status"] = "failed"
    results = dict(state.get("results") or {})
    results[step_id] = result
    return {
        "results": results,
        "validation_status": validation,
        "last_error": {
            "kind": "unknown_effect" if unknown else ("transient" if retryable else "step_failed"),
            "message": error_text[:2000] or "步骤未产生可验证结果。",
            "step_id": step_id,
            "retryable": retryable,
            "unknown_effect": unknown,
        },
        "updated_at": utc_now(),
    }


def _after_validate(state: WorkflowState) -> str:
    return {
        "success": "commit_step",
        "retry": "retry_step",
    }.get(state.get("validation_status", ""), "compensate")


async def _retry_step(state: WorkflowState) -> dict:
    return {
        "run_status": "running",
        "validation_status": "",
        "updated_at": utc_now(),
    }


async def _commit_step(state: WorkflowState) -> dict:
    step_id = state["current_step_id"]
    receipt = await asyncio.to_thread(
        commit_step_transaction,
        state["user_id"],
        state["session_id"],
        state["run_id"],
        step_id,
    )
    steps = dict(state.get("steps") or {})
    step = dict(steps[step_id])
    result = dict((state.get("results") or {}).get(step_id) or {})
    step["status"] = "done"
    step["result"] = str(result.get("output") or "")
    steps[step_id] = step
    result.update({"status": "committed", "completed_at": utc_now()})
    results = dict(state.get("results") or {})
    results[step_id] = result
    receipts = dict(state.get("effect_receipts") or {})
    receipts[receipt["operation_key"]] = receipt
    prior = state.get("final_response", "").rstrip()
    block = f"### {step['title']}\n{step['result']}".strip()
    return {
        "steps": steps,
        "results": results,
        "effect_receipts": receipts,
        "last_committed_step_id": step_id,
        "final_response": f"{prior}\n\n{block}".strip(),
        "updated_at": utc_now(),
    }


async def _reflect(state: WorkflowState) -> dict:
    plan = _plan_from_state(state)
    last = str((state.get("results") or {}).get(state["current_step_id"], {}).get("output") or "")
    try:
        reflection = await plan_execute.reflect(plan, last)
        notes = plan_execute.apply_reflection(plan, reflection)
        return {
            **_plan_update(plan),
            "reflection_decision": reflection.decision,
            "reflection_reason": reflection.reason,
            "reflection_notes": notes,
            "current_step_id": None,
        }
    except Exception as exc:
        return {
            "reflection_decision": "continue",
            "reflection_reason": f"反省失败，沿用原计划：{exc}",
            "reflection_notes": [],
            "current_step_id": None,
            "updated_at": utc_now(),
        }


def _after_reflect(state: WorkflowState) -> str:
    decision = state.get("reflection_decision", "continue")
    if decision == "complete":
        return "finalize_success"
    if decision == "stop":
        return "finalize_failed"
    return "select_step"


async def _compensate(state: WorkflowState) -> dict:
    step_id = state["current_step_id"]
    receipt = await asyncio.to_thread(
        rollback_step_transaction,
        state["user_id"],
        state["session_id"],
        state["run_id"],
        step_id,
    )
    steps = dict(state.get("steps") or {})
    step = dict(steps[step_id])
    step["status"] = "failed"
    step["result"] = str((state.get("results") or {}).get(step_id, {}).get("output") or "")
    steps[step_id] = step
    receipts = dict(state.get("effect_receipts") or {})
    receipts[receipt["operation_key"]] = receipt
    return {
        "steps": steps,
        "effect_receipts": receipts,
        "run_status": "waiting_user",
        "updated_at": utc_now(),
    }


async def _recovery_gate(state: WorkflowState) -> dict:
    choice = interrupt(
        {
            "run_id": state.get("run_id"),
            "step_id": state.get("current_step_id"),
            "error": state.get("last_error"),
            "actions": ["retry", "modify", "skip", "abort"],
        }
    )
    payload = choice if isinstance(choice, dict) else {"action": str(choice or "")}
    action = str(payload.get("action") or "retry").lower()
    if action not in {"retry", "modify", "skip", "abort"}:
        action = "retry"
    step_id = state.get("current_step_id")
    steps = dict(state.get("steps") or {})
    if step_id and step_id in steps:
        step = dict(steps[step_id])
        if action == "skip":
            step["status"] = "skipped"
        elif action in {"retry", "modify"}:
            step["status"] = "pending"
            if action == "modify":
                if payload.get("title"):
                    step["title"] = str(payload["title"])
                if payload.get("detail"):
                    step["detail"] = str(payload["detail"])
        steps[step_id] = step
    return {
        "steps": steps,
        "recovery_action": action,
        "run_status": "failed" if action == "abort" else "running",
        "last_error": state.get("last_error") if action == "abort" else None,
        "current_step_id": None if action == "skip" else step_id,
        "updated_at": utc_now(),
    }


def _after_recovery(state: WorkflowState) -> str:
    action = state.get("recovery_action", "retry")
    if action == "abort":
        return "finalize_failed"
    if action == "skip":
        return "select_step"
    return "begin_step_transaction"


async def _finalize_success(state: WorkflowState) -> dict:
    response = state.get("final_response", "").strip() or "任务已完成。"
    return {
        "run_status": "completed",
        "current_step_id": None,
        "last_error": None,
        "final_response": response,
        "updated_at": utc_now(),
    }


async def _finalize_failed(state: WorkflowState) -> dict:
    response = state.get("final_response", "").strip()
    reason = state.get("reflection_reason") or (state.get("last_error") or {}).get("message") or "任务已终止。"
    if reason and reason not in response:
        response = f"{response}\n\n任务未完成：{reason}".strip()
    return {
        "run_status": "failed",
        "current_step_id": None,
        "final_response": response,
        "updated_at": utc_now(),
    }


def build_workflow_graph(checkpointer, execute_step: StepExecutor):
    builder = StateGraph(WorkflowState)
    builder.add_node("init_run", _init_run)
    builder.add_node("plan", _plan)
    builder.add_node("select_step", _select_step)
    builder.add_node("begin_step_transaction", _begin_step)
    builder.add_node("execute_agent", _make_execute_node(execute_step))
    builder.add_node("validate_step", _validate_step)
    builder.add_node("retry_step", _retry_step)
    builder.add_node("commit_step", _commit_step)
    builder.add_node("reflect", _reflect)
    builder.add_node("compensate", _compensate)
    builder.add_node("recovery_gate", _recovery_gate)
    builder.add_node("finalize_success", _finalize_success)
    builder.add_node("finalize_failed", _finalize_failed)

    builder.add_edge(START, "init_run")
    builder.add_edge("init_run", "plan")
    builder.add_edge("plan", "select_step")
    builder.add_conditional_edges("select_step", _after_select)
    builder.add_edge("begin_step_transaction", "execute_agent")
    builder.add_edge("execute_agent", "validate_step")
    builder.add_conditional_edges("validate_step", _after_validate)
    builder.add_edge("retry_step", "execute_agent")
    builder.add_edge("commit_step", "reflect")
    builder.add_conditional_edges("reflect", _after_reflect)
    builder.add_edge("compensate", "recovery_gate")
    builder.add_conditional_edges("recovery_gate", _after_recovery)
    builder.add_edge("finalize_success", END)
    builder.add_edge("finalize_failed", END)
    return builder.compile(checkpointer=checkpointer)
