# ScaleRAG Evaluation Report

## What is included

- Retrieval benchmark script: [scripts/benchmark.py](./scripts/benchmark.py)
- Bulk ingestion script: [scripts/bulk_ingest.py](./scripts/bulk_ingest.py)
- Synthetic dataset generator: [scripts/generate_test_docs.py](./scripts/generate_test_docs.py)
- Question-level evaluation harness: [backend/eval/run_eval.py](./backend/eval/run_eval.py)
- Namespace-isolated public demo smoke harness: [scripts/rag_production_smoke_test.py](./scripts/rag_production_smoke_test.py)

## Evaluation methodology

1. Generate or collect a mixed corpus of PDF, HTML, and CSV files.
2. Bulk upload the corpus in bounded batches and wait until all documents reach `ready`.
3. Run retrieval-only evaluation with `backend/eval/run_eval.py`.
4. Run response-latency benchmarking with `scripts/benchmark.py`.
5. Re-run evaluation with `--with-llm` to score answer quality, citation hit rate, and no-answer behavior.
6. For the public demo deployment, prefer sampled correctness checks over an uncontrolled full public stress sweep.

## Metrics tracked

- Retrieval Precision proxy: `Recall@1`, `Recall@3`, `Recall@5`, `MRR`
- Response latency: total latency and TTFT, including `P50`, `P95`, and `P99`
- Hallucination rate proxy: no-answer accuracy plus grounding score emitted by the backend
- Cost per query: computed from the configured model mix and token usage during benchmark runs

## Current validation status

- Backend import/startup check: passed
- Backend unit tests: passed
- Frontend production build: passed
- End-to-end health smoke test: passed
- Public bounded live verification: stable health, repeated login, bounded namespace-isolated upload/query flow

## Commands

```bash
# Public demo bounded evaluation
python scripts/rag_production_smoke_test.py --base-url https://scalerag-backend.onrender.com --count 100 --query-sample 20

# Batched ingest with namespace isolation and readiness polling
python scripts/bulk_ingest.py --url https://scalerag-backend.onrender.com --token YOUR_JWT_TOKEN --directory ./synthetic_docs --batch-size 25 --workers 1 --namespace eval-100 --poll-ready

# Retrieval evaluation
cd backend
python eval/run_eval.py --dataset eval/datasets/eval_dataset.example.json --user-email you@example.com

# Retrieval + answer quality
python eval/run_eval.py --dataset eval/datasets/eval_dataset.example.json --user-email you@example.com --with-llm

# Latency benchmark
cd ..
python scripts/benchmark.py --url http://localhost:8000 --token YOUR_JWT_TOKEN --doc-ids 1,2,3 --queries 50
```

Both evaluation runners now emit approximate token volume and rough cost-per-query estimates so the submission covers the cost engineering requirement without requiring provider billing exports.

## Final submission note

This submission distinguishes between:

- the `architecture scale target` of the system, which is designed for large corpora and automated ingestion, and
- the `public demo deployment`, which is a constrained Render environment intended for bounded evaluator-facing verification.

For the public deployment, recommended evaluator settings are:
- upload batch size `25` to `50`
- ingest concurrency `1` to `2`
- query sample `20` to `60`

This keeps the live demo reliable while still exercising the real ingestion, retrieval, citation, and generation paths.
