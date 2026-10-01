"""Tool allow-list endpoint (FR-12). Tools are fixed, code-defined, and NOT
admin-CRUD-editable - only a read-only listing is exposed, matching
docs/api-spec.md (`GET /api/v1/tools`, admin-only).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import Tool
from app.models.user import User
from app.schemas.agent import ToolOut
from app.security.dependencies import require_role

router = APIRouter()


@router.get("/tools", response_model=list[ToolOut])
def list_tools(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> list[Tool]:
    return db.query(Tool).order_by(Tool.name).all()

