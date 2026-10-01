"""Evaluation harness endpoints (FR-15): trigger a run over the fixed
labeled dataset, list past runs, and view a run's full per-case results.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.evaluation.runner import run_evaluation
from app.models.evaluation import Evaluation
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.evaluation import EvaluationDetail, EvaluationOut, EvaluationRunRequest
from app.security.dependencies import require_role

router = APIRouter()


@router.post("/evaluations/run", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED)
def trigger_evaluation(
    payload: EvaluationRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Evaluation:
    if payload.knowledge_base_id is not None:
        kb = db.get(KnowledgeBase, payload.knowledge_base_id)
        if kb is None or kb.organization_id != current_user.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Knowledge base not found")

    return run_evaluation(
        db,
        organization_id=current_user.organization_id,
        name=payload.name,
        created_by=current_user.id,
        knowledge_base_id=payload.knowledge_base_id,
    )


@router.get("/evaluations", response_model=list[EvaluationOut])
def list_evaluations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> list[Evaluation]:
    return (
        db.query(Evaluation)
        .filter(Evaluation.organization_id == current_user.organization_id)
        .order_by(Evaluation.started_at.desc())
        .all()
    )


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetail)
def get_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None or evaluation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found")
    return evaluation

