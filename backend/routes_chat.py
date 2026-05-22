"""Chat API routes."""
import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agent import chat_with_agent, chat_with_agent_stream
from schemas import ChatRequest, ChatResponse

router = APIRouter()


def _raise_model_error(error: Exception):
    message = str(error)
    match = re.search(r"Error code:\s*(\d{3})", message)
    if not match:
        raise HTTPException(status_code=500, detail=message)
    code = int(match.group(1))
    if code == 429:
        raise HTTPException(
            status_code=429,
            detail=f"上游模型服务触发限流/额度限制（429）。请检查账号额度/模型状态。\n原始错误：{message}",
        )
    raise HTTPException(status_code=code, detail=message)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        return ChatResponse(**chat_with_agent(request.message, request.user_id, request.session_id))
    except HTTPException:
        raise
    except Exception as exc:
        _raise_model_error(exc)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    async def event_generator():
        try:
            async for chunk in chat_with_agent_stream(request.message, request.user_id, request.session_id):
                yield chunk
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
