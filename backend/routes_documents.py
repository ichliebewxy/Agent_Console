"""Knowledge-base document routes."""
import logging
import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from document_loader import DocumentLoader
from embedding import EmbeddingService
from milvus_client import MilvusManager
from milvus_writer import MilvusWriter
from parent_chunk_store import ParentChunkStore
from schemas import DocumentDeleteResponse, DocumentInfo, DocumentListResponse, DocumentUploadResponse
from services.ingestion_service import LocalIngestionTracker
from services.upload_security import (
    DEFAULT_ALLOWED_EXTENSIONS,
    UploadTooLargeError,
    UploadValidationError,
    content_sha256,
    normalize_upload_filename,
    validate_upload_size,
)
from settings import MAX_UPLOAD_BYTES

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR.parent / "data" / "documents"
VALID_EXTS = DEFAULT_ALLOWED_EXTENSIONS

router = APIRouter()
logger = logging.getLogger(__name__)


@lru_cache
def get_loader() -> DocumentLoader:
    return DocumentLoader()


@lru_cache
def get_parent_chunk_store() -> ParentChunkStore:
    return ParentChunkStore()


@lru_cache
def get_milvus_manager() -> MilvusManager:
    return MilvusManager()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


@lru_cache
def get_milvus_writer() -> MilvusWriter:
    return MilvusWriter(
        embedding_service=get_embedding_service(),
        milvus_manager=get_milvus_manager(),
    )


@lru_cache
def get_ingestion_tracker() -> LocalIngestionTracker:
    return LocalIngestionTracker()


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    try:
        milvus_manager = get_milvus_manager()
        milvus_manager.init_collection()
        rows = milvus_manager.query(output_fields=["filename", "file_type"], limit=10000)
        file_stats = {}
        for item in rows:
            filename = item.get("filename", "")
            file_stats.setdefault(filename, {
                "filename": filename,
                "file_type": item.get("file_type", ""),
                "chunk_count": 0,
            })
            file_stats[filename]["chunk_count"] += 1
        return DocumentListResponse(documents=[DocumentInfo(**stats) for stats in file_stats.values()])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {exc}")


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    job = None
    try:
        ingestion_tracker = get_ingestion_tracker()
        milvus_manager = get_milvus_manager()
        parent_chunk_store = get_parent_chunk_store()
        milvus_writer = get_milvus_writer()
        loader = get_loader()

        filename = normalize_upload_filename(file.filename, VALID_EXTS)
        content = await file.read()
        validate_upload_size(content, MAX_UPLOAD_BYTES)
        sha256 = content_sha256(content)

        existing = ingestion_tracker.find_ready_by_hash(sha256)
        if existing:
            return DocumentUploadResponse(
                filename=filename,
                chunks_processed=0,
                status="deduplicated",
                doc_id=existing.get("id"),
                sha256=sha256,
                message=(
                    f"检测到重复文档内容，已存在为 {existing.get('filename')}；"
                    "本次未重复写入向量库。"
                ),
            )

        job = ingestion_tracker.start(
            filename=filename,
            sha256=sha256,
            content_type=file.content_type or "",
        )
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        milvus_manager.init_collection()
        _delete_existing(filename, milvus_manager, parent_chunk_store)
        file_path = _save_upload(content, filename)
        new_docs = loader.load_document(str(file_path), filename)
        if not new_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")
        parent_chunk_store.upsert_documents(parent_docs)
        milvus_writer.write_documents(leaf_docs)
        ingestion_tracker.mark_ready(job["id"], chunk_count=len(leaf_docs), parent_chunk_count=len(parent_docs))
        return DocumentUploadResponse(
            filename=filename,
            chunks_processed=len(leaf_docs),
            status="ready",
            doc_id=job["id"],
            sha256=sha256,
            message=f"成功处理 {filename}！叶子分片 {len(leaf_docs)} 个，父级片段 {len(parent_docs)} 个。",
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException as exc:
        if job:
            ingestion_tracker.mark_failed(job["id"], str(exc.detail))
        raise
    except Exception as exc:
        if job:
            ingestion_tracker.mark_failed(job["id"], str(exc))
        raise HTTPException(status_code=500, detail=f"文档上传失败: {exc}")


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str):
    try:
        ingestion_tracker = get_ingestion_tracker()
        milvus_manager = get_milvus_manager()
        parent_chunk_store = get_parent_chunk_store()

        filename = normalize_upload_filename(filename, VALID_EXTS)
        milvus_manager.init_collection()
        result = milvus_manager.delete(f'filename == "{filename}"')
        parent_chunk_store.delete_by_filename(filename)
        ingestion_tracker.delete_by_filename(filename)
        count = result.get("delete_count", 0) if isinstance(result, dict) else 0
        return DocumentDeleteResponse(filename=filename, chunks_deleted=count, message=f"成功删除文档 {filename} 的向量数据")
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {exc}")


def _delete_existing(filename: str, milvus_manager: MilvusManager, parent_chunk_store: ParentChunkStore) -> None:
    try:
        milvus_manager.delete(f'filename == "{filename}"')
    except Exception as exc:
        logger.warning("Failed to delete existing Milvus rows for %s: %s", filename, exc)
    try:
        parent_chunk_store.delete_by_filename(filename)
    except Exception as exc:
        logger.warning("Failed to delete existing parent chunks for %s: %s", filename, exc)


def _save_upload(content: bytes, filename: str) -> Path:
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path
