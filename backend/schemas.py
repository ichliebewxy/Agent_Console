from pydantic import BaseModel
from typing import Optional, List, Any, Dict


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "default_user"
    session_id: Optional[str] = "default_session"


class RetrievedChunk(BaseModel):
    filename: str
    file_type: Optional[str] = None
    page_number: Optional[str | int] = None
    text: Optional[str] = None
    score: Optional[float] = None
    rrf_rank: Optional[int] = None
    rerank_score: Optional[float] = None
    chunk_id: Optional[str] = None
    retrieval_source: Optional[str] = None


class RagTrace(BaseModel):
    tool_used: bool
    tool_name: str
    query: Optional[str] = None
    expanded_query: Optional[str] = None
    step_back_question: Optional[str] = None
    step_back_answer: Optional[str] = None
    expansion_type: Optional[str] = None
    hypothetical_doc: Optional[str] = None
    retrieval_stage: Optional[str] = None
    grade_score: Optional[str] = None
    grade_route: Optional[str] = None
    rewrite_needed: Optional[bool] = None
    rewrite_strategy: Optional[str] = None
    rewrite_query: Optional[str] = None
    rerank_enabled: Optional[bool] = None
    rerank_applied: Optional[bool] = None
    rerank_model: Optional[str] = None
    rerank_endpoint: Optional[str] = None
    rerank_error: Optional[str] = None
    retrieval_mode: Optional[str] = None
    candidate_k: Optional[int] = None
    leaf_retrieve_level: Optional[int] = None
    auto_merge_enabled: Optional[bool] = None
    auto_merge_applied: Optional[bool] = None
    auto_merge_threshold: Optional[int] = None
    auto_merge_replaced_chunks: Optional[int] = None
    auto_merge_steps: Optional[int] = None
    ragflow_enabled: Optional[bool] = None
    ragflow_applied: Optional[bool] = None
    ragflow_endpoint: Optional[str] = None
    ragflow_dataset_ids: Optional[List[str]] = None
    ragflow_error: Optional[str] = None
    retrieved_chunks: Optional[List[RetrievedChunk]] = None
    initial_retrieved_chunks: Optional[List[RetrievedChunk]] = None
    expanded_retrieved_chunks: Optional[List[RetrievedChunk]] = None


class ChatResponse(BaseModel):
    response: str
    rag_trace: Optional[RagTrace] = None


class MessageInfo(BaseModel):
    type: str
    content: str
    timestamp: str
    rag_trace: Optional[RagTrace] = None


class SessionMessagesResponse(BaseModel):
    messages: List[MessageInfo]


class SessionInfo(BaseModel):
    session_id: str
    updated_at: str
    message_count: int


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]


class SessionDeleteResponse(BaseModel):
    session_id: str
    message: str


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


class HumanReviewCreateRequest(BaseModel):
    user_id: Optional[str] = "default_user"
    session_id: Optional[str] = "default_session"
    question: Optional[str] = ""
    answer: str
    message_index: Optional[int] = None
    rag_trace: Optional[Dict[str, Any]] = None
    reviewer_note: Optional[str] = ""


class HumanReviewUpdateRequest(BaseModel):
    status: str
    reviewer_note: Optional[str] = ""
    revised_answer: Optional[str] = None


class HumanReviewInfo(BaseModel):
    id: str
    status: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    question: Optional[str] = None
    answer: str
    message_index: Optional[int] = None
    rag_trace: Optional[Dict[str, Any]] = None
    reviewer_note: Optional[str] = ""
    revised_answer: Optional[str] = None
    created_at: str
    updated_at: str


class HumanReviewListResponse(BaseModel):
    reviews: List[HumanReviewInfo]


class ToolFailureUpdateRequest(BaseModel):
    status: str
    callback_note: Optional[str] = ""


class ToolFailureInfo(BaseModel):
    id: str
    status: str
    tool_name: str
    error: str
    payload: Dict[str, Any] = {}
    fallback: Optional[str] = ""
    callback_note: Optional[str] = ""
    occurrence_count: Optional[int] = 1
    created_at: str
    updated_at: str


class ToolFailureListResponse(BaseModel):
    failures: List[ToolFailureInfo]
