"""Pydantic schemas for knowledge base and document endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    filename: str
    file_type: str
    status: str
    error_message: str | None
    created_at: datetime
