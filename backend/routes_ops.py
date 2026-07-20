"""Read-only tool-failure runtime records."""
from fastapi import APIRouter

from ops_store import tool_failure_store
from schemas import ToolFailureInfo, ToolFailureListResponse


router = APIRouter()


@router.get("/tool-failures", response_model=ToolFailureListResponse)
async def list_tool_failures(status: str = None, limit: int = 100):
    rows = tool_failure_store.list(status=status, limit=limit)
    return ToolFailureListResponse(failures=[ToolFailureInfo(**row) for row in rows])
