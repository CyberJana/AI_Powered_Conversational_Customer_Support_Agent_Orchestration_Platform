"""Pydantic schemas for agent and playbook CRUD endpoints (FR-10/FR-11)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.intent_service import INTENT_LABELS

#: Recognized playbook step types. A step combines intent detection (already
#: done before playbook selection), tool calls, RAG retrieval, and confidence
#: evaluation per FR-11. Execution of these steps is implemented in later
#: phases (9 - Tool Calling, 10 - Confidence Engine); Phase 8 only defines
#: and validates the playbook's declarative structure.
STEP_TYPES = {"tool_call", "rag_retrieval", "confidence_check", "respond"}


class PlaybookStep(BaseModel):
    type: str
    config: dict = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in STEP_TYPES:
            raise ValueError(f"Unknown step type '{value}'. Allowed: {sorted(STEP_TYPES)}")
        return value


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    system_instructions: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[uuid.UUID] = Field(default_factory=list)
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    escalation_policy: dict = Field(default_factory=dict)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_instructions: str | None = None
    allowed_tools: list[str] | None = None
    knowledge_base_ids: list[uuid.UUID] | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    escalation_policy: dict | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    system_instructions: str
    allowed_tools: list[str]
    knowledge_base_ids: list[uuid.UUID]
    confidence_threshold: float
    escalation_policy: dict
    created_at: datetime


class PlaybookCreate(BaseModel):
    agent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    intent: str
    steps: list[PlaybookStep] = Field(default_factory=list)

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        if value not in INTENT_LABELS:
            raise ValueError(f"Unknown intent '{value}'. Allowed: {INTENT_LABELS}")
        return value


class PlaybookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    intent: str | None = None
    steps: list[PlaybookStep] | None = None

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str | None) -> str | None:
        if value is not None and value not in INTENT_LABELS:
            raise ValueError(f"Unknown intent '{value}'. Allowed: {INTENT_LABELS}")
        return value


class PlaybookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    intent: str
    steps: list[dict]
    created_at: datetime


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    input_schema: dict
    permission: str
    timeout_seconds: int
    enabled: bool
    created_at: datetime
