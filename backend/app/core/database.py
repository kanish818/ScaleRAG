from typing import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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
    _ensure_namespace_schema()
    if not _is_sqlite_url(DATABASE_URL):
        with engine.begin() as connection:
            # Gemini's 768-dimensional output fits pgvector's HNSW vector limit.
            connection.execute(text(
                """
                DO $$
                BEGIN
                    IF (
                        SELECT format_type(a.atttypid, a.atttypmod)
                        FROM pg_attribute a
                        WHERE a.attrelid = 'document_embeddings'::regclass
                          AND a.attname = 'embedding'
                          AND NOT a.attisdropped
                    ) <> 'vector(768)' THEN
                        ALTER TABLE document_embeddings
                        ALTER COLUMN embedding TYPE vector(768)
                        USING subvector(embedding, 1, 768)::vector(768);
                    END IF;
                END
                $$;
                """
            ))
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


def _ensure_namespace_schema() -> None:
    inspector = inspect(engine)
    targets = {
        "documents": "namespace",
        "document_chunks": "namespace",
        "document_embeddings": "namespace",
        "conversations": "namespace",
    }
    for table_name, column_name in targets.items():
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        if column_name in existing:
            continue
        ddl = (
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} VARCHAR NOT NULL DEFAULT 'default'"
        )
        with engine.begin() as connection:
            connection.execute(text(ddl))

    if _is_sqlite_url(DATABASE_URL):
        index_statements = [
            "CREATE INDEX IF NOT EXISTS ix_documents_namespace ON documents (namespace)",
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_namespace ON document_chunks (namespace)",
            "CREATE INDEX IF NOT EXISTS ix_document_embeddings_namespace ON document_embeddings (namespace)",
            "CREATE INDEX IF NOT EXISTS ix_conversations_namespace ON conversations (namespace)",
        ]
    else:
        index_statements = [
            "CREATE INDEX IF NOT EXISTS ix_documents_namespace ON documents (namespace)",
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_namespace ON document_chunks (namespace)",
            "CREATE INDEX IF NOT EXISTS ix_document_embeddings_namespace ON document_embeddings (namespace)",
            "CREATE INDEX IF NOT EXISTS ix_conversations_namespace ON conversations (namespace)",
        ]
    with engine.begin() as connection:
        for stmt in index_statements:
            connection.execute(text(stmt))
