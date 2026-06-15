"""
Hallucination Detection — self-check grounding approach.

Scores an LLM response against the retrieved context chunks using:
  1. Token overlap ratio (lexical grounding)
  2. Unsupported claim detection (sentences with no chunk match)

Returns a score 0–100:
  0   = fully grounded (low hallucination risk)
  100 = completely ungrounded (high hallucination risk)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def score_hallucination(
    response: str,
    context_chunks: List[Dict[str, Any]],
) -> Tuple[int, str]:
    """
    Returns (score, label).
    score: 0–100 (lower = more grounded)
    label: "grounded" | "partial" | "ungrounded"
    """
    if not context_chunks:
        return 50, "partial"  # no context to verify against

    # Build combined context token set
    context_text = " ".join(c.get("text", "") for c in context_chunks)
    context_tokens = _tokenize(context_text)

    sentences = _sentences(response)
    if not sentences:
        return 0, "grounded"

    ungrounded_count = 0
    for sentence in sentences:
        sentence_tokens = _tokenize(sentence)
        # Remove stop words
        content_tokens = {
            t for t in sentence_tokens
            if t not in {
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "have", "has", "had", "do", "does", "did", "will", "would",
                "could", "should", "may", "might", "this", "that", "these",
                "those", "i", "you", "we", "they", "it", "in", "on", "at",
                "to", "for", "of", "and", "or", "but", "not", "with", "from",
            }
        }
        if not content_tokens:
            continue
        overlap = len(content_tokens & context_tokens) / len(content_tokens)
        if overlap < 0.25:
            ungrounded_count += 1

    hallucination_rate = ungrounded_count / len(sentences)
    score = int(hallucination_rate * 100)

    if score <= 20:
        label = "grounded"
    elif score <= 55:
        label = "partial"
    else:
        label = "ungrounded"

    return score, label
