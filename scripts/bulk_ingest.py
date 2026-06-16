"""
Bulk ingestion script — uploads documents to ScaleRAG in parallel batches.
Used for 10K+ scale testing.

Usage:
    # First register a user and get a token
    python scripts/bulk_ingest.py --dir ./test_docs --url http://localhost:8000 \
        --token YOUR_JWT_TOKEN --workers 1 --batch-size 25 --poll-ready
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List

import httpx

ALLOWED_EXT = {".pdf", ".html", ".htm", ".csv"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

def _content_type(file_path: Path) -> str:
    if file_path.suffix.lower() == ".pdf":
        return "application/pdf"
    if file_path.suffix.lower() in (".html", ".htm"):
        return "text/html"
    return "text/csv"


def _batches(files: List[Path], batch_size: int) -> Iterable[List[Path]]:
    for start in range(0, len(files), batch_size):
        yield files[start:start + batch_size]


def upload_batch(
    file_paths: List[Path],
    base_url: str,
    token: str,
    namespace: str | None,
    timeout: int,
    max_retries: int,
) -> dict:
    url = f"{base_url}/api/documents/upload"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"namespace": namespace} if namespace else None

    for attempt in range(1, max_retries + 1):
        files = []
        handles = []
        try:
            for file_path in file_paths:
                handle = open(file_path, "rb")
                handles.append(handle)
                files.append(("files", (file_path.name, handle, _content_type(file_path))))

            resp = httpx.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=timeout,
            )

            if resp.status_code in RETRYABLE_STATUS_CODES:
                if attempt == max_retries:
                    resp.raise_for_status()
                print(
                    f"upload-batch:{file_paths[0].name}...{file_paths[-1].name}: "
                    f"retry {attempt}/{max_retries} after transient error"
                )
                time.sleep(min(2 * attempt, 10))
                continue

            resp.raise_for_status()
            payload = resp.json()
            return {
                "files": [file_path.name for file_path in file_paths],
                "ids": [item["id"] for item in payload],
                "count": len(payload),
            }
        except httpx.HTTPError:
            if attempt == max_retries:
                raise
            print(
                f"upload-batch:{file_paths[0].name}...{file_paths[-1].name}: "
                f"retry {attempt}/{max_retries} after request failure"
            )
            time.sleep(min(2 * attempt, 10))
        finally:
            for handle in handles:
                handle.close()

    raise RuntimeError("Batch upload exhausted retries.")


def poll_ready(
    base_url: str,
    token: str,
    namespace: str | None,
    expected_count: int,
    poll_interval: float,
    ready_timeout: int,
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{base_url}/api/documents/"
    started = time.time()
    target_namespace = namespace or "default"

    while True:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        docs = resp.json()
        namespace_docs = [doc for doc in docs if (doc.get("namespace") or "default") == target_namespace]
        ready_docs = [doc for doc in namespace_docs if doc.get("status") == "ready"]

        print(
            f"ready-check namespace={target_namespace} "
            f"ready={len(ready_docs)}/{expected_count} visible={len(namespace_docs)}"
        )
        if len(ready_docs) >= expected_count:
            return
        if time.time() - started > ready_timeout:
            raise TimeoutError(
                f"Timed out waiting for {expected_count} ready documents in namespace {target_namespace}."
            )
        time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Bulk ingest documents into ScaleRAG.")
    parser.add_argument("--dir", "--directory", dest="directory", required=True, help="Directory of documents to upload")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--token", required=True, help="JWT token")
    parser.add_argument("--workers", type=int, default=1, help="Parallel upload workers")
    parser.add_argument("--batch-size", type=int, default=25, help="Files per request batch")
    parser.add_argument("--limit", type=int, default=0, help="Max files to upload (0=all)")
    parser.add_argument("--namespace", default="", help="Optional upload namespace")
    parser.add_argument("--poll-ready", action="store_true", help="Wait for all uploaded docs to become ready")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between readiness polls")
    parser.add_argument("--ready-timeout", type=int, default=3600, help="Seconds to wait for ready state")
    parser.add_argument("--timeout", type=int, default=180, help="Per-request timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=5, help="Retries for transient upload failures")
    args = parser.parse_args()

    files = [
        p for p in Path(args.directory).iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_EXT
    ]
    if args.limit:
        files = files[:args.limit]

    if not files:
        print("No supported files found.")
        return

    batches = list(_batches(files, max(1, args.batch_size)))

    print(
        f"Found {len(files)} files across {len(batches)} request batches. "
        f"Uploading with {args.workers} workers …"
    )
    start = time.time()
    success, errors = 0, 0
    uploaded_doc_ids: list[int] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                upload_batch,
                batch,
                args.url,
                args.token,
                args.namespace or None,
                args.timeout,
                args.max_retries,
            ): batch
            for batch in batches
        }
        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                result = fut.result()
                success += len(batch)
                uploaded_doc_ids.extend(result["ids"])
                print(f"  ✓ {batch[0].name}...{batch[-1].name} → doc_ids={result['ids'][:3]}...")
            except Exception as exc:
                errors += len(batch)
                print(f"  ✗ {batch[0].name}...{batch[-1].name}: {exc}")

            elapsed = time.time() - start
            rate = success / elapsed if elapsed > 0 else 0
            print(
                f"\nProgress: {success + errors}/{len(files)} | Success: {success} | "
                f"Errors: {errors} | Rate: {rate:.1f} docs/s\n"
            )

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"Ingestion complete: {success} uploaded, {errors} failed")
    print(f"Total time: {elapsed:.1f}s | Throughput: {success/elapsed:.2f} docs/s")
    print(f"Estimated chunks in DB: ~{success * 15}")
    if uploaded_doc_ids:
        print(f"Uploaded doc ids: {uploaded_doc_ids[:10]}{'...' if len(uploaded_doc_ids) > 10 else ''}")

    if args.poll_ready and success:
        poll_ready(
            args.url,
            args.token,
            args.namespace or None,
            expected_count=success,
            poll_interval=args.poll_interval,
            ready_timeout=args.ready_timeout,
        )
        print("All uploaded documents reached ready state.")


if __name__ == "__main__":
    main()
