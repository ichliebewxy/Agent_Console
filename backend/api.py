"""API router aggregation."""
from fastapi import APIRouter

from routes_chat import router as chat_router
from routes_config import router as config_router
from routes_artifacts import router as artifacts_router
from routes_documents import router as documents_router
from routes_memory import router as memory_router
from routes_sessions import router as sessions_router

router = APIRouter()
router.include_router(artifacts_router)
router.include_router(config_router)
router.include_router(sessions_router)
router.include_router(chat_router)
router.include_router(documents_router)
router.include_router(memory_router)
