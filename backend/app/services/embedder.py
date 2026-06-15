"""
Embedder service.

Primary provider: Google Gemini `gemini-embedding-2` (768 dims).
Fallback provider: deterministic local hash embeddings (768 dims).

The local fallback keeps ingestion and retrieval available when Gemini is
rate-limited or temporarily unavailable. It is lower quality than Gemini but
stable across documents and queries, so hybrid retrieval can continue working.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Callable, List, Optional

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


class EmbeddingRateLimitError(RuntimeError):
    """Raised when the upstream embedding provider is throttling requests."""


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "quota" in text


def _gemini_wait_seconds(attempt: int) -> int:
    base = max(settings.EMBEDDING_RATE_LIMIT_BASE_DELAY_SECONDS, 1)
    maximum = max(settings.EMBEDDING_RATE_LIMIT_MAX_DELAY_SECONDS, base)
    return min(base * (2 ** attempt), maximum)


def _normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def _accumulate_feature(vector: List[float], token: str, weight: float) -> None:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
    first = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
    second = int.from_bytes(digest[4:8], "big") % EMBEDDING_DIMENSIONS
    first_sign = 1.0 if digest[8] % 2 == 0 else -1.0
    second_sign = 1.0 if digest[9] % 2 == 0 else -1.0
    vector[first] += first_sign * weight
    vector[second] += second_sign * (weight * 0.5)


def _local_hash_embedding(text: str) -> List[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = _tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        weight = 1.0 + min(len(token), 12) / 12.0
        _accumulate_feature(vector, token, weight)

        if len(token) >= 5:
            for idx in range(len(token) - 2):
                trigram = token[idx: idx + 3]
                _accumulate_feature(vector, f"tri:{trigram}", 0.35)

    return _normalize(vector)


def _embed_batch_local(batch: List[str]) -> List[List[float]]:
    logger.warning("Using local hash embeddings fallback for %d texts.", len(batch))
    return [_local_hash_embedding(text) for text in batch]


def _embed_batch_gemini(batch: List[str], task_type: str) -> List[List[float]]:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            _client.models.embed_content,
            model=EMBEDDING_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )
        result = future.result(timeout=settings.EMBEDDING_TIMEOUT_SECONDS)
        return [embedding.values for embedding in result.embeddings]
    except FuturesTimeout as exc:
        raise RuntimeError(
            f"Embedding timeout after {settings.EMBEDDING_TIMEOUT_SECONDS}s"
        ) from exc
    except Exception as exc:
        if _is_rate_limit_error(exc):
            raise EmbeddingRateLimitError("Gemini rate limit (429).") from exc
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def embed_texts(
    texts: List[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    heartbeat: Optional[Callable[[], None]] = None,
) -> List[List[float]]:
    if not texts:
        return []

    all_embeddings: List[List[float]] = []
    batch_size = max(settings.EMBEDDING_BATCH_SIZE, 1)
    total = len(texts)

    for start in range(0, total, batch_size):
        batch = texts[start: start + batch_size]
        logger.info("Embedding batch %d-%d / %d", start + 1, start + len(batch), total)

        embedded = False
        last_exc: Optional[Exception] = None

        for attempt in range(max(settings.EMBEDDING_MAX_RETRIES, 1)):
            try:
                if heartbeat:
                    heartbeat()
                all_embeddings.extend(_embed_batch_gemini(batch, task_type))
                embedded = True
                break
            except EmbeddingRateLimitError as exc:
                last_exc = exc
                if attempt >= max(settings.EMBEDDING_RATE_LIMIT_RETRIES, 0):
                    break
                wait = _gemini_wait_seconds(attempt)
                logger.warning(
                    "Gemini embedding rate-limited on attempt %d. Backing off for %ds.",
                    attempt + 1,
                    wait,
                )
                time.sleep(wait)
            except Exception as exc:
                last_exc = exc
                wait = min((attempt + 1) * 2, 10)
                logger.warning(
                    "Embedding attempt %d failed: %s. Retry in %ds",
                    attempt + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)

        if not embedded:
            if settings.EMBEDDING_LOCAL_FALLBACK_ENABLED:
                all_embeddings.extend(_embed_batch_local(batch))
                embedded = True
            elif last_exc is not None:
                raise RuntimeError(f"Embedding failed after retries: {last_exc}") from last_exc

        if not embedded:
            raise RuntimeError("Embedding failed without a recoverable fallback.")

        if start + batch_size < total:
            time.sleep(max(settings.EMBEDDING_INTER_BATCH_DELAY_SECONDS, 0.0))

    return all_embeddings


def embed_query(query: str) -> List[float]:
    return embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
