"""Routers for conversation listing/detail and message feedback."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.conversation import Conversation, Message
from app.models.evaluation import Feedback
from app.models.learning import ReviewQueueItem
from app.models.user import User
from app.schemas.conversation import (
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
)
from app.security.dependencies import get_current_user

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Conversation]:
    query = db.query(Conversation).filter(Conversation.organization_id == current_user.organization_id)
    if current_user.role.value == "customer":
        query = query.filter(Conversation.customer_id == current_user.id)
    if status_filter:
        query = query.filter(Conversation.status == status_filter)
    return query.order_by(Conversation.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if current_user.role.value == "customer" and conversation.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your conversation")
    return conversation


@router.post(
    "/conversations/{conversation_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
def submit_feedback(
    conversation_id: uuid.UUID,
    payload: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    message = db.get(Message, payload.message_id)
    if message is None or message.conversation_id != conversation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found in this conversation")
    if payload.rating not in ("up", "down"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rating must be 'up' or 'down'")

    db.add(
        Feedback(
            message_id=payload.message_id,
            user_id=current_user.id,
            rating=payload.rating,
            comment=payload.comment,
        )
    )

    if payload.rating == "down" and message.sender == "assistant":
        # FR-16: negative feedback on an assistant reply is captured for
        # human review alongside low-confidence/failed-tool/failed-retrieval
        # turns, independent of whether the confidence engine itself
        # flagged this turn.
        prior_customer_message = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation_id,
                Message.sender == "customer",
                Message.created_at <= message.created_at,
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        db.add(
            ReviewQueueItem(
                organization_id=conversation.organization_id,
                conversation_id=conversation_id,
                message_id=message.id,
                source_type="negative_feedback",
                input_text=prior_customer_message.content if prior_customer_message else "",
                output_text=message.content,
                context={"comment": payload.comment},
            )
        )

    db.commit()

