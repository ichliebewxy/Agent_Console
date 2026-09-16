"""Durable workflow inspection, recovery, and time-travel routes."""

from fastapi import APIRouter, HTTPException, Query

from agent import storage
from checkpoint_service import (
    fork_run,
    get_run_history,
    get_run_state,
    list_runs,
    resume_run,
)
from schemas import (
    WorkflowActionRequest,
    WorkflowForkRequest,
    WorkflowHistoryResponse,
    WorkflowRunListResponse,
    WorkflowStateResponse,
)
from runtime_context import session_async_lock

router = APIRouter(prefix="/runs", tags=["workflow-runs"])


def _project_to_conversation(state: dict) -> None:
    storage.update_workflow_projection(
        state.get("user_id", ""),
        state.get("session_id", ""),
        state.get("run_id", ""),
        state,
    )


@router.get("", response_model=WorkflowRunListResponse)
async def get_runs(user_id: str | None = None, session_id: str | None = None):
    return WorkflowRunListResponse(runs=await list_runs(user_id, session_id))


@router.get("/{run_id}", response_model=WorkflowStateResponse)
async def get_run(run_id: str):
    try:
        return WorkflowStateResponse(state=await get_run_state(run_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="工作流运行不存在")


@router.get("/{run_id}/checkpoints", response_model=WorkflowHistoryResponse)
async def get_checkpoints(run_id: str, limit: int = Query(100, ge=1, le=500)):
    checkpoints = await get_run_history(run_id, limit)
    if not checkpoints:
        raise HTTPException(status_code=404, detail="工作流运行不存在")
    return WorkflowHistoryResponse(checkpoints=checkpoints)


@router.post("/{run_id}/resume", response_model=WorkflowStateResponse)
async def resume(run_id: str, request: WorkflowActionRequest):
    try:
        current = await get_run_state(run_id)
        async with session_async_lock(current["user_id"], current["session_id"]):
            state = await resume_run(run_id, request.model_dump(exclude_none=True))
        _project_to_conversation(state)
        return WorkflowStateResponse(state=state)
    except KeyError:
        raise HTTPException(status_code=404, detail="工作流运行不存在")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{run_id}/fork", response_model=WorkflowStateResponse)
async def fork(run_id: str, request: WorkflowForkRequest):
    try:
        current = await get_run_state(run_id)
        async with session_async_lock(current["user_id"], current["session_id"]):
            state = await fork_run(
                run_id,
                request.checkpoint_id,
                request.patch,
                continue_run=request.continue_run,
            )
        _project_to_conversation(state)
        return WorkflowStateResponse(state=state)
    except KeyError:
        raise HTTPException(status_code=404, detail="运行或检查点不存在")


@router.post("/{run_id}/rollback", response_model=WorkflowStateResponse)
async def rollback(run_id: str, request: WorkflowForkRequest):
    """Alias for checkpoint fork/time travel with optional continued execution."""
    return await fork(run_id, request)
