"""
HTML Parser — BeautifulSoup.
Extracts readable text from HTML files, stripping scripts/styles.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_html(file_path: str) -> List[Dict[str, Any]]:
    filename = file_path.split("/")[-1].split("\\")[-1]
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Split into logical "pages" by top-level headings or every ~3000 chars
    sections: List[str] = []
    current: List[str] = []

    for elem in soup.find_all(["h1", "h2", "h3", "p", "li", "td", "th", "pre", "blockquote"]):
        text = elem.get_text(separator=" ", strip=True)
        if not text:
            continue
        if elem.name in ("h1", "h2") and current:
            sections.append("\n\n".join(current))
            current = []
        current.append(text)
        # flush every ~3000 chars
        if sum(len(t) for t in current) > 3000:
            sections.append("\n\n".join(current))
            current = []

    if current:
        sections.append("\n\n".join(current))

    if not sections:
        sections = [re.sub(r"\s+", " ", soup.get_text()).strip()]

    pages = [
        {"page_num": i + 1, "text": sec.strip(), "filename": filename}
        for i, sec in enumerate(sections)
        if sec.strip()
    ]
    logger.info("Parsed %d sections from HTML '%s'.", len(pages), filename)
    return pages
