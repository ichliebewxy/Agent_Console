"""Session history routes."""
from fastapi import APIRouter, HTTPException

from agent import storage
from schemas import MessageInfo, SessionDeleteResponse, SessionInfo, SessionListResponse, SessionMessagesResponse

router = APIRouter()


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
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return SessionListResponse(sessions=sessions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/sessions/{user_id}/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(user_id: str, session_id: str):
    try:
        if not storage.delete_session(user_id, session_id):
            raise HTTPException(status_code=404, detail="会话不存在")
        return SessionDeleteResponse(session_id=session_id, message="成功删除会话")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
