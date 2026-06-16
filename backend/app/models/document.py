from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger, Text
from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    namespace = Column(String, nullable=False, default="default", index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False, default="pdf")   # pdf | html | csv
    storage_path = Column(String, nullable=True)
    storage_bucket = Column(String, nullable=True)
    file_size = Column(BigInteger, nullable=False, default=0)
    page_count = Column(Integer, nullable=True, default=0)
    chunk_count = Column(Integer, nullable=True, default=0)
    status = Column(String, nullable=False, default="queued")   # queued|processing|ready|error
    processing_attempts = Column(Integer, nullable=False, default=0)
    processing_started_at = Column(DateTime, nullable=True)
    processing_heartbeat_at = Column(DateTime, nullable=True)
    processing_error = Column(String, nullable=True)
    summary_text = Column(Text, nullable=True)
    document_type = Column(String, nullable=True)
    main_topics_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
