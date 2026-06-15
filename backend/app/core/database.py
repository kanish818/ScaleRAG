from typing import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalise_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalise_database_url(settings.DATABASE_URL)


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def _is_supabase_shared_pooler(url: str) -> bool:
    if _is_sqlite_url(url):
        return False
    parsed = make_url(url)
    host = parsed.host or ""
    return host.endswith("pooler.supabase.com")


def _is_transaction_pooler(url: str) -> bool:
    if _is_sqlite_url(url):
        return False
    parsed = make_url(url)
    return _is_supabase_shared_pooler(url) and parsed.port == 6543


def _build_engine():
    kwargs = {"echo": False, "pool_pre_ping": True}
    if _is_sqlite_url(DATABASE_URL):
        parsed = make_url(DATABASE_URL)
        if parsed.database:
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        connect_args = {"sslmode": "require"}
        if _is_transaction_pooler(DATABASE_URL):
            connect_args["prepare_threshold"] = None
            kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = connect_args
    return create_engine(DATABASE_URL, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    from app.models import user, document, conversation, chunk  # noqa: F401

    if not _is_sqlite_url(DATABASE_URL):
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    if not _is_sqlite_url(DATABASE_URL):
        with engine.begin() as connection:
            # HNSW index for fast ANN search at 200K+ vectors
            connection.execute(text(
                """
                CREATE INDEX IF NOT EXISTS ix_doc_embeddings_hnsw
                ON document_embeddings
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
                """
            ))
    logger.info("Database tables created / verified.")
