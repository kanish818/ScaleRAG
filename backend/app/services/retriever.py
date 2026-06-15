"""
Hybrid Retrieval Pipeline:
  1. Dense vector search (pgvector + HNSW)
  2. Sparse BM25 keyword search
  3. RRF fusion
  4. Cohere reranker (cross-encoder)
  5. Context compression (trim low-signal tokens)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from rank_bm25 import BM25Okapi

from app.services import vector_store
from app.services.reranker import rerank

logger = logging.getLogger(__name__)

RRF_K = 60
SUMMARY_HINTS = ("summary", "summarize", "overview", "important points", "main points")
ACTION_HINTS = ("action", "next step", "todo", "task", "recommendation", "plan")
# Max chars per chunk after context compression
COMPRESSED_CHUNK_CHARS = 600


def expand_query(query: str) -> str:
    low = query.lower()
    hints = []
    if any(h in low for h in SUMMARY_HINTS):
        hints.append("summary overview main points key ideas important details")
    if any(h in low for h in ACTION_HINTS):
        hints.append("action items tasks recommendations instructions steps")
    if "name" in low:
        hints.append("name full name person candidate author")
    if "skill" in low:
        hints.append("skills technologies tools frameworks expertise")
    if "project" in low:
        hints.append("projects work experience accomplishments")
    return f"{query} {' '.join(hints)}".strip() if hints else query


def choose_top_k(query: str) -> int:
    low = query.lower()
    return 8 if any(h in low for h in SUMMARY_HINTS + ACTION_HINTS) else 5


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _rrf(ranked_lists: List[List[Dict[str, Any]]], key: str = "chunk_id") -> List[Dict[str, Any]]:
    scores: Dict[str, float] = {}
    item_map: Dict[str, Dict[str, Any]] = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst):
            k = item[key]
            scores[k] = scores.get(k, 0.0) + 1.0 / (rank + 1 + RRF_K)
            item_map.setdefault(k, item)
    return [
        {**item_map[k], "score": scores[k]}
        for k in sorted(scores, key=lambda x: scores[x], reverse=True)
    ]


def _compress_context(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Trim each chunk to COMPRESSED_CHUNK_CHARS to reduce prompt token count
    while keeping the most relevant leading sentences.
    """
    compressed = []
    for chunk in chunks:
        text = chunk.get("text", "")
        if len(text) > COMPRESSED_CHUNK_CHARS:
            # Keep leading sentences up to limit
            sentences = re.split(r"(?<=[.!?])\s+", text)
            result, total = [], 0
            for s in sentences:
                if total + len(s) > COMPRESSED_CHUNK_CHARS:
                    break
                result.append(s)
                total += len(s) + 1
            text = " ".join(result) if result else text[:COMPRESSED_CHUNK_CHARS]
        compressed.append({**chunk, "text": text})
    return compressed


def hybrid_search(
    query: str,
    query_embedding: List[float],
    user_id: int,
    doc_ids: List[int],
    n_results: int = 5,
) -> List[Dict[str, Any]]:
    if not doc_ids:
        return []

    expanded = expand_query(query)

    # 1. Dense vector search
    vector_results = vector_store.search(
        query_embedding=query_embedding,
        user_id=user_id,
        doc_ids=doc_ids,
        n_results=max(n_results * 3, 15),
    )
    logger.info("Vector search: %d results", len(vector_results))

    # 2. BM25 sparse search
    all_chunks = vector_store.get_all_chunks_for_docs(user_id=user_id, doc_ids=doc_ids)
    bm25_results: List[Dict[str, Any]] = []
    if all_chunks:
        corpus = [_tokenize(c["text"]) for c in all_chunks]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tokenize(expanded))
        scored = sorted(zip(all_chunks, scores), key=lambda x: x[1], reverse=True)
        for chunk, score in scored[:15]:
            bm25_results.append({
                **chunk,
                "score": float(score),
                "bm25_score": float(score),
            })
    logger.info("BM25 search: %d results", len(bm25_results))

    # 3. RRF fusion
    fused = _rrf([vector_results, bm25_results])
    logger.info("RRF fusion: %d unique results", len(fused))

    # 4. Cohere reranker
    reranked = rerank(query=query, results=fused, top_n=n_results)
    logger.info("Reranker: %d results", len(reranked))

    # 5. Context compression
    return _compress_context(reranked)
