"""Session history routes."""
import asyncio

import memory_service
from agent import storage
from checkpoint_service import delete_session_runs
from fastapi import APIRouter, HTTPException
from memory_scope import namespace_for_scope
from runtime_context import delete_session_files, session_async_lock
from schemas import (
    MessageInfo,
    SessionDeleteResponse,
    SessionInfo,
    SessionListResponse,
    SessionMessagesResponse,
    SessionResourcesRequest,
)
from session_resources import SESSION_RESOURCES
from skill_service import SKILL_REGISTRY

router = APIRouter()


@router.get("/sessions/{user_id}/{session_id}/resources")
async def get_session_resources(user_id: str, session_id: str):
    try:
        from dataclasses import asdict
        return asdict(SESSION_RESOURCES.get(user_id, session_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/sessions/{user_id}/{session_id}/resources")
async def put_session_resources(user_id: str, session_id: str, request: SessionResourcesRequest):
    from dataclasses import asdict

    from session_resources import validate_resources
    try:
        value = request.model_dump()
        resources = validate_resources(value)
        unknown = set(resources.skills or ()) - set(SKILL_REGISTRY.names)
        if unknown:
            raise ValueError(f"Unknown skills: {', '.join(sorted(unknown))}")
        async with session_async_lock(user_id, session_id):
            return asdict(SESSION_RESOURCES.put(user_id, session_id, value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sessions/{user_id}/{session_id}", response_model=SessionMessagesResponse)
async def get_session_messages(user_id: str, session_id: str):
    try:
        data = storage._load()
        session_data = data.get(user_id, {}).get(session_id, {})
        messages = [
            MessageInfo(
                type=item["type"],
                content=item["content"],
                timestamp=item["timestamp"],
                rag_trace=item.get("rag_trace"),
                artifacts=item.get("artifacts") or [],
                plan=item.get("plan"),
                workflow=item.get("workflow"),
            )
            for item in session_data.get("messages", [])
        ]
        return SessionMessagesResponse(messages=messages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sessions/{user_id}", response_model=SessionListResponse)
async def list_sessions(user_id: str):
    try:
        data = storage._load()
        sessions = [
            SessionInfo(
                session_id=session_id,
                updated_at=session_data.get("updated_at", ""),
                message_count=len(session_data.get("messages", [])),
            )
            for session_id, session_data in data.get(user_id, {}).items()
        ]
        sessions.extend(
            SessionInfo(session_id=session_id, updated_at="", message_count=0)
            for session_id in SESSION_RESOURCES.list_sessions(user_id)
            if session_id not in data.get(user_id, {})
        )
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return SessionListResponse(sessions=sessions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/sessions/{user_id}/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(user_id: str, session_id: str):
    try:
        async with session_async_lock(user_id, session_id):
            has_history = session_id in storage.list_sessions(user_id)
            if not has_history and not SESSION_RESOURCES.contains(user_id, session_id):
                raise HTTPException(status_code=404, detail="会话不存在")
            resources = SESSION_RESOURCES.get(user_id, session_id)
            session_namespace = namespace_for_scope(user_id, session_id, resources, "session")
            await asyncio.to_thread(memory_service.delete_all, session_namespace)
            await asyncio.to_thread(delete_session_files, user_id, session_id)
            await delete_session_runs(user_id, session_id)
            if has_history and not storage.delete_session(user_id, session_id):
                raise HTTPException(status_code=404, detail="会话不存在")
            SESSION_RESOURCES.delete(user_id, session_id)
        return SessionDeleteResponse(session_id=session_id, message="成功删除会话")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
