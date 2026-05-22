"""Knowledge-base document routes."""
import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from document_loader import DocumentLoader
from embedding import EmbeddingService
from milvus_client import MilvusManager
from milvus_writer import MilvusWriter
from parent_chunk_store import ParentChunkStore
from schemas import DocumentDeleteResponse, DocumentInfo, DocumentListResponse, DocumentUploadResponse

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR.parent / "data" / "documents"
VALID_EXTS = (".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".txt")

router = APIRouter()
loader = DocumentLoader()
parent_chunk_store = ParentChunkStore()
milvus_manager = MilvusManager()
embedding_service = EmbeddingService()
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
    filename = file.filename
    if not filename.lower().endswith(VALID_EXTS):
        raise HTTPException(status_code=400, detail=f"不支持的文件格式。仅支持: {', '.join(VALID_EXTS)}")
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        milvus_manager.init_collection()
        _delete_existing(filename)
        file_path = await _save_upload(file, filename)
        new_docs = loader.load_document(str(file_path), filename)
        if not new_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未能提取内容")

        parent_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [doc for doc in new_docs if int(doc.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            raise HTTPException(status_code=500, detail="文档处理失败，未生成可检索叶子分块")
        parent_chunk_store.upsert_documents(parent_docs)
        milvus_writer.write_documents(leaf_docs)
        return DocumentUploadResponse(
            filename=filename,
            chunks_processed=len(leaf_docs),
            message=f"成功处理 {filename}！叶子分片 {len(leaf_docs)} 个，父级片段 {len(parent_docs)} 个。",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {exc}")


@router.delete("/documents/{filename}", response_model=DocumentDeleteResponse)
async def delete_document(filename: str):
    try:
        milvus_manager.init_collection()
        result = milvus_manager.delete(f'filename == "{filename}"')
        parent_chunk_store.delete_by_filename(filename)
        count = result.get("delete_count", 0) if isinstance(result, dict) else 0
        return DocumentDeleteResponse(filename=filename, chunks_deleted=count, message=f"成功删除文档 {filename} 的向量数据")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除文档失败: {exc}")


def _delete_existing(filename: str):
    try:
        milvus_manager.delete(f'filename == "{filename}"')
    except Exception:
        pass
    try:
        parent_chunk_store.delete_by_filename(filename)
    except Exception:
        pass


async def _save_upload(file: UploadFile, filename: str) -> Path:
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as f:
        f.write(await file.read())
    return file_path
