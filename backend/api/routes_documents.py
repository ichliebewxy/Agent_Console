"""Knowledge-base document routes."""
import asyncio
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.knowledge.document_loader import DocumentLoader
from backend.knowledge.embedding import embedding_service
from backend.knowledge.milvus_client import MilvusManager
from backend.knowledge.milvus_writer import MilvusWriter
from backend.knowledge.parent_chunk_store import ParentChunkStore
from backend.common.schemas import DocumentDeleteResponse, DocumentInfo, DocumentListResponse, DocumentUploadResponse

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR.parent.parent / "tmp" / "knowledge" / "documents"
VALID_EXTS = (".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".txt")
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

router = APIRouter()
loader = DocumentLoader()
parent_chunk_store = ParentChunkStore()
milvus_manager = MilvusManager()
milvus_writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus_manager)


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    try:
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
    filename = _validated_filename(file.filename or "")
    if not filename.lower().endswith(VALID_EXTS):
        raise HTTPException(status_code=400, detail=f"不支持的文件格式。仅支持: {', '.join(VALID_EXTS)}")
    staged_path = None
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        staged_path = await _save_upload(file, filename)
        final_path = UPLOAD_DIR / filename
        new_docs = await asyncio.to_thread(loader.load_document, str(staged_path), filename)
        if not new_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")

        for document in new_docs:
            document["file_path"] = str(final_path)
        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")

        # Parsing happens against a staging file. Only replace the saved source
        # after successful extraction, so a bad re-upload cannot destroy it.
        os.replace(staged_path, final_path)
        staged_path = None
        await asyncio.to_thread(milvus_manager.init_collection)
        await asyncio.to_thread(_delete_existing, filename)
        try:
            await asyncio.to_thread(milvus_writer.write_documents, leaf_docs)
            await asyncio.to_thread(parent_chunk_store.upsert_documents, parent_docs)
        except Exception:
            await asyncio.to_thread(_delete_existing, filename)
            raise
        return DocumentUploadResponse(
            filename=filename,
            chunks_processed=len(leaf_docs),
            message=f"成功处理 {filename}！叶子分片 {len(leaf_docs)} 个，父级片段 {len(parent_docs)} 个。",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {exc}")
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str):
    try:
        milvus_manager.init_collection()
        count = _delete_existing(filename)
        return DocumentDeleteResponse(filename=filename, chunks_deleted=count, message=f"成功删除文档 {filename} 的向量数据")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {exc}")


def _filename_filter(filename: str) -> str:
    escaped = filename.replace("\\", "\\\\").replace('"', '\\"')
    return f'filename == "{escaped}"'


def _delete_existing(filename: str) -> int:
    filter_expr = _filename_filter(filename)
    delete_count = 0
    try:
        rows = milvus_manager.query(filter_expr=filter_expr, output_fields=["text"], limit=10000)
        embedding_service.increment_remove_documents([row.get("text", "") for row in rows])
        result = milvus_manager.delete(filter_expr)
        delete_count = result.get("delete_count", 0) if isinstance(result, dict) else 0
    except Exception:
        pass
    try:
        parent_chunk_store.delete_by_filename(filename)
    except Exception:
        pass
    return delete_count


def _validated_filename(raw_filename: str) -> str:
    filename = Path(raw_filename).name
    reserved_name = filename.split(".", 1)[0].upper()
    if (
        not filename
        or filename != raw_filename
        or filename in {".", ".."}
        or filename.rstrip(" .") != filename
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename)
        or reserved_name in WINDOWS_RESERVED_NAMES
    ):
        raise HTTPException(status_code=400, detail="文件名无效")
    return filename


async def _save_upload(file: UploadFile, filename: str) -> Path:
    suffix = Path(filename).suffix.lower()
    staged_path = UPLOAD_DIR / f".{uuid4().hex}.uploading{suffix}"
    total_size = 0
    try:
        with open(staged_path, "wb") as destination:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="文件大小不能超过 50MB")
                destination.write(chunk)
        return staged_path
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise
