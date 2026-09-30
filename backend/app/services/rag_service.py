"""RAG retrieval: embed the query, cosine-similarity search over a knowledge
base's chunks, and return the top-K most relevant ones.

Embeddings are compared in Python rather than pushed down as a pgvector SQL
operator so retrieval behaves identically on SQLite (tests) and PostgreSQL
(production) without dialect-specific query branches. For the chunk volumes
this project targets, loading one knowledge base's embedded chunks and
scoring them in-process is fast enough; a raw pgvector `<=>` KNN query can be
substituted later purely inside this module if profiling shows it's needed.
"""
import math
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.knowledge_base import Document, DocumentChunk, DocumentStatus
from app.services.llm_service import generate_embeddings

TOP_K = 5
MIN_RELEVANCE_SCORE = 0.2  # below this, treat context as insufficient


@dataclass
class RetrievedChunk:
    document_id: uuid.UUID
    document_filename: str
    chunk_id: uuid.UUID
    content: str
    score: float


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve(db: Session, knowledge_base_id: uuid.UUID, query: str, top_k: int = TOP_K) -> list[RetrievedChunk]:
    """Embed `query` and return the top_k most similar chunks in the given
    knowledge base. Returns an empty list if the knowledge base has no
    successfully embedded chunks yet.
    """
    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.knowledge_base_id == knowledge_base_id)
        .filter(Document.status == DocumentStatus.completed.value)
        .all()
    )
    if not rows:
        return []

    query_embedding = generate_embeddings([query])[0]

    scored: list[RetrievedChunk] = []
    for chunk, document in rows:
        if not chunk.embedding:
            continue
        score = _cosine_similarity(query_embedding, list(chunk.embedding))
        scored.append(
            RetrievedChunk(
                document_id=document.id,
                document_filename=document.filename,
                chunk_id=chunk.id,
                content=chunk.content,
                score=score,
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def has_sufficient_context(chunks: list[RetrievedChunk]) -> bool:
    return bool(chunks) and chunks[0].score >= MIN_RELEVANCE_SCORE
