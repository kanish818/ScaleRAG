"""Supabase Storage — private bucket for PDF/HTML/CSV files."""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)
TRANSIENT_DOWNLOAD_STATUSES = {502, 503, 504}
DOWNLOAD_RETRIES = 4
DOWNLOAD_RETRY_BASE_DELAY_SECONDS = 2.0


class StorageError(RuntimeError):
    pass


class SupabaseStorageService:
    def __init__(self) -> None:
        self.base_url = settings.SUPABASE_URL.rstrip("/")
        self.bucket = settings.SUPABASE_STORAGE_BUCKET
        self.timeout = httpx.Timeout(120.0, connect=15.0)

    def _headers(self, *, content_type: str | None = None) -> dict:
        h = {
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        }
        if content_type:
            h["Content-Type"] = content_type
        return h

    def is_configured(self) -> bool:
        return bool(self.base_url and settings.SUPABASE_SERVICE_ROLE_KEY and self.bucket)

    def ensure_bucket(self) -> None:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(f"{self.base_url}/storage/v1/bucket", headers=self._headers())
            r.raise_for_status()
            if any(b.get("name") == self.bucket for b in r.json()):
                return
            cr = c.post(
                f"{self.base_url}/storage/v1/bucket",
                headers=self._headers(content_type="application/json"),
                json={"id": self.bucket, "name": self.bucket, "public": False},
            )
            if cr.status_code not in (200, 201, 409):
                raise StorageError(f"Cannot create bucket: {cr.text}")

    def upload_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
                headers={**self._headers(content_type=content_type), "x-upsert": "false"},
                content=content,
            )
            if r.status_code not in (200, 201):
                raise StorageError(f"Upload failed: {r.text}")

    def download_to_tempfile(self, key: str) -> str:
        last_error = None
        for attempt in range(DOWNLOAD_RETRIES):
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.get(
                        f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
                        headers=self._headers(),
                    )
                    if r.status_code == 200:
                        suffix = Path(key).suffix or ".bin"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                            tmp.write(r.content)
                            return tmp.name
                    if r.status_code not in TRANSIENT_DOWNLOAD_STATUSES:
                        raise StorageError(f"Download failed: {r.text}")
                    last_error = StorageError(f"Download failed: {r.text}")
            except (httpx.HTTPError, StorageError) as exc:
                last_error = exc
                is_transient = isinstance(exc, httpx.HTTPError) or any(
                    str(code) in str(exc) for code in TRANSIENT_DOWNLOAD_STATUSES
                )
                if not is_transient or attempt >= DOWNLOAD_RETRIES - 1:
                    break
                wait = DOWNLOAD_RETRY_BASE_DELAY_SECONDS * (attempt + 1)
                logger.warning(
                    "Transient storage download failure for %s on attempt %d/%d: %s. Retrying in %.1fs.",
                    key,
                    attempt + 1,
                    DOWNLOAD_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
        raise StorageError(f"Download failed after retries: {last_error}")

    def delete_object(self, key: str) -> None:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.delete(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{key}",
                headers=self._headers(),
            )
            if r.status_code not in (200, 204, 404):
                raise StorageError(f"Delete failed: {r.text}")


storage_service = SupabaseStorageService()
