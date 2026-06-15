"""
Documents router — upload, list, delete.
Supports PDF, HTML, CSV formats.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.services import vector_store
from app.services.document_processor import processor
from app.services.rate_limiter import rate_limiter
from app.services.supabase_storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf": ("application/pdf", "pdf"),
    ".html": ("text/html", "html"),
    ".htm": ("text/html", "html"),
    ".csv": ("text/csv", "csv"),
}


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    status: str
    processing_error: Optional[str] = None
    summary_text: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    model_config = {"from_attributes": True}


def _doc_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.id, filename=d.filename, file_type=d.file_type or "pdf",
        file_size=d.file_size, page_count=d.page_count, chunk_count=d.chunk_count,
        status=d.status, processing_error=d.processing_error, summary_text=d.summary_text,
        created_at=d.created_at.isoformat() if d.created_at else "",
        updated_at=d.updated_at.isoformat() if d.updated_at else "",
    )


@router.post("/upload", response_model=List[DocumentOut], status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    request: Request,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload PDF, HTML, or CSV files for ingestion."""
    rate_limiter.enforce(
        f"upload:user:{current_user.id}",
        settings.UPLOAD_RATE_LIMIT_RPM,
    )
    if not storage_service.is_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Storage backend is not configured. Set Supabase environment variables first.",
        )

    created: List[Document] = []

    for upload in files:
        fname = upload.filename or ""
        ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"'{fname}' — unsupported format. Allowed: PDF, HTML, CSV.",
            )
        _, file_type = ALLOWED_EXTENSIONS[ext]
        content_type, _ = ALLOWED_EXTENSIONS[ext]

        content = await upload.read()
        if len(content) == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{fname}' is empty.")
        if len(content) > MAX_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"'{fname}' exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit.")

        key = f"{current_user.id}/{uuid.uuid4().hex}_{fname}"
        try:
            storage_service.upload_bytes(key, content, upload.content_type or content_type)
        except Exception as exc:
            logger.error("Storage upload failed: %s", exc)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Storage upload failed. Try again.")

        doc = Document(
            user_id=current_user.id, filename=fname, file_type=file_type,
            storage_path=key, storage_bucket=settings.SUPABASE_STORAGE_BUCKET,
            file_size=len(content), status="queued",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        processor.enqueue(doc.id)
        created.append(doc)
        logger.info("Queued doc_id=%d '%s' (%s)", doc.id, fname, file_type)

    return [_doc_out(d) for d in created]


@router.get("/", response_model=List[DocumentOut])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    processor.ensure_running()
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [_doc_out(d) for d in docs]


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")

    vector_store.delete_document(user_id=current_user.id, doc_id=doc_id)
    if doc.storage_path:
        try:
            storage_service.delete_object(doc.storage_path)
        except Exception as exc:
            logger.warning("Storage delete failed for doc_id=%d: %s", doc_id, exc)

    db.delete(doc)
    db.commit()
