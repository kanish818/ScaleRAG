# RAG Production Smoke Test

This repository now includes a production-safe smoke-test harness at `scripts/rag_production_smoke_test.py`.

What it uses:
- Real auth flow: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- Real ingestion path: `POST /api/documents/upload`
- Real ingestion status path: `GET /api/documents/`
- Real query path: `POST /api/chat/conversations/{conv_id}/stream`

Safety behavior:
- The harness requires a true isolated collection, tenant, namespace, or knowledge base named `rag-smoke-<UTC_TIMESTAMP>`.
- The current codebase does not implement that. Documents are isolated only by `user_id` and selected `document_ids`.
- Because of that, the runner generates the 1,000-document local dataset and manifest, writes the report artifacts, and exits with code `2` without uploading anything.

Artifacts:
- `artifacts/rag-smoke-docs/`
- `artifacts/rag-smoke-manifest.jsonl`
- `artifacts/rag-smoke-results.jsonl`
- `artifacts/rag-smoke-summary.json`
- `artifacts/rag-smoke-failures.csv`
- `artifacts/rag-smoke-report.md`

Run:

```bash
python scripts/rag_production_smoke_test.py --base-url https://scalerag-backend.onrender.com --count 1000
```

Optional auth env vars:

```bash
RAG_SMOKE_TOKEN=...
RAG_SMOKE_EMAIL=...
RAG_SMOKE_PASSWORD=...
```

Exit codes:
- `0`: all thresholds passed
- `1`: quality or performance threshold failed
- `2`: configuration, authentication, or safety failure
- `3`: unexpected runner error

Important design choices:
- Thin adapter around the existing API routes instead of inventing new test endpoints.
- Hard safety gate before any production upload.
- Exact canary-token matching for answer validation, with cross-document contamination checks.
- Local artifact generation is preserved even when execution is blocked.
