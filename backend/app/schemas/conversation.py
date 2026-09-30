"""Pydantic schemas for conversation listing/detail/feedback."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: uuid.UUID
    sender: str
    content: str
    confidence: float | None
    intent: str | None
    sources: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    id: uuid.UUID
    status: str
    intent: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class FeedbackRequest(BaseModel):
    message_id: uuid.UUID
    rating: str  # "up" | "down"
    comment: str | None = None
