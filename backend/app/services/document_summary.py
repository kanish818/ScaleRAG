"""Lightweight document summary at ingestion time (no LLM call needed)."""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, List

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "have", "will", "your",
    "into", "about", "their", "there", "these", "those", "been", "being", "were",
    "when", "where", "what", "which", "while", "shall", "would", "could", "should",
    "document", "page", "pages", "using", "used", "within", "only", "each", "also",
}


def _detect_type(filename: str, text: str) -> str:
    low = f"{filename} {text[:3000]}".lower()
    if "resume" in low or "curriculum vitae" in low or "experience" in low:
        return "resume"
    if "training plan" in low or "workout" in low or "diet" in low:
        return "plan"
    if "tutorial" in low or "guide" in low:
        return "tutorial"
    if ".csv" in filename.lower():
        return "data"
    if ".html" in filename.lower() or ".htm" in filename.lower():
        return "webpage"
    return "document"


def _extract_topics(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+\-#.]{2,}", text.lower())
    counts = Counter(t for t in tokens if t not in STOPWORDS)
    return [t for t, _ in counts.most_common(8)]


def summarize_document(pages: List[Dict[str, Any]], filename: str) -> Dict[str, str]:
    texts = [p.get("text", "").strip() for p in pages if p.get("text", "").strip()]
    combined = "\n\n".join(texts)
    intro = " ".join(texts[:2])[:1200].strip()
    summary = intro or combined[:1200]
    return {
        "summary_text": summary,
        "document_type": _detect_type(filename, combined),
        "main_topics_json": json.dumps(_extract_topics(combined)),
    }
