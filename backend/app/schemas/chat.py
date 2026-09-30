"""Pydantic schemas for the chat endpoint."""
import uuid

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    snippet: str
    score: float


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    knowledge_base_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    answer: str
    confidence: float | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    intent: str | None = None
    escalated: bool = False
