"""
Reranker — Cohere Rerank API (cross-encoder).
Falls back to local term-overlap scoring if Cohere is unavailable.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from app.core.config import settings

logger = logging.getLogger(__name__)

RRF_K = 60
DOC_ID_RE = re.compile(r"\b([A-Z]+-\d{5})\b", re.IGNORECASE)
FIELD_HINTS = {
    "retention_days": ("retention period", "retention days", "retention"),
    "budget_limit_inr": ("budget limit", "budget", "inr"),
    "sla_hours": ("sla", "hours"),
    "approval_authority": ("approval authority", "approved by", "approval owner"),
    "risk_level": ("risk level", "risk"),
    "verification_marker": ("verification marker", "marker", "verification"),
}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _extract_doc_ids(query: str) -> List[str]:
    return list(dict.fromkeys(match.upper() for match in DOC_ID_RE.findall(query or "")))


def _term_overlap(query_tokens: List[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokenize(text))
    matched = sum(1 for t in query_tokens if t in text_tokens)
    return matched / max(len(set(query_tokens)), 1)


def _field_match_bonus(query: str, text: str) -> float:
    low_query = query.lower()
    low_text = text.lower()
    bonus = 0.0
    for canonical_field, patterns in FIELD_HINTS.items():
        if any(pattern in low_query for pattern in patterns):
            if f"field: {canonical_field}" in low_text:
                bonus += 1.8
            elif canonical_field in low_text:
                bonus += 0.8
    return bonus


def _doc_id_bonus(query: str, text: str, filename: str) -> float:
    query_doc_ids = _extract_doc_ids(query)
    if not query_doc_ids:
        return 0.0
    haystack = f"{filename}\n{text}".upper()
    if any(doc_id in haystack for doc_id in query_doc_ids):
        return 2.4
    return -1.2


def _local_rerank(query: str, results: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
    """Fallback: term-overlap + exact phrase + section heading boost."""
    query_tokens = _tokenize(query)
    lowered = query.lower()
    scored = []
    for item in results:
        text = item.get("text", "")
        filename = item.get("filename", "")
        overlap = _term_overlap(query_tokens, text)
        section_overlap = _term_overlap(query_tokens, item.get("section_heading", ""))
        exact_bonus = 0.2 if lowered in text.lower() else 0.0
        field_bonus = _field_match_bonus(query, text)
        doc_id_bonus = _doc_id_bonus(query, text, filename)
        score = (
            float(item.get("score", 0.0))
            + overlap * 1.1
            + section_overlap * 0.35
            + exact_bonus
            + field_bonus
            + doc_id_bonus
        )
        scored.append({**item, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def rerank(
    query: str,
    results: List[Dict[str, Any]],
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Rerank retrieved chunks using Cohere Rerank API.
    Falls back to local scoring if Cohere key not set or request fails.
    """
    if not results:
        return []

    cohere_key = settings.COHERE_API_KEY
    if not cohere_key:
        logger.warning("COHERE_API_KEY not set — using local reranker fallback.")
        return _local_rerank(query, results, top_n)

    try:
        import cohere
        co = cohere.ClientV2(api_key=cohere_key)
        docs = [r.get("text", "")[:512] for r in results]
        response = co.rerank(
            model="rerank-v3.5",
            query=query,
            documents=docs,
            top_n=top_n,
        )
        reranked = []
        for hit in response.results:
            item = dict(results[hit.index])
            item["score"] = hit.relevance_score
            reranked.append(item)
        logger.info("Cohere reranker returned %d results.", len(reranked))
        return reranked
    except Exception as exc:
        logger.warning("Cohere rerank failed (%s) — falling back to local reranker.", exc)
        return _local_rerank(query, results, top_n)
