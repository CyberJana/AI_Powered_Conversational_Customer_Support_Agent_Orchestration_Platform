"""Pydantic schemas for the evaluation harness endpoints (FR-15)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvaluationRunRequest(BaseModel):
    name: str = Field(default="Scheduled Evaluation", min_length=1, max_length=255)
    knowledge_base_id: uuid.UUID | None = None


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    dataset_size: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    summary: dict


class EvaluationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    test_case_id: str
    metric_name: str
    metric_value: float
    details: dict
    created_at: datetime


class EvaluationDetail(EvaluationOut):
    results: list[EvaluationResultOut]
