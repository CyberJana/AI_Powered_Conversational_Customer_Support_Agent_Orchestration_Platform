"""Chat orchestration: conversation lifecycle + message persistence.

Phase 4 wired a direct LLM reply using conversation history. Phase 6 adds
retrieval-augmented generation: when a conversation is scoped to a
knowledge base, the user's message is embedded, the most relevant document
chunks are retrieved (app.services.rag_service), and the LLM is asked to
answer using only that context, with citations persisted as `sources`.
Intent classification, confidence scoring, and automatic escalation are
layered on in later phases (7/10/11) without changing this module's public
contract.
"""
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, SourceRef
from app.services import rag_service
from app.services.llm_service import generate_chat_reply, generate_grounded_reply

MAX_HISTORY_MESSAGES = 20
INSUFFICIENT_CONTEXT_ANSWER = (
    "I don't have enough information in the knowledge base to answer that confidently. "
    "Could you rephrase, or would you like me to connect you with a human agent?"
)


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

    knowledge_base_id = payload.knowledge_base_id or conversation.knowledge_base_id
    sources: list[SourceRef] = []

    if knowledge_base_id:
        retrieved = rag_service.retrieve(db, knowledge_base_id, payload.message)
        if rag_service.has_sufficient_context(retrieved):
            answer = generate_grounded_reply(history, [c.content for c in retrieved])
            sources = [
                SourceRef(document_id=c.document_id, chunk_id=c.chunk_id, snippet=c.content[:300], score=c.score)
                for c in retrieved
            ]
        else:
            answer = INSUFFICIENT_CONTEXT_ANSWER
    else:
        answer = generate_chat_reply(history)

    assistant_message = Message(
        conversation_id=conversation.id,
        sender="assistant",
        content=answer,
        sources=[s.model_dump(mode="json") for s in sources] or None,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        message_id=assistant_message.id,
        conversation_id=conversation.id,
        answer=answer,
        confidence=None,
        sources=sources,
        intent=None,
        escalated=False,
    )

