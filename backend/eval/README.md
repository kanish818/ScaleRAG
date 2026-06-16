# ScaleRAG Evaluation Harness

This directory contains a lightweight evaluation workflow for retrieval quality,
citation behavior, and no-answer handling.

## Files

- `run_eval.py`: Runs the benchmark against one user's uploaded documents.
- `datasets/eval_dataset.example.json`: Example dataset format you can copy and edit.
- `reports/`: Generated JSON and Markdown reports.

## Dataset format

Each dataset item supports:

- `id`: Stable case ID.
- `question`: The user query to evaluate.
- `question_type`: Free-form label such as `fact`, `summary`, `action_items`, `no_answer`.
- `document_filenames`: Exact uploaded filenames to search within.
- `expected_sources`: Expected supporting citations as `{ "filename": "...", "page_num": 1 }`.
- `expected_answer_contains`: Phrases that should appear in the answer when LLM scoring is enabled.
- `should_answer`: `true` when the dataset contains the answer, `false` when the assistant should refuse.
- `notes`: Optional human context.

## Metrics

The runner generates:

- `Recall@1`, `Recall@3`, `Recall@5`
- `MRR`
- `citation_hit_rate` when `--with-llm` is enabled
- `answer_phrase_coverage` when `--with-llm` is enabled
- `no_answer_accuracy` for `question_type = "no_answer"` when `--with-llm` is enabled
- approximate input/output token counts when `--with-llm` is enabled
- approximate total and per-case query cost when `--with-llm` is enabled

## Usage

Run from the `backend/` directory so the app's `.env` file is picked up:

```bash
cd backend
python eval/run_eval.py --dataset eval/datasets/eval_dataset.example.json --user-email you@example.com
```

To include answer generation and answer/citation scoring:

```bash
cd backend
python eval/run_eval.py --dataset eval/my_eval_set.json --user-email you@example.com --with-llm
```

Reports are written to `eval/reports/` as:

- `eval_report_<timestamp>.json`
- `eval_report_<timestamp>.md`

## Public demo guidance

For the public deployment, keep evaluation bounded:

- upload in batches of `25` to `50`
- use ingest concurrency `1` to `2`
- run sampled query sets instead of uncontrolled large public sweeps
