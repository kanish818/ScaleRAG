"""
Text Chunker — semantic paragraph-aware chunking with overlap.

Strategy (justification in README):
  - Paragraph-aware: splits on double newlines first to keep semantic units intact
  - Fixed-size fallback: long paragraphs split at sentence boundaries (~1600 chars)
  - Overlap: 220 chars of trailing context carried into next chunk to preserve
    sentence continuity across chunk boundaries
  - Section heading tracking: heading is attached to each chunk as metadata for
    improved BM25 scoring and citation display
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1600
CHUNK_OVERLAP = 220
MIN_PARAGRAPH_LEN = 40

COMMON_HEADINGS = {
    "summary", "experience", "work experience", "projects", "education",
    "skills", "technical skills", "certifications", "achievements",
    "profile", "objective", "introduction", "overview", "conclusion",
    "abstract", "methodology", "results", "discussion", "references",
}


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long(paragraph: str) -> List[str]:
    if len(paragraph) <= CHUNK_SIZE:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces, current = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        candidate = f"{current} {s}".strip() if current else s
        if len(candidate) <= CHUNK_SIZE:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = s
    if current:
        pieces.append(current)
    return pieces or [paragraph]


def _is_heading(p: str) -> bool:
    text = p.strip().rstrip(":")
    if not text or len(text) > 120:
        return False
    low = text.lower()
    if low in COMMON_HEADINGS:
        return True
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", text):
        return True
    if text.isupper() and len(text.split()) <= 10:
        return True
    if text == text.title() and len(text.split()) <= 8 and not text.endswith("."):
        return True
    return False


def _paragraphs_from_page(text: str) -> List[str]:
    raw = re.split(r"\n{2,}", text)
    result: List[str] = []
    for r in raw:
        c = _clean(r)
        if c:
            result.extend(_split_long(c))
    # merge shorts
    merged, buf = [], ""
    for p in result:
        if _is_heading(p):
            if buf:
                merged.append(buf)
                buf = ""
            merged.append(p)
            continue
        candidate = f"{buf}\n{p}".strip() if buf else p
        if len(buf) < MIN_PARAGRAPH_LEN or len(p) < MIN_PARAGRAPH_LEN:
            buf = candidate
            if len(buf) >= MIN_PARAGRAPH_LEN:
                merged.append(buf)
                buf = ""
        else:
            merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged


def chunk_text(pages: List[Dict[str, Any]], filename: str) -> List[Dict[str, Any]]:
    all_chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for page in pages:
        page_text = page.get("text", "").strip()
        page_num = page.get("page_num", 0)
        if not page_text:
            continue

        paragraphs = _paragraphs_from_page(page_text)
        current_heading = None
        units: List[Dict[str, str]] = []
        for p in paragraphs:
            if _is_heading(p):
                current_heading = p.rstrip(":")
                continue
            units.append({"text": p, "section_heading": current_heading or ""})

        current_units: List[Dict[str, str]] = []
        current_length = 0

        def flush():
            nonlocal current_units, current_length, chunk_index
            if not current_units:
                return
            text = "\n\n".join(u["text"] for u in current_units).strip()
            if text:
                heading = next((u["section_heading"] for u in current_units if u["section_heading"]), "")
                all_chunks.append({
                    "filename": filename,
                    "page_num": page_num,
                    "chunk_index": chunk_index,
                    "section_heading": heading,
                    "text": text,
                })
                chunk_index += 1
            # overlap
            overlap_units, overlap_len = [], 0
            for u in reversed(current_units):
                ul = len(u["text"]) + 2
                if overlap_len + ul > CHUNK_OVERLAP:
                    break
                overlap_units.insert(0, u)
                overlap_len += ul
            current_units[:] = overlap_units
            current_length = overlap_len

        for unit in units:
            ul = len(unit["text"])
            if (
                current_units
                and unit["section_heading"]
                and current_units[-1]["section_heading"] != unit["section_heading"]
                and current_length >= CHUNK_SIZE * 0.6
            ):
                flush()
            if current_units and current_length + ul + 2 > CHUNK_SIZE:
                flush()
            current_units.append(unit)
            current_length += ul + 2

        flush()

    logger.info("Created %d chunks from %d pages of '%s'.", len(all_chunks), len(pages), filename)
    return all_chunks
