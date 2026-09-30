"""Agent, playbook, tool, and agent-run/tool-call models."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class Agent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "agents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    system_instructions: Mapped[str] = mapped_column(Text, default="")
    allowed_tools: Mapped[list] = mapped_column(JSONB, default=list)
    knowledge_base_ids: Mapped[list] = mapped_column(JSONB, default=list)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    escalation_policy: Mapped[dict] = mapped_column(JSONB, default=dict)

    playbooks: Mapped[list["Playbook"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class Playbook(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "playbooks"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    intent: Mapped[str] = mapped_column(String(100), nullable=False)
    steps: Mapped[list] = mapped_column(JSONB, default=list)

    agent: Mapped["Agent"] = relationship(back_populates="playbooks")


class Tool(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    permission: Mapped[str] = mapped_column(String(50), default="agent")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5)
    enabled: Mapped[bool] = mapped_column(default=True)


class AgentRun(Base, UUIDPKMixin):
    __tablename__ = "agent_runs"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    playbook_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("playbooks.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")


class ToolCall(Base, UUIDPKMixin):
    __tablename__ = "tool_calls"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tools.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    success: Mapped[bool] = mapped_column(default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent_run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")
