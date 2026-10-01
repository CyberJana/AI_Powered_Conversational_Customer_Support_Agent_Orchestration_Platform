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
rows. Confidence scoring and automatic escalation are layered on in Phase
10/11 without changing this module's public contract.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentRun, Playbook, Tool
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, SourceRef
from app.services import intent_service, rag_service, tool_service
from app.services.llm_service import extract_tool_arguments, generate_chat_reply, generate_grounded_reply

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
) -> tuple[list[dict], list[SourceRef]]:
    """Executes a Playbook's declarative steps, returning (tool_outputs,
    rag_sources) for the final `respond` step to incorporate. Every
    tool_call step is validated/executed/audit-logged via tool_service.
    """
    agent_run = AgentRun(conversation_id=conversation.id, agent_id=playbook.agent_id, playbook_id=playbook.id)
    db.add(agent_run)
    db.flush()

    tool_outputs: list[dict] = []
    sources: list[SourceRef] = []
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
                retrieved = rag_service.retrieve(db, kb_id, message)
                sources = [
                    SourceRef(document_id=c.document_id, chunk_id=c.chunk_id, snippet=c.content[:300], score=c.score)
                    for c in retrieved
                ]
        elif step_type == "confidence_check":
            # No-op placeholder: real confidence scoring/escalation lands in
            # Phase 10 (FR-13/FR-14) without changing this loop's contract.
            pass
        # "respond" is handled by the caller once all prior steps have run.

    agent_run.status = "failed" if failed else "completed"
    agent_run.finished_at = datetime.now(timezone.utc)
    db.flush()
    return tool_outputs, sources


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

    playbook = None
    if conversation.agent_id:
        playbook = (
            db.query(Playbook).filter(Playbook.agent_id == conversation.agent_id, Playbook.intent == intent).first()
        )

    if playbook:
        tool_outputs, sources = _run_playbook(db, conversation, playbook, payload.message)
        context_passages = [f"Tool '{t['tool']}' result: {t['output'] or t['error']}" for t in tool_outputs]
        if knowledge_base_id and not sources:
            retrieved = rag_service.retrieve(db, knowledge_base_id, payload.message)
            if rag_service.has_sufficient_context(retrieved):
                sources = [
                    SourceRef(document_id=c.document_id, chunk_id=c.chunk_id, snippet=c.content[:300], score=c.score)
                    for c in retrieved
                ]
                context_passages.extend(c.content for c in retrieved)
        context_passages.extend(s.snippet for s in sources if s.snippet not in context_passages)
        answer = (
            generate_grounded_reply(history, context_passages) if context_passages else generate_chat_reply(history)
        )
    elif knowledge_base_id:
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
        intent=intent,
        escalated=False,
    )

