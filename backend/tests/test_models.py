"""Tests that do not require a live database: model metadata integrity."""
from app.database import Base
from app import models  # noqa: F401  (registers all models)

EXPECTED_TABLES = {
    "organizations", "users", "roles", "knowledge_bases", "documents", "document_chunks",
    "conversations", "messages", "intents", "agents", "playbooks", "tools", "agent_runs",
    "tool_calls", "evaluations", "evaluation_results", "feedback", "security_events",
    "audit_logs", "escalations",
}


def test_all_expected_tables_registered():
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_document_chunk_has_vector_embedding_column():
    chunks = Base.metadata.tables["document_chunks"]
    assert "embedding" in chunks.columns


def test_users_email_is_unique():
    users = Base.metadata.tables["users"]
    assert users.columns["email"].unique
