"""Session artifact listing and safe file downloads."""
import asyncio
import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from artifact_service import (
    list_session_artifacts,
    open_session_artifact,
    verify_artifact_access,
)
from runtime_context import session_async_lock
from schemas import ArtifactInfo, ArtifactListResponse


router = APIRouter()


@router.get(
    "/sessions/{user_id}/{session_id}/artifacts",
    response_model=ArtifactListResponse,
)
async def list_artifacts(
    user_id: str,
    session_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    token: str | None = Query(default=None),
):
    if not verify_artifact_access(user_id, session_id, token or ""):
        raise HTTPException(status_code=404, detail="Artifact session not found")
    async with session_async_lock(user_id, session_id):
        rows = await asyncio.to_thread(
            list_session_artifacts,
            user_id,
            session_id,
            limit,
        )
    return ArtifactListResponse(artifacts=[ArtifactInfo(**row) for row in rows])


@router.get("/sessions/{user_id}/{session_id}/artifacts/{artifact_path:path}")
async def download_artifact(
    user_id: str,
    session_id: str,
    artifact_path: str,
    token: str | None = Query(default=None),
):
    if not verify_artifact_access(user_id, session_id, token or ""):
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        async with session_async_lock(user_id, session_id):
            handle, path, stat = await asyncio.to_thread(
                open_session_artifact,
                user_id,
                session_id,
                artifact_path,
            )
    except (FileNotFoundError, OSError, ValueError):
        raise HTTPException(status_code=404, detail="Artifact not found")

    def chunks():
        try:
            while block := handle.read(64 * 1024):
                yield block
        finally:
            handle.close()

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded_name = quote(path.name, safe="")
    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(stat.st_size),
            "X-Content-Type-Options": "nosniff",
        },
    )
