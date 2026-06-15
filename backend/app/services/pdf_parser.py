"""
PDF Parser — PyMuPDF + Tesseract OCR fallback.
Ported from DocuMind with minor cleanup.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

import fitz
import io
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)

OCR_THRESHOLD = 50
OCR_TIMEOUT_SECONDS = 25
OCR_SCALE = 2.5


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_primary_text(page: fitz.Page) -> str:
    try:
        blocks = page.get_text("blocks", sort=True)
    except Exception:
        blocks = []
    parts = [_clean_text(b[4]) for b in blocks if len(b) > 6 and b[6] == 0 and b[4].strip()]
    return "\n\n".join(parts) if parts else _clean_text(page.get_text("text", sort=True))


def _should_try_ocr(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(text) < OCR_THRESHOLD or not compact:
        return True
    return sum(ch.isalpha() for ch in compact) / max(len(compact), 1) < 0.25


def _ocr_page(page: fitz.Page) -> str:
    matrix = fitz.Matrix(OCR_SCALE, OCR_SCALE)
    pix = page.get_pixmap(matrix=matrix)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return _clean_text(
        pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6", timeout=OCR_TIMEOUT_SECONDS)
    )


def parse_pdf(file_path: str, heartbeat: Optional[Callable[[], None]] = None) -> List[Dict[str, Any]]:
    filename = file_path.split("/")[-1].split("\\")[-1]
    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF: {exc}") from exc

    pages: List[Dict[str, Any]] = []
    for idx in range(len(doc)):
        page = doc[idx]
        if heartbeat:
            heartbeat()
        try:
            text = _extract_primary_text(page)
        except Exception:
            text = ""
        if _should_try_ocr(text):
            try:
                ocr = _ocr_page(page)
                if len(ocr) > len(text):
                    text = ocr
            except Exception as exc:
                logger.warning("OCR failed page %d: %s", idx + 1, exc)
        pages.append({"page_num": idx + 1, "text": _clean_text(text), "filename": filename})

    doc.close()
    logger.info("Parsed %d pages from '%s'.", len(pages), filename)
    return pages
