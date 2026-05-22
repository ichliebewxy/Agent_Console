"""Shared RAG pipeline state and schemas."""
from typing import List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


GRADE_PROMPT = (
    "You are a grader assessing relevance of a retrieved document to a user question.\n"
    "Here is the retrieved document:\n\n{context}\n\n"
    "Here is the user question: {question}\n"
    "If the document contains keywords or semantic meaning related to the question, "
    "grade it as relevant. Give a binary score 'yes' or 'no'."
)


class GradeDocuments(BaseModel):
    binary_score: str = Field(description="Relevance score: 'yes' or 'no'")


class RewriteStrategy(BaseModel):
    strategy: Literal["step_back", "hyde", "complex"]


class RAGState(TypedDict):
    question: str
    query: str
    context: str
    docs: List[dict]
    route: Optional[str]
    expansion_type: Optional[str]
    expanded_query: Optional[str]
    step_back_question: Optional[str]
    step_back_answer: Optional[str]
    hypothetical_doc: Optional[str]
    rag_trace: Optional[dict]


def format_docs(docs: List[dict]) -> str:
    chunks = []
    for idx, doc in enumerate(docs, 1):
        source = doc.get("filename", "Unknown")
        page = doc.get("page_number", "N/A")
        chunks.append(f"[{idx}] {source} (Page {page}):\n{doc.get('text', '')}")
    return "\n\n---\n\n".join(chunks)


def empty_rag_state(question: str) -> RAGState:
    return {
        "question": question,
        "query": question,
        "context": "",
        "docs": [],
        "route": None,
        "expansion_type": None,
        "expanded_query": None,
        "step_back_question": None,
        "step_back_answer": None,
        "hypothetical_doc": None,
        "rag_trace": None,
    }
