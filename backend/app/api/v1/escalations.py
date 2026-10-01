"""Escalation queue endpoints (FR-14): manual escalation creation, the
agent/admin queue, and resolution. Automatic escalation creation from the
confidence engine lives in app.services.chat_service; this module covers
the human-facing CRUD surface described in docs/api-spec.md.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.conversation import Conversation
from app.models.evaluation import Escalation
from app.models.user import User
from app.schemas.escalation import EscalationCreate, EscalationOut
from app.security.dependencies import get_current_user, require_role

router = APIRouter()


def _get_conversation_in_org(db: Session, conversation_id: uuid.UUID, organization_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


def _get_escalation_in_org(db: Session, escalation_id: uuid.UUID, organization_id: uuid.UUID) -> Escalation:
    escalation = db.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation not found")
    conversation = db.get(Conversation, escalation.conversation_id)
    if conversation is None or conversation.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation not found")
    return escalation


@router.post("/escalations", response_model=EscalationOut, status_code=status.HTTP_201_CREATED)
def create_escalation(
    payload: EscalationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Escalation:
    conversation = _get_conversation_in_org(db, payload.conversation_id, current_user.organization_id)
    if current_user.role.value == "customer" and conversation.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your conversation")

    escalation = Escalation(conversation_id=conversation.id, reason=payload.reason)
    conversation.status = "escalated"
    db.add(escalation)
    db.commit()
    db.refresh(escalation)
    return escalation


@router.get("/escalations", response_model=list[EscalationOut])
def list_escalations(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("agent", "admin")),
) -> list[Escalation]:
    query = (
        db.query(Escalation)
        .join(Conversation, Escalation.conversation_id == Conversation.id)
        .filter(Conversation.organization_id == current_user.organization_id)
    )
    if status_filter:
        query = query.filter(Escalation.status == status_filter)
    return query.order_by(Escalation.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/escalations/{escalation_id}/resolve", response_model=EscalationOut)
def resolve_escalation(
    escalation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("agent", "admin")),
) -> Escalation:
    escalation = _get_escalation_in_org(db, escalation_id, current_user.organization_id)
    escalation.status = "resolved"
    escalation.resolved_at = datetime.now(timezone.utc)
    if escalation.assigned_to is None:
        escalation.assigned_to = current_user.id

    conversation = db.get(Conversation, escalation.conversation_id)
    if conversation is not None:
        conversation.status = "resolved"

    db.commit()
    db.refresh(escalation)
    return escalation

