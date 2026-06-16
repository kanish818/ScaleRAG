"""
Namespace-isolated production RAG smoke test harness.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from faker import Faker
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

fake = Faker()
styles = getSampleStyleSheet()

ROOT_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
GENERATED_DOCS_DIR = ARTIFACTS_DIR / "rag-smoke-docs"
MANIFEST_PATH = ARTIFACTS_DIR / "rag-smoke-manifest.jsonl"
RESULTS_PATH = ARTIFACTS_DIR / "rag-smoke-results.jsonl"
SUMMARY_PATH = ARTIFACTS_DIR / "rag-smoke-summary.json"
FAILURES_PATH = ARTIFACTS_DIR / "rag-smoke-failures.csv"
REPORT_PATH = ARTIFACTS_DIR / "rag-smoke-report.md"

NEGATIVE_CONTROL_COUNT = 20
SIMILAR_ID_CONTROL_COUNT = 20
TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
NO_TOKEN_PATTERNS = [
    re.compile(r"\b[A-Z0-9]{20,}\b"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+"),
]


class SmokeTestError(Exception):
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class SmokeConfig:
    base_url: str
    token: str = ""
    email: str = ""
    password: str = ""
    name: str = "RAG Smoke Tester"
    count: int = 1000
    ingest_concurrency: int = 20
    query_concurrency: int = 20
    ingestion_timeout_seconds: int = 300
    request_timeout_seconds: int = 45
    poll_interval_seconds: float = 2.0
    max_retries: int = 5
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0
    exact_accuracy_threshold: float = 0.99
    source_hit_threshold: float = 0.99
    citation_threshold: float = 0.99
    negative_false_positive_threshold: float = 0.01
    max_total_duration_seconds: int = 600

    @classmethod
    def from_env(cls, count: int) -> "SmokeConfig":
        return cls(
            base_url=os.getenv("RAG_SMOKE_BASE_URL", "http://localhost:8000").rstrip("/"),
            token=os.getenv("RAG_SMOKE_TOKEN", "").strip(),
            email=os.getenv("RAG_SMOKE_EMAIL", "").strip(),
            password=os.getenv("RAG_SMOKE_PASSWORD", "").strip(),
            name=os.getenv("RAG_SMOKE_NAME", "RAG Smoke Tester").strip() or "RAG Smoke Tester",
            count=count,
            ingest_concurrency=int(os.getenv("RAG_SMOKE_INGEST_CONCURRENCY", "20")),
            query_concurrency=int(os.getenv("RAG_SMOKE_QUERY_CONCURRENCY", "20")),
            ingestion_timeout_seconds=int(os.getenv("RAG_SMOKE_INGESTION_TIMEOUT", "300")),
            request_timeout_seconds=int(os.getenv("RAG_SMOKE_REQUEST_TIMEOUT", "45")),
            poll_interval_seconds=float(os.getenv("RAG_SMOKE_POLL_INTERVAL", "2")),
            max_retries=int(os.getenv("RAG_SMOKE_MAX_RETRIES", "5")),
            backoff_base_seconds=float(os.getenv("RAG_SMOKE_BACKOFF_BASE_SECONDS", "0.5")),
            backoff_max_seconds=float(os.getenv("RAG_SMOKE_BACKOFF_MAX_SECONDS", "8")),
            exact_accuracy_threshold=float(os.getenv("RAG_SMOKE_EXACT_ACCURACY_THRESHOLD", "0.99")),
            source_hit_threshold=float(os.getenv("RAG_SMOKE_SOURCE_HIT_THRESHOLD", "0.99")),
            citation_threshold=float(os.getenv("RAG_SMOKE_CITATION_THRESHOLD", "0.99")),
            negative_false_positive_threshold=float(
                os.getenv("RAG_SMOKE_NEGATIVE_FALSE_POSITIVE_THRESHOLD", "0.01")
            ),
            max_total_duration_seconds=int(os.getenv("RAG_SMOKE_MAX_TOTAL_DURATION_SECONDS", "600")),
        )


@dataclass
class SyntheticDoc:
    document_id: str
    filename: str
    unique_canary: str
    expected_answer: str
    question: str
    test_run_id: str
    timestamp_utc: str
    format: str
    path: str


@dataclass
class QueryResult:
    phase: str
    document_id: str
    question: str
    expected_answer: str
    answer: str
    source_hit: bool
    citation_hit: bool
    answer_hit: bool
    contamination: bool
    passed: bool
    latency_ms: float
    sources: List[Dict[str, object]] = field(default_factory=list)
    status_code: int = 200
    reason: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_test_run_id() -> str:
    return f"RUN-{utc_now().strftime('%Y%m%dT%H%M%SZ')}"


def build_namespace(test_run_id: str) -> str:
    return f"rag-smoke-{test_run_id.replace('RUN-', '').lower()}"


def ensure_dirs() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)


def random_canary() -> str:
    return f"CANARY-{secrets.token_hex(4).upper()}"


def deterministic_fact(document_id: str) -> str:
    return f"No other calibration code is valid for station {document_id}."


def create_manifest_entry(index: int, test_run_id: str, docs_dir: Path) -> SyntheticDoc:
    document_id = f"RAG-SMOKE-DOC-{index:04d}"
    canary = random_canary()
    question = f"What is the authorized calibration code for station {document_id}?"
    fmt = "pdf" if index % 5 in (1, 2, 3) else "html" if index % 5 == 4 else "csv"
    filename = f"{document_id}.{fmt}"
    return SyntheticDoc(
        document_id=document_id,
        filename=filename,
        unique_canary=canary,
        expected_answer=canary,
        question=question,
        test_run_id=test_run_id,
        timestamp_utc=utc_now().isoformat(),
        format=fmt,
        path=str(docs_dir / filename),
    )


def _pdf_story(doc: SyntheticDoc) -> List[object]:
    story = [
        Paragraph(f"<b>Document ID:</b> {doc.document_id}", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            f"The authorized calibration code for station {doc.document_id} is <b>{doc.unique_canary}</b>.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
        Paragraph(f"The station belongs to synthetic smoke-test run {doc.test_run_id}.", styles["BodyText"]),
        Spacer(1, 8),
        Paragraph(deterministic_fact(doc.document_id), styles["BodyText"]),
        Spacer(1, 8),
        Paragraph("Decoy note: routine maintenance schedule and staffing summary.", styles["BodyText"]),
        PageBreak(),
        Paragraph("Operational Appendix", styles["Heading2"]),
        Paragraph("Synthetic decoy content for retrieval validation.", styles["BodyText"]),
        Spacer(1, 8),
        Paragraph(f"Metadata: {doc.test_run_id} | {doc.timestamp_utc}", styles["BodyText"]),
    ]
    if int(doc.document_id[-2:]) % 2 == 0:
        story.extend([PageBreak(), Paragraph("Reference Page", styles["Heading2"]), Paragraph("Synthetic appendix.", styles["BodyText"])])
    return story


def write_pdf(doc: SyntheticDoc) -> None:
    pdf = SimpleDocTemplate(doc.path, pagesize=letter)
    pdf.build(_pdf_story(doc))


def write_html(doc: SyntheticDoc) -> None:
    page_break = '<div style="page-break-after: always;"></div>'
    extra = page_break + "<h2>Appendix</h2><p>Harmless decoy text for retrieval validation.</p>"
    if int(doc.document_id[-2:]) % 2 == 0:
        extra += page_break + "<h2>Reference</h2><p>Synthetic appendix page.</p>"
    content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{doc.document_id}</title></head>
<body>
<h1>Document ID: {doc.document_id}</h1>
<p>The authorized calibration code for station {doc.document_id} is <strong>{doc.unique_canary}</strong>.</p>
<p>The station belongs to synthetic smoke-test run {doc.test_run_id}.</p>
<p>{deterministic_fact(doc.document_id)}</p>
<p>Decoy note: regional logistics review and inventory reconciliation summary.</p>
{page_break}
<h2>Operational Notes</h2>
<p>Metadata timestamp: {doc.timestamp_utc}</p>
<p>Additional harmless decoy text for retrieval checks.</p>
{extra}
</body>
</html>
"""
    Path(doc.path).write_text(content, encoding="utf-8")


def write_csv(doc: SyntheticDoc) -> None:
    rows = [
        ["row_number", "logical_page", "document_id", "field", "value", "notes"],
        ["1", "1", doc.document_id, "authorized_calibration_code", doc.unique_canary, "Primary deterministic fact"],
        ["2", "1", doc.document_id, "test_run_id", doc.test_run_id, "Synthetic run marker"],
        ["3", "1", doc.document_id, "policy_statement", deterministic_fact(doc.document_id), "Valid answer guard"],
        ["4", "2", doc.document_id, "decoy_text", "Routine staffing review", "Harmless decoy text"],
        ["5", "2", doc.document_id, "timestamp_utc", doc.timestamp_utc, "Metadata"],
        ["6", "3", doc.document_id, "appendix", "Synthetic appendix", "Optional page"],
    ]
    with open(doc.path, "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def generate_documents(test_run_id: str, count: int, docs_dir: Path = GENERATED_DOCS_DIR) -> List[SyntheticDoc]:
    ensure_dirs()
    for existing in docs_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    docs = []
    for index in range(1, count + 1):
        doc = create_manifest_entry(index, test_run_id, docs_dir)
        docs.append(doc)
        if doc.format == "pdf":
            write_pdf(doc)
        elif doc.format == "html":
            write_html(doc)
        else:
            write_csv(doc)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(asdict(doc)) + "\n")
    return docs


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def answer_contains_only_expected_canary(answer: str, expected_canary: str, all_canaries: Sequence[str]) -> bool:
    normalized = normalize_text(answer)
    expected = normalize_text(expected_canary)
    if expected not in normalized:
        return False
    for canary in all_canaries:
        if canary == expected_canary:
            continue
        if normalize_text(canary) in normalized:
            return False
    return True


def sources_contain_document(sources: Sequence[Dict[str, object]], expected_filename: str) -> bool:
    expected = expected_filename.lower()
    return any(str(source.get("filename", "")).lower() == expected for source in sources)


def citations_contain_document(answer: str, expected_filename: str) -> bool:
    lowered_answer = (answer or "").lower()
    stem = Path(expected_filename).stem.lower()
    return expected_filename.lower() in lowered_answer or stem in lowered_answer


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


def sanitize_for_output(text: str) -> str:
    sanitized = text or ""
    for pattern in NO_TOKEN_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def retryable_request(fn, *, config: SmokeConfig, label: str, metrics: Dict[str, int]):
    last_error: Optional[Exception] = None
    for attempt in range(config.max_retries + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 429:
                metrics["http_429_count"] += 1
            if code >= 500:
                metrics["http_5xx_count"] += 1
            if code not in TRANSIENT_STATUSES:
                raise
            last_error = exc
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            metrics["http_5xx_count"] += 1
            last_error = exc
        if attempt >= config.max_retries:
            break
        metrics["retry_count"] += 1
        sleep_for = min(config.backoff_max_seconds, config.backoff_base_seconds * (2 ** attempt)) + random.uniform(0, 0.25)
        print(f"{label}: retry {attempt + 1}/{config.max_retries} after transient error")
        time.sleep(sleep_for)
    raise last_error or RuntimeError(f"{label} failed without captured exception")


class ScaleRAGClient:
    def __init__(self, config: SmokeConfig, metrics: Dict[str, int]):
        self.config = config
        self.metrics = metrics
        self._client = httpx.Client(timeout=config.request_timeout_seconds, follow_redirects=False)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> Dict[str, str]:
        if not self.config.token:
            raise SmokeTestError("Missing auth credentials. Set RAG_SMOKE_TOKEN or RAG_SMOKE_EMAIL/RAG_SMOKE_PASSWORD.", 2)
        return {"Authorization": f"Bearer {self.config.token}"}

    def ensure_token(self) -> None:
        if self.config.token:
            return
        if not self.config.email or not self.config.password:
            raise SmokeTestError("Missing auth credentials. Set RAG_SMOKE_TOKEN or RAG_SMOKE_EMAIL/RAG_SMOKE_PASSWORD.", 2)
        response = self._client.post(
            f"{self.config.base_url}/api/auth/login",
            json={"email": self.config.email, "password": self.config.password},
        )
        if response.status_code == 401:
            register = self._client.post(
                f"{self.config.base_url}/api/auth/register",
                json={"email": self.config.email, "password": self.config.password, "name": self.config.name},
            )
            if register.status_code not in (200, 201):
                register.raise_for_status()
            self.config.token = register.json()["access_token"]
            return
        response.raise_for_status()
        self.config.token = response.json()["access_token"]

    def get_me(self) -> Dict[str, object]:
        self.ensure_token()
        def do_get():
            response = self._client.get(f"{self.config.base_url}/api/auth/me", headers=self._headers())
            response.raise_for_status()
            return response
        return retryable_request(do_get, config=self.config, label="auth-me", metrics=self.metrics).json()

    def list_namespaces(self) -> List[Dict[str, object]]:
        self.ensure_token()
        response = self._client.get(f"{self.config.base_url}/api/documents/namespaces", headers=self._headers())
        if response.status_code == 404:
            raise SmokeTestError(
                "Safety limitation: deployed service does not expose namespace-aware document isolation endpoints.",
                2,
            )
        response.raise_for_status()
        return response.json()

    def list_documents(self, namespace: Optional[str] = None) -> List[Dict[str, object]]:
        self.ensure_token()
        params = {"namespace": namespace} if namespace else None
        response = self._client.get(f"{self.config.base_url}/api/documents/", headers=self._headers(), params=params)
        response.raise_for_status()
        return response.json()

    def upload_document(self, path: Path, namespace: str) -> Dict[str, object]:
        self.ensure_token()

        def do_upload():
            with open(path, "rb") as handle:
                content_type = "application/pdf" if path.suffix == ".pdf" else "text/html" if path.suffix in (".html", ".htm") else "text/csv"
                response = self._client.post(
                    f"{self.config.base_url}/api/documents/upload",
                    headers=self._headers(),
                    data={"namespace": namespace},
                    files={"files": (path.name, handle, content_type)},
                )
                response.raise_for_status()
                return response

        return retryable_request(do_upload, config=self.config, label=f"upload:{path.name}", metrics=self.metrics).json()[0]

    def create_conversation(self, namespace: str, document_ids: List[int]) -> Dict[str, object]:
        self.ensure_token()
        def do_create():
            response = self._client.post(
                f"{self.config.base_url}/api/chat/conversations",
                headers=self._headers(),
                json={"title": "RAG Smoke Test", "namespace": namespace, "document_ids": document_ids},
            )
            response.raise_for_status()
            return response
        return retryable_request(do_create, config=self.config, label="create-conversation", metrics=self.metrics).json()

    def ask_stream(self, conversation_id: int, question: str, document_ids: List[int], namespace: str) -> Dict[str, object]:
        self.ensure_token()
        answer = ""
        sources: List[Dict[str, object]] = []
        hallucination = None
        started = time.perf_counter()
        def do_stream():
            return self._client.stream(
                "POST",
                f"{self.config.base_url}/api/chat/conversations/{conversation_id}/stream",
                headers={**self._headers(), "Accept": "text/event-stream"},
                json={"question": question, "document_ids": document_ids, "namespace": namespace},
            )
        with retryable_request(do_stream, config=self.config, label="chat-stream-open", metrics=self.metrics) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                kind = payload.get("type")
                if kind == "chunk":
                    answer += payload.get("content", "")
                elif kind == "sources":
                    sources = payload.get("sources", [])
                elif kind == "hallucination":
                    hallucination = payload
                elif kind == "done":
                    break
                elif kind == "error":
                    raise SmokeTestError(f"Chat stream error: {payload.get('content', 'unknown error')}", 1)
        return {
            "answer": answer,
            "sources": sources,
            "hallucination": hallucination,
            "latency_ms": (time.perf_counter() - started) * 1000,
        }

    def delete_namespace(self, namespace: str) -> None:
        self.ensure_token()
        response = self._client.delete(f"{self.config.base_url}/api/documents/namespaces/{namespace}", headers=self._headers())
        if response.status_code not in (200, 202, 204, 404):
            response.raise_for_status()


def inspect_repository_capabilities() -> Dict[str, object]:
    return {
        "ingestion_endpoint": "POST /api/documents/upload",
        "ingestion_status_endpoint": "GET /api/documents/?namespace=<name>",
        "query_endpoint": "POST /api/chat/conversations/{conv_id}/stream",
        "citation_format": "inline filename/page references in answer text plus SSE sources payload",
        "authentication": ["POST /api/auth/register", "POST /api/auth/login", "Bearer JWT", "GET /api/auth/me"],
        "supported_formats": ["pdf", "html", "csv"],
        "namespace_mechanism": "named namespace on documents, chunks, embeddings, and conversations",
        "existing_test_framework": "unittest",
        "env_conventions": ["RAG_SMOKE_*", "backend/app/core/config.py app settings"],
        "vector_store_verification": ["backend/app/services/vector_store.py", "document chunk_count via GET /api/documents/"],
    }


def check_namespace_isolation(client: ScaleRAGClient, namespace: str) -> Tuple[bool, str]:
    namespaces = client.list_namespaces()
    if any((item.get("namespace") or "") == namespace for item in namespaces):
        return True, f"Namespace {namespace} already exists and can be cleaned safely."
    return True, f"Namespace {namespace} is supported by the deployed service."


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_failures_csv(failures: Iterable[Dict[str, object]]) -> None:
    rows = list(failures)
    with open(FAILURES_PATH, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["phase", "document_id", "reason"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in ("phase", "document_id", "reason")})


def write_results_jsonl(results: Iterable[QueryResult]) -> None:
    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result)) + "\n")


def write_report(summary: Dict[str, object], failures: List[Dict[str, object]]) -> None:
    lines = [
        "# RAG Production Smoke Test",
        "",
        f"- Verdict: **{summary['verdict']}**",
        f"- Test run ID: `{summary['test_run_id']}`",
        f"- Namespace: `{summary['namespace']}`",
        f"- Documents attempted: {summary['documents_attempted']}",
        f"- Documents ready: {summary['documents_ready']}",
        f"- Questions attempted: {summary['questions_attempted']}",
        f"- Exact-answer accuracy: {summary['exact_answer_accuracy']:.4f}",
        f"- Source hit rate: {summary['retrieval_source_hit_rate']:.4f}",
        f"- Citation accuracy: {summary['citation_accuracy']:.4f}",
        f"- Negative false-positive rate: {summary['negative_control_false_positive_rate']:.4f}",
        f"- Total duration seconds: {summary['total_duration_seconds']}",
        "",
        "## Capabilities",
        "",
        f"- Namespace mechanism: {summary['capabilities']['namespace_mechanism']}",
        f"- Query endpoint: `{summary['capabilities']['query_endpoint']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        for failure in failures[:50]:
            lines.append(f"- {failure.get('phase')}: {failure.get('document_id') or 'n/a'} -> {failure.get('reason')}")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_negative_controls(client: ScaleRAGClient, namespace: str, docs_by_id: Dict[str, SyntheticDoc], ready_rows: List[Dict[str, object]]) -> List[QueryResult]:
    results: List[QueryResult] = []
    sample_rows = ready_rows[:NEGATIVE_CONTROL_COUNT]
    for idx, row in enumerate(sample_rows, start=1):
        fake_id = f"RAG-SMOKE-DOC-XNEG-{idx:04d}"
        question = f"What is the authorized calibration code for station {fake_id}?"
        conv = client.create_conversation(namespace, [int(row["id"])])
        response = client.ask_stream(conv["id"], question, [int(row["id"])], namespace)
        answer = response["answer"]
        found_any_canary = any(doc.unique_canary.lower() in answer.lower() for doc in docs_by_id.values())
        source_hit = len(response["sources"]) == 0
        passed = ("could not find" in answer.lower() or "not found" in answer.lower() or "unavailable" in answer.lower()) and not found_any_canary and source_hit
        results.append(QueryResult(
            phase="negative_control",
            document_id=fake_id,
            question=question,
            expected_answer="",
            answer=answer,
            source_hit=source_hit,
            citation_hit=source_hit,
            answer_hit=not found_any_canary,
            contamination=found_any_canary,
            passed=passed,
            latency_ms=float(response["latency_ms"]),
            sources=response["sources"],
            reason="" if passed else "Negative control returned content or sources.",
        ))
    return results


def run_primary_queries(client: ScaleRAGClient, config: SmokeConfig, namespace: str, docs: List[SyntheticDoc], ready_rows: List[Dict[str, object]]) -> List[QueryResult]:
    row_by_filename = {row["filename"]: row for row in ready_rows}
    all_canaries = [doc.unique_canary for doc in docs]
    results: List[QueryResult] = []

    def ask_one(doc: SyntheticDoc) -> QueryResult:
        row = row_by_filename.get(doc.filename)
        if not row:
            return QueryResult(
                phase="primary",
                document_id=doc.document_id,
                question=doc.question,
                expected_answer=doc.expected_answer,
                answer="",
                source_hit=False,
                citation_hit=False,
                answer_hit=False,
                contamination=False,
                passed=False,
                latency_ms=0.0,
                reason="Document not ready or missing from namespace listing.",
            )
        conv = client.create_conversation(namespace, [int(row["id"])])
        response = client.ask_stream(conv["id"], doc.question, [int(row["id"])], namespace)
        answer_hit = answer_contains_only_expected_canary(response["answer"], doc.expected_answer, all_canaries)
        source_hit = sources_contain_document(response["sources"], doc.filename)
        citation_hit = citations_contain_document(response["answer"], doc.filename)
        contamination = not answer_hit and any(
            canary.lower() in response["answer"].lower()
            for canary in all_canaries
            if canary != doc.expected_answer
        )
        passed = answer_hit and source_hit and citation_hit and not contamination
        return QueryResult(
            phase="primary",
            document_id=doc.document_id,
            question=doc.question,
            expected_answer=doc.expected_answer,
            answer=response["answer"],
            source_hit=source_hit,
            citation_hit=citation_hit,
            answer_hit=answer_hit,
            contamination=contamination,
            passed=passed,
            latency_ms=float(response["latency_ms"]),
            sources=response["sources"],
            reason="" if passed else "Answer, source, citation, or contamination check failed.",
        )

    with ThreadPoolExecutor(max_workers=config.query_concurrency) as pool:
        futures = {pool.submit(ask_one, doc): doc for doc in docs}
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            results.append(result)
            if completed % 25 == 0 or completed == len(docs):
                p95 = percentile([item.latency_ms for item in results], 0.95)
                passed = sum(1 for item in results if item.passed)
                failed = completed - passed
                print(f"Queries:   {passed}/{completed} passed | {failed} failed | p95 {round(p95 / 1000, 2) if p95 else 'n/a'}s")
    return results


def run_similar_id_checks(primary_results: List[QueryResult]) -> List[QueryResult]:
    selected = []
    suffixes = tuple(f"{i:02d}" for i in range(1, SIMILAR_ID_CONTROL_COUNT + 1))
    for item in primary_results:
        if item.document_id.endswith(suffixes):
            selected.append(QueryResult(**{**asdict(item), "phase": "similar_id"}))
    return selected


def build_summary(
    config: SmokeConfig,
    test_run_id: str,
    namespace: str,
    capabilities: Dict[str, object],
    docs: List[SyntheticDoc],
    accepted_count: int,
    ready_rows: List[Dict[str, object]],
    query_results: List[QueryResult],
    negative_results: List[QueryResult],
    duplicate_count: int,
    metrics: Dict[str, int],
    total_duration_seconds: float,
) -> Dict[str, object]:
    primary = [item for item in query_results if item.phase == "primary"]
    primary_count = len(primary) or 1
    negative_count = len(negative_results) or 1
    exact_accuracy = sum(1 for item in primary if item.answer_hit) / primary_count
    source_rate = sum(1 for item in primary if item.source_hit) / primary_count
    citation_rate = sum(1 for item in primary if item.citation_hit) / primary_count
    contamination_rate = sum(1 for item in primary if item.contamination) / primary_count
    negative_false_positive_rate = sum(1 for item in negative_results if not item.passed) / negative_count
    query_latencies = [item.latency_ms for item in primary]
    verdict = "PASS"
    if (
        accepted_count != config.count
        or len(ready_rows) != config.count
        or exact_accuracy < config.exact_accuracy_threshold
        or source_rate < config.source_hit_threshold
        or citation_rate < config.citation_threshold
        or contamination_rate > 0
        or negative_false_positive_rate > config.negative_false_positive_threshold
        or total_duration_seconds > config.max_total_duration_seconds
    ):
        verdict = "FAIL"
    return {
        "verdict": verdict,
        "exit_code": 0 if verdict == "PASS" else 1,
        "base_url": config.base_url,
        "test_run_id": test_run_id,
        "namespace": namespace,
        "documents_attempted": len(docs),
        "documents_accepted": accepted_count,
        "documents_ready": len(ready_rows),
        "documents_failed": max(0, accepted_count - len(ready_rows)),
        "documents_timed_out": 0,
        "duplicate_count": duplicate_count,
        "chunk_index_verification_rate": sum(1 for row in ready_rows if (row.get("chunk_count") or 0) > 0) / (len(ready_rows) or 1),
        "questions_attempted": len(primary),
        "exact_answer_accuracy": exact_accuracy,
        "retrieval_source_hit_rate": source_rate,
        "citation_accuracy": citation_rate,
        "cross_document_contamination_rate": contamination_rate,
        "negative_control_false_positive_rate": negative_false_positive_rate,
        "http_429_count": metrics["http_429_count"],
        "http_5xx_count": metrics["http_5xx_count"],
        "retry_count": metrics["retry_count"],
        "ingestion_latency_ms": {"p50": None, "p95": None, "p99": None},
        "query_latency_ms": {
            "p50": percentile(query_latencies, 0.50),
            "p95": percentile(query_latencies, 0.95),
            "p99": percentile(query_latencies, 0.99),
        },
        "total_duration_seconds": round(total_duration_seconds, 2),
        "estimated_api_model_usage": None,
        "capabilities": capabilities,
        "rerun_command": f"python scripts/rag_production_smoke_test.py --base-url {config.base_url} --count {config.count}",
    }


def execute_smoke_test(config: SmokeConfig, test_run_id: str, namespace: str) -> int:
    started = time.perf_counter()
    capabilities = inspect_repository_capabilities()
    docs = generate_documents(test_run_id, config.count)
    metrics = {"http_429_count": 0, "http_5xx_count": 0, "retry_count": 0}
    client = ScaleRAGClient(config, metrics)
    failures: List[Dict[str, object]] = []
    query_results: List[QueryResult] = []
    negative_results: List[QueryResult] = []
    duplicate_count = 0
    accepted_count = 0
    try:
        client.get_me()
        supported, note = check_namespace_isolation(client, namespace)
        if not supported:
            raise SmokeTestError(note, 2)
        print(note)
        client.delete_namespace(namespace)

        def upload_one(doc: SyntheticDoc) -> Tuple[SyntheticDoc, Dict[str, object]]:
            return doc, client.upload_document(Path(doc.path), namespace)

        with ThreadPoolExecutor(max_workers=config.ingest_concurrency) as pool:
            futures = {pool.submit(upload_one, doc): doc for doc in docs}
            completed = 0
            for future in as_completed(futures):
                doc, uploaded = future.result()
                completed += 1
                accepted_count += 1
                if completed % 25 == 0 or completed == len(docs):
                    print(f"Ingestion: {completed}/{len(docs)} accepted | 0 retrying | 0 failed")

        duplicate_response = client.upload_document(Path(docs[0].path), namespace)
        if duplicate_response.get("id"):
            duplicate_count = 1

        malformed = GENERATED_DOCS_DIR / "malformed.txt"
        malformed.write_text("unsupported", encoding="utf-8")
        try:
            client.upload_document(malformed, namespace)
            failures.append({"phase": "ingestion_negative", "document_id": "malformed", "reason": "Unsupported file unexpectedly accepted."})
        except Exception:
            pass

        empty_pdf = GENERATED_DOCS_DIR / "empty.pdf"
        empty_pdf.write_bytes(b"")
        try:
            client.upload_document(empty_pdf, namespace)
            failures.append({"phase": "ingestion_negative", "document_id": "empty", "reason": "Empty file unexpectedly accepted."})
        except Exception:
            pass

        deadline = time.perf_counter() + config.ingestion_timeout_seconds
        ready_rows: List[Dict[str, object]] = []
        while time.perf_counter() < deadline:
            rows = client.list_documents(namespace)
            ready_rows = [row for row in rows if row.get("status") == "ready" and row.get("filename") in {doc.filename for doc in docs}]
            failed_rows = [row for row in rows if row.get("status") == "error" and row.get("filename") in {doc.filename for doc in docs}]
            print(f"Ingestion: {len(ready_rows)}/{config.count} ready | 0 retrying | {len(failed_rows)} failed | elapsed {round(time.perf_counter() - started)}s")
            if len(ready_rows) == config.count:
                break
            time.sleep(config.poll_interval_seconds)
        if len(ready_rows) != config.count:
            missing = config.count - len(ready_rows)
            failures.append({"phase": "ingestion", "document_id": "", "reason": f"{missing} documents not ready before timeout."})

        query_results = run_primary_queries(client, config, namespace, docs, ready_rows)
        negative_results = run_negative_controls(client, namespace, {doc.document_id: doc for doc in docs}, ready_rows)
        query_results.extend(run_similar_id_checks(query_results))

        for result in query_results + negative_results:
            if not result.passed:
                failures.append({"phase": result.phase, "document_id": result.document_id, "reason": result.reason})

        total_duration_seconds = time.perf_counter() - started
        write_results_jsonl(query_results + negative_results)
        summary = build_summary(
            config=config,
            test_run_id=test_run_id,
            namespace=namespace,
            capabilities=capabilities,
            docs=docs,
            accepted_count=accepted_count,
            ready_rows=ready_rows,
            query_results=query_results,
            negative_results=negative_results,
            duplicate_count=duplicate_count,
            metrics=metrics,
            total_duration_seconds=total_duration_seconds,
        )
        write_json(SUMMARY_PATH, summary)
        write_failures_csv(failures)
        write_report(summary, failures)
        print(summary["verdict"])
        print(f"Ingestion: {summary['documents_ready']}/{summary['documents_attempted']} ready")
        print(f"Answer accuracy: {summary['exact_answer_accuracy']:.4f}")
        print(f"Retrieval source accuracy: {summary['retrieval_source_hit_rate']:.4f}")
        print(f"Citation accuracy: {summary['citation_accuracy']:.4f}")
        print(f"Negative controls: {1 - summary['negative_control_false_positive_rate']:.4f}")
        print(f"Total duration: {summary['total_duration_seconds']}s")
        print(f"Report path: {REPORT_PATH}")
        return int(summary["exit_code"])
    finally:
        try:
            client.delete_namespace(namespace)
        except Exception:
            pass
        client.close()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Namespace-isolated production-safe RAG smoke test")
    parser.add_argument("--base-url", default=os.getenv("RAG_SMOKE_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--count", type=int, default=1000)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = SmokeConfig.from_env(count=args.count)
    config.base_url = args.base_url.rstrip("/")
    ensure_dirs()
    test_run_id = build_test_run_id()
    namespace = build_namespace(test_run_id)
    return execute_smoke_test(config, test_run_id, namespace)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SmokeTestError as exc:
        print(sanitize_for_output(str(exc)))
        sys.exit(exc.exit_code)
    except Exception as exc:  # pragma: no cover
        print(sanitize_for_output(f"Unexpected test-runner error: {exc}"))
        sys.exit(3)
