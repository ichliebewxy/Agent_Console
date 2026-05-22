"""API router aggregation."""
from fastapi import APIRouter

from routes_chat import router as chat_router
from routes_documents import router as documents_router
from routes_ops import router as ops_router
from routes_sessions import router as sessions_router

router = APIRouter()
router.include_router(ops_router)
router.include_router(sessions_router)
router.include_router(chat_router)
router.include_router(documents_router)
