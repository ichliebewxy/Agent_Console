"""mem0 长期记忆的 REST 接口，供前端“记忆”面板调用。

路由约定：
- GET    /memory/{user_id}          列出用户全部记忆
- POST   /memory/{user_id}          手动新增一条记忆
- PUT    /memory/{memory_id}        更新某条记忆
- DELETE /memory/{memory_id}        删除某条记忆
- DELETE /memory/user/{user_id}     清空某用户记忆
- GET    /memory/status             记忆服务状态
"""

import asyncio

from fastapi import APIRouter, HTTPException

import memory_service
from schemas import (
    MemoryAddRequest,
    MemoryAddResponse,
    MemoryDeleteResponse,
    MemoryInfo,
    MemoryListResponse,
    MemoryStatusResponse,
    MemoryUpdateRequest,
)

router = APIRouter()


def _to_info(item) -> MemoryInfo:
    return MemoryInfo(
        id=item.get("id", ""),
        memory=item.get("memory", ""),
        created_at=item.get("created_at"),
        updated_at=item.get("updated_at"),
        metadata=item.get("metadata"),
    )


@router.get("/memory/status", response_model=MemoryStatusResponse)
async def memory_status():
    return MemoryStatusResponse(**memory_service.status())


@router.get("/memory/{user_id}", response_model=MemoryListResponse)
async def list_memories(user_id: str):
    try:
        results = await asyncio.to_thread(memory_service.get_all, user_id)
        memories = [_to_info(item) for item in results]
        # 按更新时间倒序，便于前端展示最近记忆在前。
        memories.sort(key=lambda m: m.updated_at or "", reverse=True)
        return MemoryListResponse(
            memories=memories,
            enabled=memory_service.is_enabled(),
            initialized=memory_service.status()["initialized"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取记忆列表失败: {exc}")


@router.post("/memory/{user_id}", response_model=MemoryAddResponse)
async def add_memory(user_id: str, request: MemoryAddRequest):
    text = request.memory.strip()
    if not text:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="记忆内容过长（最多 4000 字符）")
    try:
        result = await asyncio.to_thread(
            memory_service.add_memory, text, user_id, None, request.infer
        )
        results = result.get("results", []) if isinstance(result, dict) else []
        result_msg = "已记录记忆" if request.infer else "已记录记忆（原文照存）"
        return MemoryAddResponse(
            message=result_msg,
            memory=text,
            results=results,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"新增记忆失败: {exc}")


@router.put("/memory/{memory_id}", response_model=MemoryDeleteResponse)
async def update_memory(memory_id: str, request: MemoryUpdateRequest):
    text = request.memory.strip()
    if not text:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    try:
        await asyncio.to_thread(memory_service.update_memory, memory_id, text)
        return MemoryDeleteResponse(memory_id=memory_id, message="记忆已更新")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新记忆失败: {exc}")


@router.delete("/memory/user/{user_id}", response_model=MemoryDeleteResponse)
async def clear_user_memories(user_id: str):
    """清空某用户的全部记忆。注意：此路由须在 /memory/{memory_id} 之前声明无关，
    FastAPI 按路径段数区分，两者不会冲突。"""
    try:
        await asyncio.to_thread(memory_service.delete_all, user_id)
        return MemoryDeleteResponse(memory_id=user_id, message="已清空该用户全部记忆")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清空记忆失败: {exc}")


@router.delete("/memory/{memory_id}", response_model=MemoryDeleteResponse)
async def delete_memory(memory_id: str):
    try:
        await asyncio.to_thread(memory_service.delete_memory, memory_id)
        return MemoryDeleteResponse(memory_id=memory_id, message="记忆已删除")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除记忆失败: {exc}")
