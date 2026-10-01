"""Pydantic schemas for escalation endpoints (FR-14)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EscalationCreate(BaseModel):
    conversation_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=2000)


class EscalationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    reason: str
    ai_confidence: float | None
    status: str
    assigned_to: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
