"""Knowledge/memory sidecar for the pi-based Node application.

The former LangChain chat runtime is intentionally not initialized here.  This
service only owns the proven document parsing, chunking, embedding, Milvus RAG,
and optional mem0 APIs that the new pi host calls.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config.runtime_data import configure_caches, migrate_knowledge

configure_caches()
migrate_knowledge()

from backend.knowledge.embedding import embedding_service
from backend.api.routes_documents import router as documents_router
from backend.api.routes_knowledge import router as knowledge_router
from backend.api.routes_memory import router as memory_router
from backend.config.settings import MILVUS_DENSE_DIM


@asynccontextmanager
async def lifespan(_: FastAPI):
    info = await asyncio.to_thread(embedding_service.warm_up)
    if info["dim"] != MILVUS_DENSE_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: got {info['dim']}, expected {MILVUS_DENSE_DIM}"
        )
    yield


app = FastAPI(title="二狗子助手知识库服务", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)
app.include_router(knowledge_router)
app.include_router(memory_router)


@app.get("/health")
async def health():
    return {"ok": True, "service": "rag"}
