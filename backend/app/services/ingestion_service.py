"""Orchestrates document ingestion: extract -> chunk -> embed -> persist.

Runs synchronously within the upload/reindex request. Document.status
transitions PENDING -> PROCESSING -> COMPLETED | FAILED (see
docs/api-spec.md). No background worker exists yet, so callers should be
mindful this is a blocking call for large documents.
"""
from sqlalchemy.orm import Session

from app.models.knowledge_base import Document, DocumentChunk, DocumentStatus
from app.services.chunking_service import chunk_text
from app.services.document_service import extract_text
from app.services.llm_service import OpenAIKeyMissingError, generate_embeddings


def process_document(db: Session, document: Document, content: bytes) -> None:
    document.status = DocumentStatus.processing.value
    document.error_message = None
    db.commit()

    try:
        text = extract_text(document.filename, content)
        chunks = chunk_text(text)
        if not chunks:
            document.status = DocumentStatus.failed.value
            document.error_message = "No extractable text content was found in the document."
            db.commit()
            return

        embeddings = generate_embeddings(chunks)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=embedding,
                )
            )

        document.status = DocumentStatus.completed.value
        document.error_message = None
        db.commit()
    except OpenAIKeyMissingError as exc:
        db.rollback()
        document.status = DocumentStatus.failed.value
        document.error_message = str(exc)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - persist any ingestion failure on the document
        db.rollback()
        document.status = DocumentStatus.failed.value
        document.error_message = f"Processing failed: {exc}"
        db.commit()
