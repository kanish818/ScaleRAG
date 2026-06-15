from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Index
from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)
    page_num = Column(Integer, nullable=False, default=0)
    section_heading = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    embedding = Column(Vector(768), nullable=False)


Index("ix_document_chunks_doc_chunk", DocumentChunk.document_id, DocumentChunk.chunk_index, unique=True)
