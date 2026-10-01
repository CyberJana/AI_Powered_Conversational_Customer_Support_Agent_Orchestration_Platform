"""Aggregate all models so Alembic autogenerate and Base.metadata see everything."""
from app.models.agent import Agent, AgentRun, Playbook, Tool, ToolCall  # noqa: F401
from app.models.commerce import Order, Product  # noqa: F401
from app.models.conversation import Conversation, Intent, Message  # noqa: F401
from app.models.evaluation import (  # noqa: F401
    AuditLog,
    Escalation,
    Evaluation,
    EvaluationResult,
    Feedback,
    SecurityEvent,
)
from app.models.knowledge_base import Document, DocumentChunk, KnowledgeBase  # noqa: F401
from app.models.learning import ReviewQueueItem, TrainingExample  # noqa: F401
from app.models.user import Organization, Role, User  # noqa: F401
