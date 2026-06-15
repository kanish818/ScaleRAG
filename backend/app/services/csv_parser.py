"""
CSV Parser — Pandas.

The parser emits paragraph-separated row blocks with explicit lookup keys so
retrieval can target individual field/value records instead of broad page-sized
 CSV blobs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

ROWS_PER_PAGE = 50  # rows per logical "page"
KEY_PRIORITY = [
    "document_id",
    "project",
    "department",
    "region",
    "section",
    "field",
    "value",
    "logical_page",
    "row_number",
]


def _row_to_block(row: Dict[str, str], columns: List[str]) -> str:
    lookup_parts = []
    lines = []

    for key in KEY_PRIORITY:
        value = row.get(key, "")
        if not value:
            continue
        lines.append(f"{key}: {value}")
        if key in {"document_id", "project", "section", "field", "value"}:
            lookup_parts.append(f"{key} {value}")

    for col in columns:
        if col in KEY_PRIORITY:
            continue
        value = row.get(col, "")
        if value:
            lines.append(f"{col}: {value}")

    if lookup_parts:
        lines.insert(0, "Lookup keys: " + " | ".join(lookup_parts))
    return "\n".join(lines).strip()


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

    has_logical_page = "logical_page" in df.columns
    if has_logical_page:
        grouped_rows = []
        for logical_page, page_df in df.groupby("logical_page", sort=False):
            grouped_rows.append((logical_page, page_df))
    else:
        grouped_rows = []
        for page_start in range(0, max(total_rows, 1), ROWS_PER_PAGE):
            page_df = df.iloc[page_start: page_start + ROWS_PER_PAGE]
            grouped_rows.append((len(grouped_rows) + 1, page_df))

    for page_num_raw, page_df in grouped_rows:
        row_blocks = []
        for _, series in page_df.iterrows():
            row = {col: str(series[col]).strip() for col in columns}
            block = _row_to_block(row, columns)
            if block:
                row_blocks.append(block)
        text = "\n\n".join([header_line, *row_blocks]).strip()
        if text:
            try:
                page_num = int(str(page_num_raw).strip())
            except ValueError:
                page_num = len(pages) + 1
            pages.append({
                "page_num": page_num,
                "text": text,
                "filename": filename,
            })

    if not pages:
        pages = [{"page_num": 1, "text": header_line, "filename": filename}]

    logger.info("Parsed %d pages from CSV '%s' (%d rows).", len(pages), filename, total_rows)
    return pages
