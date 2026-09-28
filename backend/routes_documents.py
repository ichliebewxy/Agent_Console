"""Knowledge-base document routes."""
import asyncio
import os
import re
import threading
import weakref
from pathlib import Path
from uuid import uuid4

from document_loader import DocumentLoader
from document_versions import DocumentVersionStore, version_chunk_prefix, version_filter
from embedding import embedding_service
from fastapi import APIRouter, File, HTTPException, UploadFile
from milvus_client import MilvusManager
from milvus_writer import MilvusWriter
from parent_chunk_store import ParentChunkStore
from schemas import (
    DocumentDeleteResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadResponse,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR.parent / "data" / "documents"
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
document_versions = DocumentVersionStore()
_DOCUMENT_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
_DOCUMENT_LOCKS_GUARD = threading.Lock()


def _document_lock(filename: str) -> asyncio.Lock:
    with _DOCUMENT_LOCKS_GUARD:
        lock = _DOCUMENT_LOCKS.get(filename)
        if lock is None:
            lock = asyncio.Lock()
            _DOCUMENT_LOCKS[filename] = lock
        return lock


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    try:
        milvus_manager.init_collection()
        rows = milvus_manager.query(
            filter_expr=document_versions.active_filter(),
            output_fields=["filename", "file_type"],
            limit=10000,
        )
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
        async with _document_lock(filename):
            result = await _publish_document(staged_path, filename)
            staged_path = None
            return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {exc}")
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str):
    filename = _validated_filename(filename)
    try:
        async with _document_lock(filename):
            await asyncio.to_thread(milvus_manager.init_collection)
            count = await asyncio.to_thread(_delete_existing, filename)
            await asyncio.to_thread(document_versions.remove, filename)
        return DocumentDeleteResponse(filename=filename, chunks_deleted=count, message=f"成功删除文档 {filename} 的向量数据")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {exc}")


def _filename_filter(filename: str) -> str:
    escaped = filename.replace("\\", "\\\\").replace('"', '\\"')
    return f'filename == "{escaped}"'


def _delete_existing(filename: str) -> int:
    filter_expr = _filename_filter(filename)
    rows = milvus_manager.query(filter_expr=filter_expr, output_fields=["text"], limit=10000)
    result = milvus_manager.delete(filter_expr)
    delete_count = result.get("delete_count", 0) if isinstance(result, dict) else 0
    embedding_service.increment_remove_documents([row.get("text", "") for row in rows])
    parent_chunk_store.delete_by_filename(filename)
    return delete_count


def _delete_version(filename: str, version: str) -> int:
    filter_expr = version_filter(filename, version)
    rows = milvus_manager.query(filter_expr=filter_expr, output_fields=["text"], limit=10000)
    result = milvus_manager.delete(filter_expr)
    embedding_service.increment_remove_documents([row.get("text", "") for row in rows])
    parent_chunk_store.delete_by_chunk_prefix(version_chunk_prefix(filename, version))
    source_path = UPLOAD_DIR / ".versions" / version / filename if version else UPLOAD_DIR / filename
    source_path.unlink(missing_ok=True)
    if version:
        try:
            source_path.parent.rmdir()
        except FileNotFoundError:
            pass
    return result.get("delete_count", 0) if isinstance(result, dict) else 0


def _drain_pending_cleanup(filename: str) -> None:
    active = document_versions.active_version(filename)
    for version in document_versions.pending_cleanup(filename):
        if version == active:
            continue
        try:
            _delete_version(filename, version)
            document_versions.clear_cleanup(filename, version)
        except Exception as exc:
            print(f"[documents] Version cleanup deferred: {exc}")


async def _publish_document(staged_path: Path, filename: str) -> DocumentUploadResponse:
    new_docs = await asyncio.to_thread(loader.load_document, str(staged_path), filename)
    if not new_docs:
        raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")
    leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
    if not leaf_docs:
        raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")

    await asyncio.to_thread(milvus_manager.init_collection)
    old_version = await asyncio.to_thread(document_versions.prepare, filename)
    await asyncio.to_thread(_drain_pending_cleanup, filename)
    version = uuid4().hex
    prefix = version_chunk_prefix(filename, version)
    version_dir = UPLOAD_DIR / ".versions" / version
    version_dir.mkdir(parents=True, exist_ok=False)
    source_path = version_dir / filename
    for document in new_docs:
        document["file_path"] = str(source_path)
        document["document_version"] = version
        for key in ("chunk_id", "parent_chunk_id", "root_chunk_id"):
            if document.get(key):
                document[key] = prefix + document[key]
    parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]

    committed = False
    try:
        await asyncio.to_thread(document_versions.mark_cleanup, filename, version)
        os.replace(staged_path, source_path)
        await asyncio.to_thread(milvus_writer.write_documents, leaf_docs)
        await asyncio.to_thread(parent_chunk_store.upsert_documents, parent_docs)
        await asyncio.to_thread(document_versions.mark_cleanup, filename, old_version)
        await asyncio.to_thread(document_versions.activate, filename, version)
        committed = True
    except Exception:
        # If SQLite committed before surfacing an error, the new version is
        # already visible and must never be removed by this cleanup path.
        if await asyncio.to_thread(document_versions.active_version, filename) == version:
            committed = True
        else:
            try:
                await asyncio.to_thread(_delete_version, filename, version)
                await asyncio.to_thread(document_versions.clear_cleanup, filename, version)
            except Exception as cleanup_error:
                print(f"[documents] New version cleanup deferred: {cleanup_error}")
            raise

    if committed and old_version != version:
        try:
            await asyncio.to_thread(document_versions.clear_cleanup, filename, version)
        except Exception as cleanup_error:
            print(f"[documents] Cleanup journal update deferred: {cleanup_error}")
        # The active-version filter keeps old rows invisible if cleanup fails.
        await asyncio.to_thread(_drain_pending_cleanup, filename)
    return DocumentUploadResponse(
        filename=filename,
        chunks_processed=len(leaf_docs),
        message=f"成功处理 {filename}！叶子分片 {len(leaf_docs)} 个，父级片段 {len(parent_docs)} 个。",
    )


def _validated_filename(raw_filename: str) -> str:
    normalized_filename = _repair_utf8_mojibake(raw_filename)
    filename = Path(normalized_filename).name
    reserved_name = filename.split(".", 1)[0].upper()
    if (
        not filename
        or filename != normalized_filename
        or filename in {".", ".."}
        or filename.rstrip(" .") != filename
        or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', filename)
        or reserved_name in WINDOWS_RESERVED_NAMES
    ):
        raise HTTPException(status_code=400, detail="文件名无效")
    return filename


def _repair_utf8_mojibake(value: str) -> str:
    """Repair UTF-8 bytes that a multipart client decoded as Latin-1.

    C1 control characters are not valid in user-facing filenames, but they are
    a reliable marker of this specific mojibake pattern (for example,
    ``ç \x81`` instead of ``码``). Leave every other filename untouched.
    """
    if not any("\x80" <= character <= "\x9f" for character in value):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


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
