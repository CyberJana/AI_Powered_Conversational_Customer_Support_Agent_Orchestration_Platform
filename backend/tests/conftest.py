"""Shared pytest fixtures: an isolated in-memory SQLite DB for API tests.

Note: pgvector's ``Vector`` column type is Postgres-only, so only the
tables needed for auth tests are created here. Full-schema integration
tests against Postgres/pgvector run via docker-compose (see README).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.user import Organization, User  # noqa: F401
from app.models.conversation import Conversation, Message  # noqa: F401
from app.models.evaluation import Escalation, Feedback, SecurityEvent  # noqa: F401
from app.models.knowledge_base import Document, DocumentChunk, KnowledgeBase  # noqa: F401
from app.models.agent import Agent, AgentRun, Playbook, Tool, ToolCall  # noqa: F401
from app.models.commerce import Order, Product  # noqa: F401


@pytest.fixture()
def _db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Organization.__table__,
            User.__table__,
            Conversation.__table__,
            Message.__table__,
            Feedback.__table__,
            KnowledgeBase.__table__,
            Document.__table__,
            DocumentChunk.__table__,
            Agent.__table__,
            Playbook.__table__,
            Tool.__table__,
            AgentRun.__table__,
            ToolCall.__table__,
            Product.__table__,
            Order.__table__,
            Escalation.__table__,
            SecurityEvent.__table__,
        ],
    )
    yield engine


@pytest.fixture()
def db_session(_db_engine):
    """A session bound to the same in-memory DB the `client` fixture serves
    requests against - lets tests seed rows (e.g. Tool/Product/Order) that
    have no admin-facing create endpoint.
    """
    TestingSessionLocal = sessionmaker(bind=_db_engine, autoflush=False, autocommit=False, future=True)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(tmp_path, monkeypatch, _db_engine):
    monkeypatch.setattr("app.services.storage_service._UPLOAD_DIR", tmp_path / "uploads")

    # Starlette caches the built middleware stack (including the in-memory
    # rate limiter's hit counters) on the FastAPI app instance. Since `app`
    # is a module-level singleton shared across the whole test session,
    # force a rebuild here so each test starts with a fresh rate-limit
    # bucket instead of accumulating hits across the entire test run.
    app.middleware_stack = None

    TestingSessionLocal = sessionmaker(bind=_db_engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
