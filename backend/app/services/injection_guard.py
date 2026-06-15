"""
Prompt injection defense.

Two layers are implemented:
  1. Block unsafe user questions before retrieval/generation
  2. Sanitize retrieved document text so hostile instructions embedded inside
     documents are not forwarded verbatim to the model
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Patterns commonly used in prompt injection attacks
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|system)\s+(instructions?|prompts?|rules?|context)",
    r"forget\s+(all\s+)?(previous|prior|above|system)\s+(instructions?|prompts?|rules?)",
    r"you\s+are\s+now\s+(a\s+)?(different|new|another|evil|jailbroken)",
    r"act\s+as\s+(if\s+you\s+are\s+)?(a\s+)?(different|new|evil|unfiltered|dan|jailbroken)",
    r"do\s+not\s+follow\s+(your\s+)?(instructions?|guidelines?|rules?|restrictions?)",
    r"disregard\s+(all\s+)?(previous|prior|your)\s+(instructions?|prompts?|rules?)",
    r"your\s+new\s+(role|persona|task|instruction|prompt)\s+is",
    r"(system|admin|root)\s*:\s*\[",
    r"\[system\]|\[admin\]|\[override\]|\[jailbreak\]",
    r"pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(different|unrestricted|evil|dan)",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions?|api\s+key)",
    r"print\s+(your\s+)?(system\s+prompt|instructions?|configuration)",
]

_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS]
_LINE_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Max allowed question length
MAX_QUESTION_LEN = 2000


def check_injection(text: str) -> Tuple[bool, str]:
    """
    Returns (is_safe, reason).
    is_safe=True means the input is clean.
    """
    if len(text) > MAX_QUESTION_LEN:
        return False, f"Question exceeds maximum length of {MAX_QUESTION_LEN} characters."

    for pattern in _COMPILED:
        if pattern.search(text):
            return False, "Your message contains content that cannot be processed."

    return True, ""


def sanitize_retrieved_chunks(chunks: List[Dict]) -> Tuple[List[Dict], int]:
    """
    Remove document lines that look like instruction overrides.

    This protects the generation step against prompt injection buried inside the
    retrieved context itself. The function returns (sanitized_chunks, line_count).
    """
    sanitized: List[Dict] = []
    removed_lines = 0

    for chunk in chunks:
        text = chunk.get("text", "")
        kept_lines = []
        chunk_removed = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and any(pattern.search(stripped) for pattern in _LINE_COMPILED):
                removed_lines += 1
                chunk_removed = True
                continue
            kept_lines.append(line)

        cleaned_text = "\n".join(kept_lines).strip()
        if not cleaned_text:
            continue

        sanitized.append(
            {
                **chunk,
                "text": cleaned_text,
                "sanitized": chunk_removed,
            }
        )

    return sanitized, removed_lines
