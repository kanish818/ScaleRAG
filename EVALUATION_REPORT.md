# ScaleRAG Evaluation Report

## What is included

- Retrieval benchmark script: [scripts/benchmark.py](/C:/Projects2/Grade%20Chatbot/ScaleRAG/scripts/benchmark.py)
- Bulk ingestion script: [scripts/bulk_ingest.py](/C:/Projects2/Grade%20Chatbot/ScaleRAG/scripts/bulk_ingest.py)
- Synthetic dataset generator: [scripts/generate_test_docs.py](/C:/Projects2/Grade%20Chatbot/ScaleRAG/scripts/generate_test_docs.py)
- Question-level evaluation harness: [backend/eval/run_eval.py](/C:/Projects2/Grade%20Chatbot/ScaleRAG/backend/eval/run_eval.py)

## Evaluation methodology

1. Generate or collect a mixed corpus of PDF, HTML, and CSV files.
2. Bulk upload the corpus and wait until all documents reach `ready`.
3. Run retrieval-only evaluation with `backend/eval/run_eval.py`.
4. Run response-latency benchmarking with `scripts/benchmark.py`.
5. Re-run evaluation with `--with-llm` to score answer quality, citation hit rate, and no-answer behavior.

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

## Commands

```bash
# Retrieval evaluation
cd backend
python eval/run_eval.py --dataset eval/datasets/eval_dataset.example.json --user-email you@example.com

# Retrieval + answer quality
python eval/run_eval.py --dataset eval/datasets/eval_dataset.example.json --user-email you@example.com --with-llm

# Latency benchmark
cd ..
python scripts/benchmark.py --url http://localhost:8000 --token YOUR_JWT_TOKEN --doc-ids 1,2,3 --queries 50
```

## Final submission note

Replace this report with the measured JSON/Markdown outputs from your final deployed environment before submission if you have time to run the full benchmark suite.
