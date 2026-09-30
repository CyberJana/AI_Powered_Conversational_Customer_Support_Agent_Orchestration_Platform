"""Agent and playbook management endpoints (admin-only CRUD, FR-10/FR-11).

Agents define an AI persona (instructions, allowed tools, knowledge bases,
confidence threshold, escalation policy). Playbooks attach an ordered list
of declarative steps to an agent for a specific intent. Step *execution*
(tool calls, RAG, confidence evaluation) is wired into chat orchestration
in later phases - this module only manages the configuration.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import Agent, Playbook, Tool
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    PlaybookCreate,
    PlaybookOut,
    PlaybookUpdate,
)
from app.security.dependencies import require_role

router = APIRouter()


def _get_agent_or_404(db: Session, agent_id: uuid.UUID, organization_id: uuid.UUID) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


def _get_playbook_or_404(db: Session, playbook_id: uuid.UUID, organization_id: uuid.UUID) -> Playbook:
    playbook = db.get(Playbook, playbook_id)
    if playbook is None or playbook.agent.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return playbook


def _validate_knowledge_base_ids(db: Session, kb_ids: list[uuid.UUID], organization_id: uuid.UUID) -> None:
    for kb_id in kb_ids:
        kb = db.get(KnowledgeBase, kb_id)
        if kb is None or kb.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Knowledge base {kb_id} not found in this organization",
            )


def _validate_allowed_tools(db: Session, tool_names: list[str]) -> None:
    if not tool_names:
        return
    existing = {t.name for t in db.query(Tool).filter(Tool.name.in_(tool_names)).all()}
    missing = set(tool_names) - existing
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tool(s): {sorted(missing)}",
        )


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Agent:
    _validate_allowed_tools(db, payload.allowed_tools)
    _validate_knowledge_base_ids(db, payload.knowledge_base_ids, user.organization_id)

    agent = Agent(
        organization_id=user.organization_id,
        name=payload.name,
        description=payload.description,
        system_instructions=payload.system_instructions,
        allowed_tools=payload.allowed_tools,
        knowledge_base_ids=[str(kb_id) for kb_id in payload.knowledge_base_ids],
        confidence_threshold=payload.confidence_threshold,
        escalation_policy=payload.escalation_policy,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/agents", response_model=list[AgentOut])
def list_agents(
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[Agent]:
    return (
        db.query(Agent)
        .filter(Agent.organization_id == user.organization_id)
        .order_by(Agent.created_at.desc())
        .all()
    )


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Agent:
    return _get_agent_or_404(db, agent_id, user.organization_id)


@router.put("/agents/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Agent:
    agent = _get_agent_or_404(db, agent_id, user.organization_id)

    updates = payload.model_dump(exclude_unset=True)
    if "allowed_tools" in updates:
        _validate_allowed_tools(db, updates["allowed_tools"])
    if "knowledge_base_ids" in updates:
        _validate_knowledge_base_ids(db, payload.knowledge_base_ids or [], user.organization_id)
        updates["knowledge_base_ids"] = [str(kb_id) for kb_id in (payload.knowledge_base_ids or [])]

    for field, value in updates.items():
        setattr(agent, field, value)

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    agent = _get_agent_or_404(db, agent_id, user.organization_id)
    db.delete(agent)
    db.commit()


@router.post("/playbooks", response_model=PlaybookOut, status_code=status.HTTP_201_CREATED)
def create_playbook(
    payload: PlaybookCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Playbook:
    _get_agent_or_404(db, payload.agent_id, user.organization_id)

    playbook = Playbook(
        agent_id=payload.agent_id,
        name=payload.name,
        intent=payload.intent,
        steps=[step.model_dump() for step in payload.steps],
    )
    db.add(playbook)
    db.commit()
    db.refresh(playbook)
    return playbook


@router.get("/playbooks", response_model=list[PlaybookOut])
def list_playbooks(
    agent_id: uuid.UUID | None = None,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[Playbook]:
    query = db.query(Playbook).join(Agent).filter(Agent.organization_id == user.organization_id)
    if agent_id:
        query = query.filter(Playbook.agent_id == agent_id)
    return query.order_by(Playbook.created_at.desc()).all()


@router.get("/playbooks/{playbook_id}", response_model=PlaybookOut)
def get_playbook(
    playbook_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Playbook:
    return _get_playbook_or_404(db, playbook_id, user.organization_id)


@router.put("/playbooks/{playbook_id}", response_model=PlaybookOut)
def update_playbook(
    playbook_id: uuid.UUID,
    payload: PlaybookUpdate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Playbook:
    playbook = _get_playbook_or_404(db, playbook_id, user.organization_id)

    updates = payload.model_dump(exclude_unset=True)
    if "steps" in updates:
        updates["steps"] = [
            step.model_dump() if hasattr(step, "model_dump") else step for step in (payload.steps or [])
        ]

    for field, value in updates.items():
        setattr(playbook, field, value)

    db.commit()
    db.refresh(playbook)
    return playbook


@router.delete("/playbooks/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playbook(
    playbook_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    playbook = _get_playbook_or_404(db, playbook_id, user.organization_id)
    db.delete(playbook)
    db.commit()

