"""
Lightweight in-memory fixed-window rate limiting.

This is intentionally simple for a single-process deployment target such as
Render free tier. The limiter keys on user ID when available and falls back to
client IP for unauthenticated routes.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, status


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)

    def enforce(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(int(bucket[0] + window_seconds - now), 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)


rate_limiter = InMemoryRateLimiter()

