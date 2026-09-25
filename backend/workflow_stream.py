"""Translate durable graph updates into the existing browser SSE event model."""

from __future__ import annotations

from checkpoint_service import get_workflow, register_run, workflow_config
from workflow_state import plan_payload, public_workflow_state


async def stream_workflow_events(initial_state: dict):
    workflow = get_workflow()
    run_id = initial_state["run_id"]
    state = dict(initial_state)
    await register_run(state)
    yield {
        "type": "workflow",
        "run_id": run_id,
        "status": "planning",
        "resumable": True,
    }
    yield {
        "type": "plan_step",
        "step": {"icon": "🧭", "phase": "plan", "label": "正在规划任务拆解", "detail": ""},
    }

    async for chunk in workflow.astream(
        initial_state,
        workflow_config(run_id),
        stream_mode="updates",
        durability="sync",
    ):
        if not isinstance(chunk, dict):
            continue
        for node_name, update in chunk.items():
            if node_name == "__interrupt__":
                raw_interrupts = update if isinstance(update, (list, tuple)) else [update]
                yield {
                    "type": "workflow",
                    "run_id": run_id,
                    "status": "waiting_user",
                    "interrupts": [getattr(item, "value", item) for item in raw_interrupts],
                    "resumable": True,
                }
                continue
            if not isinstance(update, dict):
                continue
            state.update(update)
            if node_name == "plan":
                yield {"type": "plan", "run_id": run_id, **plan_payload(state)}
                yield {
                    "type": "plan_step",
                    "step": {
                        "icon": "📋",
                        "phase": "plan",
                        "label": f"规划完成：拆分为 {len(state.get('step_order') or [])} 个子任务",
                        "detail": state.get("objective", ""),
                    },
                }
            elif node_name == "begin_step_transaction":
                step_id = state.get("current_step_id")
                step = (state.get("steps") or {}).get(step_id, {})
                index = (state.get("step_order") or []).index(step_id) if step_id in (state.get("step_order") or []) else 0
                yield {
                    "type": "execute",
                    "step_id": step_id,
                    "status": "in_progress",
                    "title": step.get("title", ""),
                    "index": index,
                    "total": len(state.get("step_order") or []),
                }
                yield {
                    "type": "plan_step",
                    "step": {
                        "icon": "▶",
                        "phase": "execute",
                        "label": f"执行 {index + 1}/{len(state.get('step_order') or [])}：{step.get('title', '')}",
                        "detail": step.get("detail", ""),
                    },
                }
            elif node_name == "execute_agent":
                step_id = state.get("current_step_id")
                result = (state.get("results") or {}).get(step_id, {})
                for event in result.get("tool_events") or []:
                    yield {"type": "tool_step", "step": event}
                output = str(result.get("output") or "")
                step = (state.get("steps") or {}).get(step_id, {})
                if output:
                    yield {"type": "content", "content": f"### {step.get('title', '步骤')}\n{output}\n"}
            elif node_name == "validate_step" and state.get("validation_status") != "success":
                step_id = state.get("current_step_id")
                step = (state.get("steps") or {}).get(step_id, {})
                yield {
                    "type": "execute",
                    "step_id": step_id,
                    "status": "failed" if state.get("validation_status") == "recover" else "in_progress",
                    "title": step.get("title", ""),
                    "result": ((state.get("last_error") or {}).get("message") or "")[:200],
                }
            elif node_name == "commit_step":
                step_id = state.get("last_committed_step_id")
                step = (state.get("steps") or {}).get(step_id, {})
                yield {
                    "type": "execute",
                    "step_id": step_id,
                    "status": "done",
                    "title": step.get("title", ""),
                    "result": str(step.get("result") or "")[:200],
                }
            elif node_name == "reflect":
                yield {
                    "type": "reflect",
                    "decision": state.get("reflection_decision", "continue"),
                    "reason": state.get("reflection_reason", ""),
                    "adjusted": bool(state.get("reflection_notes")),
                }
                if state.get("reflection_notes"):
                    yield {"type": "plan", "run_id": run_id, **plan_payload(state)}
            elif node_name in {"finalize_success", "finalize_failed"}:
                yield {
                    "type": "workflow",
                    "run_id": run_id,
                    "status": state.get("run_status"),
                    "resumable": state.get("run_status") != "completed",
                }

    await register_run(public_workflow_state(state))
