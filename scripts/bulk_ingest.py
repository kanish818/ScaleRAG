"""
Bulk ingestion script — uploads documents to ScaleRAG in parallel batches.
Used for 10K+ scale testing.

Usage:
    # First register a user and get a token
    python scripts/bulk_ingest.py --dir ./test_docs --url http://localhost:8000 \
        --token YOUR_JWT_TOKEN --workers 4 --batch-size 10
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

ALLOWED_EXT = {".pdf", ".html", ".htm", ".csv"}


def upload_file(file_path: Path, base_url: str, token: str) -> dict:
    url = f"{base_url}/api/documents/upload"
    headers = {"Authorization": f"Bearer {token}"}
    with open(file_path, "rb") as f:
        content_type = (
            "application/pdf" if file_path.suffix == ".pdf"
            else "text/html" if file_path.suffix in (".html", ".htm")
            else "text/csv"
        )
        resp = httpx.post(
            url,
            headers=headers,
            files={"files": (file_path.name, f, content_type)},
            timeout=60,
        )
    resp.raise_for_status()
    return {"file": file_path.name, "status": "queued", "ids": [d["id"] for d in resp.json()]}


def main():
    parser = argparse.ArgumentParser(description="Bulk ingest documents into ScaleRAG.")
    parser.add_argument("--dir", required=True, help="Directory of documents to upload")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--token", required=True, help="JWT token")
    parser.add_argument("--workers", type=int, default=4, help="Parallel upload workers")
    parser.add_argument("--batch-size", type=int, default=10, help="Files per batch")
    parser.add_argument("--limit", type=int, default=0, help="Max files to upload (0=all)")
    args = parser.parse_args()

    files = [
        p for p in Path(args.dir).iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_EXT
    ]
    if args.limit:
        files = files[:args.limit]

    print(f"Found {len(files)} files. Uploading with {args.workers} workers …")
    start = time.time()
    success, errors = 0, 0

    # Process in batches
    for batch_start in range(0, len(files), args.batch_size):
        batch = files[batch_start: batch_start + args.batch_size]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(upload_file, f, args.url, args.token): f for f in batch}
            for fut in as_completed(futures):
                fname = futures[fut].name
                try:
                    result = fut.result()
                    success += 1
                    print(f"  ✓ {fname} → doc_ids={result['ids']}")
                except Exception as exc:
                    errors += 1
                    print(f"  ✗ {fname}: {exc}")

        elapsed = time.time() - start
        rate = success / elapsed if elapsed > 0 else 0
        print(f"\nProgress: {success + errors}/{len(files)} | Success: {success} | "
              f"Errors: {errors} | Rate: {rate:.1f} docs/s\n")

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"Ingestion complete: {success} uploaded, {errors} failed")
    print(f"Total time: {elapsed:.1f}s | Throughput: {success/elapsed:.2f} docs/s")
    print(f"Estimated chunks in DB: ~{success * 15}")


if __name__ == "__main__":
    main()
