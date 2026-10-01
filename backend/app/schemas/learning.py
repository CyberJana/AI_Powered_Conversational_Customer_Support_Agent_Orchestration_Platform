"""Pydantic schemas for the continuous-learning review queue (FR-16)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.learning import TRAINING_CASE_TYPES


class ReviewQueueItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID | None
    message_id: uuid.UUID | None
    source_type: str
    status: str
    input_text: str
    output_text: str | None
    context: dict
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class ReviewApproveRequest(BaseModel):
    """The human reviewer's correction, promoted verbatim into a
    TrainingExample once approved. Exactly one case_type's fields apply.
    """

    case_type: str
    expected_intent: str | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    expect_tool_success: bool | None = None

    @field_validator("case_type")
    @classmethod
    def validate_case_type(cls, value: str) -> str:
        if value not in TRAINING_CASE_TYPES:
            raise ValueError(f"Unknown case_type '{value}'. Allowed: {sorted(TRAINING_CASE_TYPES)}")
        return value


class TrainingExampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_type: str
    message: str
    expected_intent: str | None
    tool_name: str | None
    tool_input: dict | None
    expect_tool_success: bool | None
    approved_by: uuid.UUID
    created_at: datetime
