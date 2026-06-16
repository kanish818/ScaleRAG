"""Helpers for namespace normalization and validation."""
from __future__ import annotations

import re

from fastapi import HTTPException, status

DEFAULT_NAMESPACE = "default"
NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def normalize_namespace(value: str | None) -> str:
    raw = (value or DEFAULT_NAMESPACE).strip().lower()
    return raw or DEFAULT_NAMESPACE


def validate_namespace(value: str | None) -> str:
    namespace = normalize_namespace(value)
    if not NAMESPACE_RE.fullmatch(namespace):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Namespace must be 2-63 chars of lowercase letters, digits, hyphen, or underscore.",
        )
    return namespace
