"""
Embedder — Google Gemini gemini-embedding-2 (768 dims).
Batches 100 texts per call with retry + rate-limit handling.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import List, Optional, Callable

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768
BATCH_SIZE = 100
INTER_BATCH_DELAY = 0.1
EMBED_TIMEOUT = 45


def embed_texts(
    texts: List[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    heartbeat: Optional[Callable[[], None]] = None,
) -> List[List[float]]:
    if not texts:
        return []

    all_embeddings: List[List[float]] = []
    total = len(texts)

    for start in range(0, total, BATCH_SIZE):
        batch = texts[start: start + BATCH_SIZE]
        logger.info("Embedding batch %d–%d / %d", start + 1, start + len(batch), total)

        last_exc = None
        for attempt in range(3):
            executor = None
            try:
                if heartbeat:
                    heartbeat()
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(
                    _client.models.embed_content,
                    model=EMBEDDING_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=EMBEDDING_DIMENSIONS,
                    ),
                )
                result = future.result(timeout=EMBED_TIMEOUT)
                all_embeddings.extend(e.values for e in result.embeddings)
                last_exc = None
                break
            except FuturesTimeout as exc:
                last_exc = exc
                logger.error("Embedding timeout after %ds", EMBED_TIMEOUT)
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc):
                    raise RuntimeError("Gemini rate limit (429). Retry later.") from exc
                wait = (attempt + 1) * 2
                logger.warning("Embed attempt %d failed: %s. Retry in %ds", attempt + 1, exc, wait)
                time.sleep(wait)
            finally:
                if executor:
                    executor.shutdown(wait=False, cancel_futures=True)

        if last_exc is not None:
            raise RuntimeError(f"Embedding failed after 3 attempts: {last_exc}") from last_exc

        if start + BATCH_SIZE < total:
            time.sleep(INTER_BATCH_DELAY)

    return all_embeddings


def embed_query(query: str) -> List[float]:
    return embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
