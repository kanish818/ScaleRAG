"""
Chat router — conversations + SSE streaming with hallucination scoring.
"""
import json
import logging
import re
from typing import AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.conversation import Conversation, ConversationDocument, Message
from app.models.document import Document
from app.models.user import User
from app.services.embedder import embed_query
from app.services.hallucination_guard import score_hallucination
from app.services.injection_guard import check_injection, sanitize_retrieved_chunks
from app.services.llm import stream_chat
from app.services.namespaces import DEFAULT_NAMESPACE, validate_namespace
from app.services.rate_limiter import rate_limiter
from app.services.retriever import choose_top_k, hybrid_search

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    document_ids: Optional[List[int]] = []
    namespace: Optional[str] = DEFAULT_NAMESPACE


class ConversationOut(BaseModel):
    id: int
    title: str
    namespace: str
    created_at: str
    message_count: int
    document_ids: List[int] = []


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[List[dict]] = None
    hallucination_score: Optional[int] = None
    created_at: str


class StreamRequest(BaseModel):
    question: str
    document_ids: List[int] = []
    namespace: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_sources(raw: Optional[str]) -> Optional[List[dict]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _get_conv(conv_id: int, user_id: int, db: Session) -> Conversation:
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id, Conversation.user_id == user_id
    ).first()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return conv


def _conv_doc_ids(conv_id: int, db: Session) -> List[int]:
    rows = db.query(ConversationDocument.document_id).filter(
        ConversationDocument.conversation_id == conv_id
    ).all()
    return [r.document_id for r in rows]


def _persist_conv_docs(conv_id: int, doc_ids: List[int], db: Session) -> List[int]:
    existing = set(_conv_doc_ids(conv_id, db))
    new = [d for d in doc_ids if d not in existing]
    if new:
        db.add_all([ConversationDocument(conversation_id=conv_id, document_id=d) for d in new])
        db.commit()
    return _conv_doc_ids(conv_id, db)


def _allowed_docs(user_id: int, namespace: str, doc_ids: List[int], db: Session) -> List[Document]:
    if not doc_ids:
        return []
    return db.query(Document).filter(
        Document.user_id == user_id,
        Document.namespace == namespace,
        Document.status == "ready",
        Document.id.in_(doc_ids),
    ).all()


def _build_history(conv_id: int, newest_id: int, allowed_docs: List[Document], db: Session) -> List[dict]:
    allowed_files = {d.filename for d in allowed_docs}
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id, Message.id != newest_id)
        .order_by(Message.created_at.asc())
        .limit(12)
        .all()
    )
    history = []
    for msg in rows:
        if msg.role == "user":
            history.append({"role": "user", "content": msg.content})
            continue
        sources = _parse_sources(msg.sources)
        if not sources:
            continue
        src_files = {s.get("filename", "") for s in sources if s.get("filename")}
        if src_files and src_files.issubset(allowed_files):
            history.append({"role": "assistant", "content": msg.content})
    return history[-10:]


def _is_summary(q: str) -> bool:
    return any(t in q.lower() for t in ("summary", "summarize", "overview", "important points"))


def _inject_summaries(chunks: List[dict], docs: List[Document], question: str) -> List[dict]:
    if not _is_summary(question):
        return chunks
    summary_chunks = [
        {
            "chunk_id": f"summary-{d.id}", "text": d.summary_text,
            "filename": d.filename, "page_num": 1,
            "chunk_index": -1, "section_heading": "Document Summary",
            "doc_id": d.id, "score": 2.0,
        }
        for d in docs if d.summary_text
    ]
    return summary_chunks + chunks if summary_chunks else chunks


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).all()
    result = []
    for conv in convs:
        count = db.query(Message).filter(Message.conversation_id == conv.id).count()
        doc_ids = _conv_doc_ids(conv.id, db)
        result.append(ConversationOut(
            id=conv.id, title=conv.title,
            namespace=conv.namespace or DEFAULT_NAMESPACE,
            created_at=conv.created_at.isoformat() if conv.created_at else "",
            message_count=count, document_ids=doc_ids,
        ))
    return result


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    namespace = validate_namespace(payload.namespace)
    doc_ids = list(dict.fromkeys(payload.document_ids or []))
    if doc_ids:
        owned_docs = _allowed_docs(current_user.id, namespace, doc_ids, db)
        owned = {d.id for d in owned_docs}
        invalid = [d for d in doc_ids if d not in owned]
        if invalid:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Invalid document IDs: {invalid}")
        if any((d.namespace or DEFAULT_NAMESPACE) != namespace for d in owned_docs):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "All conversation documents must belong to the same namespace.")

    conv = Conversation(user_id=current_user.id, namespace=namespace, title=payload.title or "New Conversation")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    if doc_ids:
        db.add_all([ConversationDocument(conversation_id=conv.id, document_id=d) for d in doc_ids])
        db.commit()

    return ConversationOut(
        id=conv.id, title=conv.title,
        namespace=conv.namespace or DEFAULT_NAMESPACE,
        created_at=conv.created_at.isoformat() if conv.created_at else "",
        message_count=0, document_ids=doc_ids,
    )


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_conv(conv_id, current_user.id, db)
    db.query(ConversationDocument).filter(ConversationDocument.conversation_id == conv_id).delete()
    db.query(Message).filter(Message.conversation_id == conv_id).delete()
    db.delete(conv)
    db.commit()


@router.get("/conversations/{conv_id}/messages", response_model=List[MessageOut])
def get_messages(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_conv(conv_id, current_user.id, db)
    msgs = db.query(Message).filter(
        Message.conversation_id == conv_id
    ).order_by(Message.created_at.asc()).all()
    return [
        MessageOut(
            id=m.id, role=m.role, content=m.content,
            sources=_parse_sources(m.sources),
            hallucination_score=m.hallucination_score,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in msgs
    ]


@router.post("/conversations/{conv_id}/stream")
async def stream_conversation(
    conv_id: int,
    payload: StreamRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    SSE streaming endpoint.
    Events: chunk | sources | hallucination | done | error
    """
    _get_conv(conv_id, current_user.id, db)
    rate_limiter.enforce(f"chat:user:{current_user.id}", settings.RATE_LIMIT_RPM)

    question = payload.question.strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Question is empty.")

    # Prompt injection defense
    is_safe, reason = check_injection(question)
    if not is_safe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)

    conv = _get_conv(conv_id, current_user.id, db)
    conv_namespace = conv.namespace or DEFAULT_NAMESPACE
    scoped_ids = _conv_doc_ids(conv_id, db)
    requested_ids = list(dict.fromkeys(payload.document_ids or []))
    requested_namespace = validate_namespace(payload.namespace or conv_namespace)
    if requested_namespace != conv_namespace:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Conversation namespace cannot be changed.")

    if scoped_ids:
        doc_ids = scoped_ids
    else:
        doc_ids = requested_ids
        if doc_ids:
            doc_ids = _persist_conv_docs(conv_id, doc_ids, db)

    allowed_docs = _allowed_docs(current_user.id, conv_namespace, doc_ids, db)
    allowed_ids = {d.id for d in allowed_docs}
    invalid = [d for d in doc_ids if d not in allowed_ids]
    if invalid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Invalid document IDs: {invalid}")

    user_msg = Message(conversation_id=conv_id, role="user", content=question)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    chat_history = _build_history(conv_id, user_msg.id, allowed_docs, db)
    user_id = current_user.id

    async def generate() -> AsyncGenerator[str, None]:
        if not doc_ids:
            msg = "Please start a new conversation and select a document first."
            yield f"data: {json.dumps({'type': 'chunk', 'content': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # Embed query
        try:
            q_emb = embed_query(question)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            return

        # Hybrid retrieval
        chunks = []
        try:
            chunks = hybrid_search(
                query=question, query_embedding=q_emb,
                user_id=user_id, namespace=conv_namespace, doc_ids=doc_ids,
                n_results=choose_top_k(question),
            )
        except Exception as exc:
            logger.error("Retrieval error: %s", exc)

        chunks = _inject_summaries(chunks, allowed_docs, question)
        chunks, sanitized_lines = sanitize_retrieved_chunks(chunks)
        if sanitized_lines:
            logger.warning(
                "Removed %d suspicious retrieved lines before generation for conv_id=%d",
                sanitized_lines,
                conv_id,
            )

        # Stream LLM
        full_response = ""
        try:
            for token in stream_chat(question=question, context_chunks=chunks, chat_history=chat_history):
                full_response += token
                yield f"data: {json.dumps({'type': 'chunk', 'content': token})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
            return

        # Hallucination scoring
        h_score, h_label = score_hallucination(full_response, chunks)

        # Sources
        seen = set()
        sources = []
        for chunk in chunks:
            key = (chunk.get("filename", ""), chunk.get("page_num", 0), chunk.get("chunk_index", -1))
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "filename": chunk.get("filename", ""),
                    "page_num": chunk.get("page_num", 0),
                    "text": chunk.get("text", "")[:400],
                }
            )

        # Persist assistant message
        from app.core.database import SessionLocal
        save_db = SessionLocal()
        try:
            save_db.add(Message(
                conversation_id=conv_id,
                role="assistant",
                content=full_response,
                sources=json.dumps(sources) if sources else None,
                hallucination_score=h_score,
            ))
            save_db.commit()
        except Exception as exc:
            logger.error("Failed to save assistant message: %s", exc)
        finally:
            save_db.close()

        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'hallucination', 'score': h_score, 'label': h_label})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
