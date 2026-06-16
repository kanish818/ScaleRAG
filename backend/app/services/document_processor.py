"""
Durable document processing worker.
Handles PDF, HTML, and CSV with batched embedding + retry logic.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.document import Document
from app.services import vector_store
from app.services.chunker import chunk_text
from app.services.csv_parser import chunk_csv_pages
from app.services.document_summary import summarize_document
from app.services.embedder import embed_texts
from app.services.supabase_storage import storage_service

logger = logging.getLogger(__name__)

HEARTBEAT_STALE_MINUTES = 10
MAX_ATTEMPTS = 3
SUPERVISOR_INTERVAL = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_file(temp_path: str, file_type: str, heartbeat=None):
    """Route to correct parser based on file type."""
    if file_type == "html":
        from app.services.html_parser import parse_html
        return parse_html(temp_path)
    elif file_type == "csv":
        from app.services.csv_parser import parse_csv
        return parse_csv(temp_path)
    else:
        from app.services.pdf_parser import parse_pdf
        return parse_pdf(temp_path, heartbeat=heartbeat)


class DocumentProcessor:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._queued_ids: set = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._supervisor: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self.ensure_running()
        self._start_supervisor()
        self._recover()
        logger.info("Document processor started.")

    def stop(self) -> None:
        self._stop.set()
        for t in [*self._workers, self._supervisor]:
            if t and t.is_alive():
                t.join(timeout=5)
        self._workers = []
        logger.info("Document processor stopped.")

    def ensure_running(self) -> None:
        desired_workers = max(1, settings.DOCUMENT_PROCESSOR_WORKERS)
        self._workers = [worker for worker in self._workers if worker.is_alive()]
        while len(self._workers) < desired_workers:
            worker_id = len(self._workers) + 1
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"doc-worker-{worker_id}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def _start_supervisor(self) -> None:
        if self._supervisor and self._supervisor.is_alive():
            return
        self._supervisor = threading.Thread(target=self._supervisor_loop, name="doc-supervisor", daemon=True)
        self._supervisor.start()

    def enqueue(self, doc_id: int) -> None:
        self.ensure_running()
        with self._lock:
            if doc_id in self._queued_ids:
                return
            self._queued_ids.add(doc_id)
        self._queue.put(doc_id)

    def _recover(self) -> None:
        db = SessionLocal()
        cutoff = _utcnow() - timedelta(minutes=HEARTBEAT_STALE_MINUTES)
        try:
            stale = (
                db.query(Document)
                .filter(Document.status.in_(("queued", "processing")))
                .filter(or_(
                    Document.processing_heartbeat_at.is_(None),
                    Document.processing_heartbeat_at < cutoff,
                ))
                .all()
            )
            for doc in stale:
                if (doc.processing_attempts or 0) >= MAX_ATTEMPTS:
                    doc.status = "error"
                    doc.processing_error = "Exceeded retry limit."
                else:
                    doc.status = "queued"
                    doc.processing_error = "Recovered after interruption."
                doc.processing_heartbeat_at = _utcnow()
                doc.updated_at = _utcnow()
            if stale:
                db.commit()
                logger.warning("Recovered %d stale jobs.", len(stale))
            # Re-enqueue all pending
            pending = db.query(Document).filter(Document.status.in_(("queued",))).all()
            for d in pending:
                self.enqueue(d.id)
        finally:
            db.close()

    def _supervisor_loop(self) -> None:
        while not self._stop.wait(SUPERVISOR_INTERVAL):
            try:
                self.ensure_running()
                self._recover()
            except Exception:
                logger.exception("Supervisor iteration failed.")

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                doc_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._process(doc_id)
            except Exception:
                logger.exception("Unhandled failure for doc_id=%d", doc_id)
            finally:
                with self._lock:
                    self._queued_ids.discard(doc_id)
                self._queue.task_done()

    def _heartbeat(self, db, doc: Document) -> None:
        doc.processing_heartbeat_at = _utcnow()
        doc.updated_at = _utcnow()
        db.commit()

    def _process(self, doc_id: int) -> None:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc or doc.status == "ready":
                return
            if not doc.storage_path:
                doc.status = "error"
                doc.processing_error = "File reference missing."
                db.commit()
                return

            doc.status = "processing"
            doc.processing_attempts = (doc.processing_attempts or 0) + 1
            doc.processing_started_at = _utcnow()
            doc.processing_heartbeat_at = _utcnow()
            doc.processing_error = None
            doc.updated_at = _utcnow()
            db.commit()

            temp_path = storage_service.download_to_tempfile(doc.storage_path)
            try:
                pages = _parse_file(temp_path, doc.file_type or "pdf", heartbeat=lambda: self._heartbeat(db, doc))
                self._heartbeat(db, doc)

                if (doc.file_type or "pdf") == "csv":
                    chunks = chunk_csv_pages(pages, doc.filename)
                else:
                    chunks = chunk_text(pages, doc.filename)
                if not chunks:
                    raise RuntimeError("No extractable text found in this file.")
                self._heartbeat(db, doc)

                summary = summarize_document(pages, doc.filename)
                self._heartbeat(db, doc)

                texts = [c["text"] for c in chunks]
                embeddings = embed_texts(texts, task_type="RETRIEVAL_DOCUMENT", heartbeat=lambda: self._heartbeat(db, doc))

                vector_store.delete_document(user_id=doc.user_id, namespace=doc.namespace or "default", doc_id=doc.id)
                vector_store.add_chunks(
                    chunks=chunks,
                    embeddings=embeddings,
                    user_id=doc.user_id,
                    doc_id=doc.id,
                    namespace=doc.namespace or "default",
                )

                doc.page_count = len(pages)
                doc.chunk_count = len(chunks)
                doc.summary_text = summary["summary_text"]
                doc.document_type = summary["document_type"]
                doc.main_topics_json = summary["main_topics_json"]
                doc.status = "ready"
                doc.processing_error = None
                doc.processing_started_at = None
                doc.processing_heartbeat_at = _utcnow()
                doc.updated_at = _utcnow()
                db.commit()
                logger.info("doc_id=%d ready: %d pages, %d chunks.", doc.id, len(pages), len(chunks))
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except Exception as exc:
            logger.error("Processing failed doc_id=%d: %s", doc_id, exc, exc_info=True)
            db.rollback()
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.status = "error"
                doc.processing_error = str(exc)[:1000]
                doc.processing_started_at = None
                doc.processing_heartbeat_at = _utcnow()
                doc.updated_at = _utcnow()
                db.commit()
        finally:
            db.close()


processor = DocumentProcessor()
