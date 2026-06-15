"""
CSV Parser — Pandas.
Converts CSV files into readable text chunks grouped by rows.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

ROWS_PER_PAGE = 50  # rows per logical "page"


def parse_csv(file_path: str) -> List[Dict[str, Any]]:
    filename = file_path.split("/")[-1].split("\\")[-1]
    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise RuntimeError(f"Cannot parse CSV '{filename}': {exc}") from exc

    df = df.fillna("")
    columns = list(df.columns)
    header_line = "Columns: " + ", ".join(columns)

    pages: List[Dict[str, Any]] = []
    total_rows = len(df)

    for page_start in range(0, max(total_rows, 1), ROWS_PER_PAGE):
        chunk_rows = df.iloc[page_start: page_start + ROWS_PER_PAGE]
        lines = [header_line]
        for _, row in chunk_rows.iterrows():
            line = " | ".join(f"{col}: {row[col]}" for col in columns if row[col])
            if line.strip():
                lines.append(line)
        text = "\n".join(lines).strip()
        if text:
            pages.append({
                "page_num": len(pages) + 1,
                "text": text,
                "filename": filename,
            })

    if not pages:
        pages = [{"page_num": 1, "text": header_line, "filename": filename}]

    logger.info("Parsed %d pages from CSV '%s' (%d rows).", len(pages), filename, total_rows)
    return pages
