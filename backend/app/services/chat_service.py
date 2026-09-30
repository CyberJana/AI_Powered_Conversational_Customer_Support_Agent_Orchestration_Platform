"""Chat orchestration: conversation lifecycle + message persistence.

Phase 4 wires a direct LLM reply using conversation history. Intent
classification, RAG retrieval/sources, confidence scoring, and automatic
escalation are layered on in later phases (6/7/9/10) without changing
this module's public contract.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import generate_chat_reply

MAX_HISTORY_MESSAGES = 20


def _get_or_create_conversation(db: Session, user: User, payload: ChatRequest) -> Conversation:
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if conversation is None or conversation.organization_id != user.organization_id:
            raise ValueError("Conversation not found")
        return conversation

    conversation = Conversation(
        organization_id=user.organization_id,
        customer_id=user.id,
        knowledge_base_id=payload.knowledge_base_id,
    )
    db.add(conversation)
    db.flush()
    return conversation


def handle_chat_message(db: Session, user: User, payload: ChatRequest) -> ChatResponse:
    conversation = _get_or_create_conversation(db, user, payload)

    user_message = Message(conversation_id=conversation.id, sender="customer", content=payload.message)
    db.add(user_message)
    db.flush()

    history_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    history_messages.reverse()
    history = [
        {"role": "user" if m.sender == "customer" else "assistant", "content": m.content}
        for m in history_messages
    ]

    answer = generate_chat_reply(history)

    assistant_message = Message(conversation_id=conversation.id, sender="assistant", content=answer)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        message_id=assistant_message.id,
        conversation_id=conversation.id,
        answer=answer,
        confidence=None,
        sources=[],
        intent=None,
        escalated=False,
    )
