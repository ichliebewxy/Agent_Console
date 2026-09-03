"""HTTP facade for the existing hybrid RAG pipeline used by the pi tool."""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.retrieval.rag_pipeline import run_rag_graph


router = APIRouter()


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)


@router.post("/knowledge/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    try:
        result = await asyncio.to_thread(run_rag_graph, request.query.strip())
        return result if isinstance(result, dict) else {"docs": [], "rag_trace": {}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识库检索失败: {exc}") from exc
