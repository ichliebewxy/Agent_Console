"""知识库与记忆侧车的 HTTP 数据契约。"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict


class DocumentInfo(BaseModel):
    filename: str
    file_type: str
    chunk_count: int
    uploaded_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]


class DocumentUploadResponse(BaseModel):
    filename: str
    chunks_processed: int
    message: str


class DocumentDeleteResponse(BaseModel):
    filename: str
    chunks_deleted: int
    message: str


class MemoryInfo(BaseModel):
    id: str
    memory: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MemoryListResponse(BaseModel):
    memories: List[MemoryInfo] = Field(default_factory=list)
    enabled: bool = True
    initialized: bool = True


class MemoryAddRequest(BaseModel):
    memory: str
    infer: bool = False


class MemoryAddResponse(BaseModel):
    message: str
    memory: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)


class MemoryUpdateRequest(BaseModel):
    memory: str


class MemoryDeleteResponse(BaseModel):
    memory_id: str
    message: str


class MemoryStatusResponse(BaseModel):
    enabled: bool
    initialized: bool
    dir: str
    model: str
    error: Optional[str] = None
