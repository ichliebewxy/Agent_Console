"""Human review and tool-failure routes."""
from fastapi import APIRouter, HTTPException

from agent import retry_mcp_init_async
from ops_store import review_store, tool_failure_store
from schemas import (
    HumanReviewCreateRequest,
    HumanReviewInfo,
    HumanReviewListResponse,
    HumanReviewUpdateRequest,
    ToolFailureInfo,
    ToolFailureListResponse,
    ToolFailureUpdateRequest,
)

router = APIRouter()


@router.get("/reviews", response_model=HumanReviewListResponse)
async def list_reviews(status: str = None, limit: int = 100):
    rows = review_store.list(status=status, limit=limit)
    return HumanReviewListResponse(reviews=[HumanReviewInfo(**row) for row in rows])


@router.post("/reviews", response_model=HumanReviewInfo)
async def create_review(request: HumanReviewCreateRequest):
    return HumanReviewInfo(**review_store.create(request.model_dump()))


@router.patch("/reviews/{review_id}", response_model=HumanReviewInfo)
async def update_review(review_id: str, request: HumanReviewUpdateRequest):
    if request.status not in {"pending", "approved", "rejected", "needs_revision"}:
        raise HTTPException(status_code=400, detail="Invalid review status")
    row = review_store.update(review_id, request.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    return HumanReviewInfo(**row)


@router.get("/tool-failures", response_model=ToolFailureListResponse)
async def list_tool_failures(status: str = None, limit: int = 100):
    rows = tool_failure_store.list(status=status, limit=limit)
    return ToolFailureListResponse(failures=[ToolFailureInfo(**row) for row in rows])


@router.patch("/tool-failures/{failure_id}", response_model=ToolFailureInfo)
async def update_tool_failure(failure_id: str, request: ToolFailureUpdateRequest):
    if request.status not in {"open", "retry_requested", "resolved", "ignored"}:
        raise HTTPException(status_code=400, detail="Invalid failure status")
    existing = tool_failure_store.get(failure_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Tool failure not found")
    if request.status == "retry_requested" and existing.get("tool_name") == "amap_mcp_init":
        return await _retry_mcp_failure(failure_id, request)
    row = tool_failure_store.update(failure_id, request.model_dump())
    return ToolFailureInfo(**row)


async def _retry_mcp_failure(failure_id: str, request: ToolFailureUpdateRequest):
    try:
        result = await retry_mcp_init_async()
        note = f"{request.callback_note or ''}\nMCP 初始化重试成功，已加载 {result['mcp_tool_count']} 个工具。".strip()
        row = tool_failure_store.update(failure_id, {"status": "resolved", "callback_note": note})
    except Exception as exc:
        note = f"{request.callback_note or ''}\nMCP 初始化重试失败：{exc}".strip()
        row = tool_failure_store.update(failure_id, {"status": "open", "callback_note": note})
    return ToolFailureInfo(**row)
