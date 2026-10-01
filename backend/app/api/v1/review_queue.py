"""Continuous learning: human review queue + promoted training examples
(FR-16). Items are captured automatically by chat_service (low confidence,
failed tool calls, failed retrieval) and by the feedback endpoint (negative
feedback). A human agent/admin approves or rejects each item; only
approved items become TrainingExample rows, which app.evaluation.runner
merges into the evaluation dataset for that organization.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.learning import ReviewQueueItem, TrainingExample
from app.models.user import User
from app.schemas.learning import (
    ReviewApproveRequest,
    ReviewQueueItemOut,
    TrainingExampleOut,
)
from app.security.dependencies import require_role

router = APIRouter()


def _get_item_in_org(db: Session, item_id: uuid.UUID, organization_id: uuid.UUID) -> ReviewQueueItem:
    item = db.get(ReviewQueueItem, item_id)
    if item is None or item.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review queue item not found")
    return item


@router.get("/review-queue", response_model=list[ReviewQueueItemOut])
def list_review_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("agent", "admin")),
) -> list[ReviewQueueItem]:
    query = db.query(ReviewQueueItem).filter(ReviewQueueItem.organization_id == current_user.organization_id)
    if status_filter:
        query = query.filter(ReviewQueueItem.status == status_filter)
    if source_type:
        query = query.filter(ReviewQueueItem.source_type == source_type)
    return query.order_by(ReviewQueueItem.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/review-queue/{item_id}/approve", response_model=TrainingExampleOut, status_code=status.HTTP_201_CREATED)
def approve_review_item(
    item_id: uuid.UUID,
    payload: ReviewApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("agent", "admin")),
) -> TrainingExample:
    item = _get_item_in_org(db, item_id, current_user.organization_id)
    if item.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item has already been reviewed")

    if payload.case_type == "intent" and not payload.expected_intent:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expected_intent is required")
    if payload.case_type == "tool" and not payload.tool_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tool_name is required")

    example = TrainingExample(
        organization_id=current_user.organization_id,
        source_review_item_id=item.id,
        case_type=payload.case_type,
        message=item.input_text,
        expected_intent=payload.expected_intent,
        tool_name=payload.tool_name,
        tool_input=payload.tool_input,
        expect_tool_success=payload.expect_tool_success,
        approved_by=current_user.id,
    )
    db.add(example)

    item.status = "approved"
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(example)
    return example


@router.post("/review-queue/{item_id}/reject", response_model=ReviewQueueItemOut)
def reject_review_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("agent", "admin")),
) -> ReviewQueueItem:
    item = _get_item_in_org(db, item_id, current_user.organization_id)
    if item.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item has already been reviewed")

    item.status = "rejected"
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.get("/training-examples", response_model=list[TrainingExampleOut])
def list_training_examples(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> list[TrainingExample]:
    return (
        db.query(TrainingExample)
        .filter(TrainingExample.organization_id == current_user.organization_id)
        .order_by(TrainingExample.created_at.desc())
        .all()
    )
