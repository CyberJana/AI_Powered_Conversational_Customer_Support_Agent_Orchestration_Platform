"""Chat orchestration: conversation lifecycle + message persistence.

Phase 4 wired a direct LLM reply using conversation history. Phase 6 adds
retrieval-augmented generation: when a conversation is scoped to a
knowledge base, the user's message is embedded, the most relevant document
chunks are retrieved (app.services.rag_service), and the LLM is asked to
answer using only that context, with citations persisted as `sources`.
Phase 7 adds intent classification (app.services.intent_service): every
incoming message is classified into the fixed intent taxonomy and stored on
both the message and the conversation. Phase 9 adds playbook-driven tool
calling (FR-11/FR-12): when the conversation is linked to an Agent and the
classified intent matches one of that Agent's Playbooks, the playbook's
declarative steps (tool_call/rag_retrieval/confidence_check/respond) are
executed, with every tool invocation audit-logged via AgentRun/ToolCall
rows. Phase 10 adds composite confidence scoring and automatic escalation
(FR-13/FR-14, app.services.confidence_service): every assistant reply gets
a confidence score derived from real signals (intent confidence, retrieval
relevance, source coverage, citation grounding, tool success), and
conversations below the applicable threshold - or matching an explicit
trigger (human agent request, sensitive topic, tool failure, security
event, repeated low confidence) - get a real Escalation row.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.agent import Agent, AgentRun, Playbook, Tool
from app.models.conversation import Conversation, Message
from app.models.evaluation import Escalation, SecurityEvent
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, SourceRef
from app.services import confidence_service, intent_service, rag_service, tool_service
from app.services.llm_service import extract_tool_arguments, generate_chat_reply, generate_grounded_reply

settings = get_settings()

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

    agent_id = payload.agent_id
    if agent_id is not None:
        agent = db.get(Agent, agent_id)
        if agent is None or agent.organization_id != user.organization_id:
            raise ValueError("Agent not found")

    conversation = Conversation(
        organization_id=user.organization_id,
        customer_id=user.id,
        knowledge_base_id=payload.knowledge_base_id,
        agent_id=agent_id,
    )
    db.add(conversation)
    db.flush()
    return conversation


def _run_playbook(
    db: Session, conversation: Conversation, playbook: Playbook, message: str
) -> tuple[list[dict], list[SourceRef], list[rag_service.RetrievedChunk], bool]:
    """Executes a Playbook's declarative steps, returning (tool_outputs,
    rag_sources, retrieved_chunks, rag_attempted) for the final `respond`
    step - and Phase 10's confidence scoring - to incorporate. Every
    tool_call step is validated/executed/audit-logged via tool_service.
    """
    agent_run = AgentRun(conversation_id=conversation.id, agent_id=playbook.agent_id, playbook_id=playbook.id)
    db.add(agent_run)
    db.flush()

    tool_outputs: list[dict] = []
    sources: list[SourceRef] = []
    retrieved_chunks: list[rag_service.RetrievedChunk] = []
    rag_attempted = False
    ctx = tool_service.ToolContext(organization_id=conversation.organization_id, conversation_id=conversation.id)
    failed = False

    for step in playbook.steps:
        step_type = step.get("type")
        config = step.get("config") or {}

        if step_type == "tool_call":
            tool_name = config.get("tool")
            tool = db.query(Tool).filter(Tool.name == tool_name).first()
            arguments = extract_tool_arguments(
                message, tool_name, tool.description if tool else "", tool.input_schema if tool else {}
            )
            tool_call = tool_service.execute_tool(db, agent_run.id, tool_name, arguments, ctx)
            tool_outputs.append(
                {"tool": tool_name, "success": tool_call.success, "output": tool_call.output, "error": tool_call.error_message}
            )
            if not tool_call.success:
                failed = True
        elif step_type == "rag_retrieval":
            kb_id = config.get("knowledge_base_id") or conversation.knowledge_base_id
            if kb_id:
                rag_attempted = True
                retrieved_chunks = rag_service.retrieve(db, kb_id, message)
                sources = [
                    SourceRef(document_id=c.document_id, chunk_id=c.chunk_id, snippet=c.content[:300], score=c.score)
                    for c in retrieved_chunks
                ]
        elif step_type == "confidence_check":
            # No-op placeholder: Phase 10 computes the real composite score
            # in handle_chat_message once all steps have run, so this step
            # type stays a declarative marker in the playbook definition.
            pass
        # "respond" is handled by the caller once all prior steps have run.

    agent_run.status = "failed" if failed else "completed"
    agent_run.finished_at = datetime.now(timezone.utc)
    db.flush()
    return tool_outputs, sources, retrieved_chunks, rag_attempted


def handle_chat_message(db: Session, user: User, payload: ChatRequest) -> ChatResponse:
    conversation = _get_or_create_conversation(db, user, payload)

    intent, intent_confidence = intent_service.classify(payload.message)

    user_message = Message(
        conversation_id=conversation.id,
        sender="customer",
        content=payload.message,
        intent=intent,
        intent_confidence=intent_confidence,
    )
    db.add(user_message)
    conversation.intent = intent
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
    tool_outputs: list[dict] = []
    retrieved_chunks: list[rag_service.RetrievedChunk] = []
    rag_attempted = False

    playbook = None
    if conversation.agent_id:
        playbook = (
            db.query(Playbook).filter(Playbook.agent_id == conversation.agent_id, Playbook.intent == intent).first()
        )

    if playbook:
        tool_outputs, sources, retrieved_chunks, rag_attempted = _run_playbook(
            db, conversation, playbook, payload.message
        )
        context_passages = [f"Tool '{t['tool']}' result: {t['output'] or t['error']}" for t in tool_outputs]
        if knowledge_base_id and not sources:
            rag_attempted = True
            retrieved_chunks = rag_service.retrieve(db, knowledge_base_id, payload.message)
            if rag_service.has_sufficient_context(retrieved_chunks):
                sources = [
                    SourceRef(document_id=c.document_id, chunk_id=c.chunk_id, snippet=c.content[:300], score=c.score)
                    for c in retrieved_chunks
                ]
                context_passages.extend(c.content for c in retrieved_chunks)
        context_passages.extend(s.snippet for s in sources if s.snippet not in context_passages)
        answer = (
            generate_grounded_reply(history, context_passages) if context_passages else generate_chat_reply(history)
        )
    elif knowledge_base_id:
        rag_attempted = True
        retrieved_chunks = rag_service.retrieve(db, knowledge_base_id, payload.message)
        if rag_service.has_sufficient_context(retrieved_chunks):
            answer = generate_grounded_reply(history, [c.content for c in retrieved_chunks])
            sources = [
                SourceRef(document_id=c.document_id, chunk_id=c.chunk_id, snippet=c.content[:300], score=c.score)
                for c in retrieved_chunks
            ]
        else:
            answer = INSUFFICIENT_CONTEXT_ANSWER
    else:
        answer = generate_chat_reply(history)

    # --- Phase 10: composite confidence + escalation (FR-13/FR-14) ---
    if rag_attempted:
        retrieval_relevance = retrieved_chunks[0].score if retrieved_chunks else 0.0
        source_coverage = len(retrieved_chunks) / rag_service.TOP_K
    else:
        retrieval_relevance = None
        source_coverage = None
    grounding = confidence_service.grounding_score(answer, len(sources)) if sources else None
    tool_success_rate = (
        sum(1 for t in tool_outputs if t["success"]) / len(tool_outputs) if tool_outputs else None
    )

    confidence = confidence_service.compute_confidence(
        confidence_service.ConfidenceSignals(
            intent_confidence=intent_confidence,
            retrieval_relevance=retrieval_relevance,
            source_coverage=source_coverage,
            grounding_score=grounding,
            tool_success_rate=tool_success_rate,
        )
    )

    threshold = settings.default_confidence_threshold
    if conversation.agent_id:
        agent = db.get(Agent, conversation.agent_id)
        if agent:
            threshold = agent.confidence_threshold

    recent_confidences = (
        db.query(Message.confidence)
        .filter(Message.conversation_id == conversation.id, Message.sender == "assistant")
        .order_by(Message.created_at.desc())
        .limit(confidence_service.REPEATED_FAILURE_WINDOW)
        .all()
    )
    repeated_low_confidence = len(recent_confidences) == confidence_service.REPEATED_FAILURE_WINDOW and all(
        c is not None and c < threshold for (c,) in recent_confidences
    )
    has_security_event = (
        db.query(SecurityEvent.id).filter(SecurityEvent.conversation_id == conversation.id).first() is not None
    )
    tool_failed = any(not t["success"] for t in tool_outputs)

    trigger = confidence_service.detect_trigger(
        intent=intent,
        message=payload.message,
        tool_failed=tool_failed,
        has_security_event=has_security_event,
        repeated_low_confidence=repeated_low_confidence,
    )
    escalated = trigger.should_escalate or confidence < threshold
    escalation_reason = trigger.reason or (
        f"Composite confidence {confidence:.2f} is below the {threshold:.2f} threshold."
    )

    assistant_message = Message(
        conversation_id=conversation.id,
        sender="assistant",
        content=answer,
        confidence=confidence,
        sources=[s.model_dump(mode="json") for s in sources] or None,
    )
    db.add(assistant_message)

    if escalated:
        conversation.status = "escalated"
        db.add(Escalation(conversation_id=conversation.id, reason=escalation_reason, ai_confidence=confidence))

    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        message_id=assistant_message.id,
        conversation_id=conversation.id,
        answer=answer,
        confidence=confidence,
        sources=sources,
        intent=intent,
        escalated=escalated,
    )

