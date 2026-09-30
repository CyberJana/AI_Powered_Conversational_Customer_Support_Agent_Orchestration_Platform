"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    user_role = pg.ENUM("admin", "agent", "customer", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "roles",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(500), server_default=""),
    )

    op.create_table(
        "knowledge_bases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kb_organization_id", "knowledge_bases", ["organization_id"])

    op.create_table(
        "documents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("knowledge_base_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("uploaded_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_kb_id", "documents", ["knowledge_base_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", pg.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("chunk_metadata", pg.JSONB, server_default="{}"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    op.create_index("ix_chunks_document_id", "document_chunks", ["document_id"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "conversations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("knowledge_base_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("intent", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_org_id", "conversations", ["organization_id"])
    op.create_index("ix_conversations_status", "conversations", ["status"])

    op.create_table(
        "messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", pg.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("intent", sa.String(100), nullable=True),
        sa.Column("sources", pg.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "intents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, server_default=""),
    )

    op.create_table(
        "agents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("system_instructions", sa.Text, server_default=""),
        sa.Column("allowed_tools", pg.JSONB, server_default="[]"),
        sa.Column("knowledge_base_ids", pg.JSONB, server_default="[]"),
        sa.Column("confidence_threshold", sa.Float, server_default="0.6"),
        sa.Column("escalation_policy", pg.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "playbooks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", pg.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("intent", sa.String(100), nullable=False),
        sa.Column("steps", pg.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tools",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("input_schema", pg.JSONB, server_default="{}"),
        sa.Column("permission", sa.String(50), server_default="agent"),
        sa.Column("timeout_seconds", sa.Integer, server_default="5"),
        sa.Column("enabled", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", pg.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", pg.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("playbook_id", pg.UUID(as_uuid=True), sa.ForeignKey("playbooks.id"), nullable=True),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_run_id", pg.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", pg.UUID(as_uuid=True), sa.ForeignKey("tools.id"), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("input", pg.JSONB, server_default="{}"),
        sa.Column("output", pg.JSONB, nullable=True),
        sa.Column("success", sa.Boolean, server_default=sa.false()),
        sa.Column("duration_ms", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tool_calls_agent_run_id", "tool_calls", ["agent_run_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dataset_size", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("summary", pg.JSONB, server_default="{}"),
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("evaluation_id", pg.UUID(as_uuid=True), sa.ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_case_id", sa.String(100), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Float, nullable=False),
        sa.Column("details", pg.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_eval_results_evaluation_id", "evaluation_results", ["evaluation_id"])

    op.create_table(
        "feedback",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", pg.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rating", sa.String(10), nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "security_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", pg.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), server_default="low"),
        sa.Column("details", pg.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_security_events_conversation_id", "security_events", ["conversation_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("details", pg.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "escalations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", pg.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("assigned_to", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_escalations_status", "escalations", ["status"])
    op.create_index("ix_escalations_conversation_id", "escalations", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("escalations")
    op.drop_table("audit_logs")
    op.drop_table("security_events")
    op.drop_table("feedback")
    op.drop_table("evaluation_results")
    op.drop_table("evaluations")
    op.drop_table("tool_calls")
    op.drop_table("agent_runs")
    op.drop_table("tools")
    op.drop_table("playbooks")
    op.drop_table("agents")
    op.drop_table("intents")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("knowledge_bases")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("organizations")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
