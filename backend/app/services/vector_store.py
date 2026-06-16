"""
Postgres vector store — pgvector + HNSW index.
Supports 200K+ vectors with sub-50ms query latency.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import DATABASE_URL, SessionLocal
from app.models.chunk import DocumentChunk, DocumentEmbedding

logger = logging.getLogger(__name__)


def _is_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def add_chunks(
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
    user_id: int,
    doc_id: int,
    namespace: str,
) -> None:
    if not chunks:
        return
    db: Session = SessionLocal()
    try:
        created: List[DocumentChunk] = []
        for chunk in chunks:
            row = DocumentChunk(
                document_id=doc_id,
                user_id=user_id,
                namespace=namespace,
                chunk_index=chunk["chunk_index"],
                filename=chunk["filename"],
                page_num=chunk["page_num"],
                section_heading=chunk.get("section_heading", ""),
                text=chunk["text"],
            )
            db.add(row)
            created.append(row)
        db.flush()

        for chunk_row, emb in zip(created, embeddings):
            db.add(DocumentEmbedding(
                chunk_id=chunk_row.id,
                document_id=doc_id,
                user_id=user_id,
                namespace=namespace,
                embedding=emb,
            ))
        db.commit()
        logger.info("Stored %d chunks for doc_id=%d", len(chunks), doc_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def search(
    query_embedding: List[float],
    user_id: int,
    namespace: str,
    doc_ids: List[int],
    n_results: int = 10,
) -> List[Dict[str, Any]]:
    if not doc_ids:
        return []
    db: Session = SessionLocal()
    try:
        if _is_sqlite():
            stmt = (
                select(DocumentChunk, DocumentEmbedding.embedding)
                .join(DocumentEmbedding, DocumentEmbedding.chunk_id == DocumentChunk.id)
                .where(DocumentEmbedding.user_id == user_id)
                .where(DocumentEmbedding.namespace == namespace)
                .where(DocumentEmbedding.document_id.in_(doc_ids))
            )
            rows = db.execute(stmt).all()
            scored = []
            for chunk, embedding in rows:
                score = _cosine_similarity(query_embedding, embedding)
                scored.append(
                    {
                        "chunk_id": str(chunk.id),
                        "text": chunk.text,
                        "filename": chunk.filename,
                        "page_num": chunk.page_num,
                        "chunk_index": chunk.chunk_index,
                        "section_heading": chunk.section_heading or "",
                        "doc_id": chunk.document_id,
                        "score": score,
                        "vector_score": score,
                    }
                )
            scored.sort(key=lambda item: item["score"], reverse=True)
            return scored[:n_results]

        distance = DocumentEmbedding.embedding.cosine_distance(query_embedding)
        stmt = (
            select(DocumentChunk, distance.label("distance"))
            .join(DocumentEmbedding, DocumentEmbedding.chunk_id == DocumentChunk.id)
            .where(DocumentEmbedding.user_id == user_id)
            .where(DocumentEmbedding.namespace == namespace)
            .where(DocumentEmbedding.document_id.in_(doc_ids))
            .order_by(distance.asc())
            .limit(n_results)
        )
        rows = db.execute(stmt).all()
        return [
            {
                "chunk_id": str(chunk.id),
                "text": chunk.text,
                "filename": chunk.filename,
                "page_num": chunk.page_num,
                "chunk_index": chunk.chunk_index,
                "section_heading": chunk.section_heading or "",
                "doc_id": chunk.document_id,
                "score": 1.0 - float(dist),
                "vector_score": 1.0 - float(dist),
            }
            for chunk, dist in rows
        ]
    finally:
        db.close()


def get_all_chunks_for_docs(user_id: int, namespace: str, doc_ids: List[int]) -> List[Dict[str, Any]]:
    if not doc_ids:
        return []
    db: Session = SessionLocal()
    try:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.user_id == user_id)
            .where(DocumentChunk.namespace == namespace)
            .where(DocumentChunk.document_id.in_(doc_ids))
            .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
        )
        rows = db.execute(stmt).scalars().all()
        return [
            {
                "chunk_id": str(r.id),
                "text": r.text,
                "filename": r.filename,
                "page_num": r.page_num,
                "chunk_index": r.chunk_index,
                "section_heading": r.section_heading or "",
                "doc_id": r.document_id,
            }
            for r in rows
        ]
    finally:
        db.close()


def delete_document(user_id: int, namespace: str, doc_id: int) -> None:
    db: Session = SessionLocal()
    try:
        chunk_ids = db.execute(
            select(DocumentChunk.id)
            .where(DocumentChunk.user_id == user_id)
            .where(DocumentChunk.namespace == namespace)
            .where(DocumentChunk.document_id == doc_id)
        ).scalars().all()
        if chunk_ids:
            db.query(DocumentEmbedding).filter(DocumentEmbedding.chunk_id.in_(chunk_ids)).delete(
                synchronize_session=False
            )
        db.query(DocumentChunk).filter(
            DocumentChunk.user_id == user_id,
            DocumentChunk.namespace == namespace,
            DocumentChunk.document_id == doc_id,
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_namespace(user_id: int, namespace: str) -> None:
    db: Session = SessionLocal()
    try:
        chunk_ids = db.execute(
            select(DocumentChunk.id)
            .where(DocumentChunk.user_id == user_id)
            .where(DocumentChunk.namespace == namespace)
        ).scalars().all()
        if chunk_ids:
            db.query(DocumentEmbedding).filter(DocumentEmbedding.chunk_id.in_(chunk_ids)).delete(
                synchronize_session=False
            )
        db.query(DocumentChunk).filter(
            DocumentChunk.user_id == user_id,
            DocumentChunk.namespace == namespace,
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
