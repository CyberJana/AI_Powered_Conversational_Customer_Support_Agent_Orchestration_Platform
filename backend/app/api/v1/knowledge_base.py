"""Knowledge base and document management endpoints (see docs/api-spec.md)."""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.knowledge_base import Document, KnowledgeBase
from app.models.user import User
from app.schemas.knowledge_base import DocumentOut, KnowledgeBaseCreate, KnowledgeBaseOut
from app.security.dependencies import get_current_user, require_role
from app.services.document_service import SUPPORTED_EXTENSIONS, extension_of
from app.services.ingestion_service import process_document
from app.services.storage_service import read_file, save_file

router = APIRouter()


def _get_knowledge_base_or_404(db: Session, kb_id: uuid.UUID, organization_id: uuid.UUID) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return kb


def _get_document_or_404(db: Session, document_id: uuid.UUID, organization_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.knowledge_base.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("/knowledge-bases", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    kb = KnowledgeBase(organization_id=user.organization_id, name=payload.name, description=payload.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeBase]:
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.organization_id == user.organization_id)
        .order_by(KnowledgeBase.created_at.desc())
        .all()
    )


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Document:
    _get_knowledge_base_or_404(db, kb_id, user.organization_id)

    ext = extension_of(file.filename or "")
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: .{ext or 'unknown'}. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    content = await file.read()

    document = Document(
        knowledge_base_id=kb_id,
        filename=file.filename,
        file_type=ext,
        uploaded_by=user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    document.storage_path = save_file(document.id, document.filename, content)
    db.commit()

    process_document(db, document, content)
    db.refresh(document)
    return document


@router.get("/knowledge-bases/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(
    kb_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Document]:
    _get_knowledge_base_or_404(db, kb_id, user.organization_id)
    return (
        db.query(Document)
        .filter(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    document = _get_document_or_404(db, document_id, user.organization_id)
    db.delete(document)
    db.commit()


@router.post("/documents/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(
    document_id: uuid.UUID,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Document:
    document = _get_document_or_404(db, document_id, user.organization_id)
    if not document.storage_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original file is no longer available for reindexing.",
        )
    content = read_file(document.storage_path)
    process_document(db, document, content)
    db.refresh(document)
    return document

