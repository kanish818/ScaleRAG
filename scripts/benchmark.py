"""
Retrieval & latency benchmark for the evaluation report.
Tests P50/P95 query latency and basic retrieval quality.

Usage:
    python scripts/benchmark.py --url http://localhost:8000 \
        --token YOUR_JWT_TOKEN --doc-ids 1,2,3 --queries 50
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import List

import httpx

TEST_QUESTIONS = [
    "What are the main topics covered in this document?",
    "Summarize the key points.",
    "What methodology was used?",
    "Who are the key people mentioned?",
    "What are the conclusions?",
    "What data or metrics are presented?",
    "What recommendations are made?",
    "Describe the technical architecture.",
    "What are the main challenges discussed?",
    "What is the purpose of this document?",
]


def create_conversation(base_url: str, token: str, doc_ids: List[int]) -> int:
    r = httpx.post(
        f"{base_url}/api/chat/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Benchmark", "document_ids": doc_ids},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def ask_question(base_url: str, token: str, conv_id: int, question: str, doc_ids: List[int]) -> dict:
    start = time.perf_counter()
    first_token_time = None
    full_response = ""

    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{base_url}/api/chat/conversations/{conv_id}/stream",
            headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
            json={"question": question, "document_ids": doc_ids},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])
                if data.get("type") == "chunk":
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    full_response += data.get("content", "")
                elif data.get("type") == "done":
                    break

    end = time.perf_counter()
    return {
        "ttft_ms": round((first_token_time - start) * 1000) if first_token_time else None,
        "total_ms": round((end - start) * 1000),
        "response_len": len(full_response),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--doc-ids", required=True, help="Comma-separated doc IDs")
    parser.add_argument("--queries", type=int, default=20)
    args = parser.parse_args()

    doc_ids = [int(x) for x in args.doc_ids.split(",")]
    print(f"Benchmarking ScaleRAG at {args.url}")
    print(f"Documents: {doc_ids} | Queries: {args.queries}")

    conv_id = create_conversation(args.url, args.token, doc_ids)
    print(f"Created conversation id={conv_id}\n")

    latencies, ttfts = [], []
    questions = (TEST_QUESTIONS * ((args.queries // len(TEST_QUESTIONS)) + 1))[:args.queries]

    for i, q in enumerate(questions):
        try:
            result = ask_question(args.url, args.token, conv_id, q, doc_ids)
            latencies.append(result["total_ms"])
            if result["ttft_ms"]:
                ttfts.append(result["ttft_ms"])
            print(f"  [{i+1}/{args.queries}] {q[:50]!r} → {result['total_ms']}ms (TTFT: {result['ttft_ms']}ms)")
        except Exception as exc:
            print(f"  [{i+1}/{args.queries}] ERROR: {exc}")

    if latencies:
        latencies.sort()
        ttfts.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"\n{'='*50}")
        print(f"BENCHMARK RESULTS ({len(latencies)} successful queries)")
        print(f"  P50 Latency:  {p50}ms")
        print(f"  P95 Latency:  {p95}ms")
        print(f"  P99 Latency:  {latencies[int(len(latencies)*0.99)]}ms")
        print(f"  Mean:         {round(statistics.mean(latencies))}ms")
        print(f"  TTFT P50:     {ttfts[len(ttfts)//2] if ttfts else 'N/A'}ms")
        print(f"  TTFT P95:     {ttfts[int(len(ttfts)*0.95)] if ttfts else 'N/A'}ms")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
