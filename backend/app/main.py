"""
ScaleRAG — Production-Grade RAG System
FastAPI application entry point.
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import create_tables, engine, DATABASE_URL
from app.api import auth, documents, chat
from app.services.document_processor import processor
from app.services.supabase_storage import storage_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ScaleRAG API",
    description=(
        "Production-grade RAG assistant. "
        "Supports 10,000+ documents (PDF, HTML, CSV) with hybrid retrieval, "
        "streaming responses, source citations, and hallucination detection."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])


# ── Startup / Shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    logger.info("ScaleRAG starting up …")
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    create_tables()
    if storage_service.is_configured():
        storage_service.ensure_bucket()
    processor.start()
    logger.info("ScaleRAG ready. Docs at /docs | Metrics at /metrics")


@app.on_event("shutdown")
def on_shutdown():
    processor.stop()


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "service": "ScaleRAG", "version": "1.0.0"}


@app.head("/", tags=["Health"], include_in_schema=False)
def health_head():
    return Response(status_code=200)


@app.get("/health", tags=["Health"])
def health_detailed():
    """Detailed health check for load balancers."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"
    return {
        "status": "ok",
        "database": db_status,
        "storage": "configured" if storage_service.is_configured() else "not configured",
    }
