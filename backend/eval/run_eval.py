"""
Evaluation runner for ScaleRAG retrieval and answer quality.

Usage examples:
  python eval/run_eval.py --dataset eval/datasets/eval_dataset.example.json --user-email you@example.com
  python eval/run_eval.py --dataset eval/my_eval_set.json --user-email you@example.com --with-llm
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal, create_tables  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.embedder import embed_query  # noqa: E402
from app.services.llm import stream_chat  # noqa: E402
from app.services.retriever import hybrid_search  # noqa: E402

NO_ANSWER_PATTERNS = (
    "i could not find",
    "not enough information",
    "not found in the provided documents",
    "could not find this information in the provided documents",
)
APPROX_TOKEN_CHARS = 4
MODEL_COSTS_PER_1K_TOKENS = {
    "input_usd": 0.0005,
    "output_usd": 0.0015,
}


@dataclass
class EvalCase:
    case_id: str
    question: str
    document_filenames: List[str]
    expected_sources: List[Dict[str, Any]]
    expected_answer_contains: List[str]
    should_answer: bool
    question_type: str
    notes: str


@dataclass
class CaseResult:
    case_id: str
    question: str
    question_type: str
    should_answer: bool
    document_filenames: List[str]
    resolved_doc_ids: List[int]
    retrieved_sources: List[Dict[str, Any]]
    answer: Optional[str]
    retrieval_hit_rank: Optional[int]
    recall_at_1: bool
    recall_at_3: bool
    recall_at_5: bool
    reciprocal_rank: float
    citation_hit: bool
    no_answer_correct: Optional[bool]
    phrase_match_fraction: Optional[float]
    missing_documents: List[str]
    error: Optional[str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run retrieval/answer evaluation for ScaleRAG.")
    parser.add_argument("--dataset", required=True, help="Path to the evaluation dataset JSON file.")
    parser.add_argument("--user-email", help="User email whose uploaded documents should be evaluated.")
    parser.add_argument("--user-id", type=int, help="User ID whose uploaded documents should be evaluated.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of retrieved chunks to score.")
    parser.add_argument(
        "--namespace",
        default="default",
        help="Document namespace to evaluate. Defaults to the standard app namespace.",
    )
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Also run generation and score answer/citation behavior.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(BACKEND_DIR / "eval" / "reports"),
        help="Directory for JSON/Markdown reports.",
    )
    return parser.parse_args()


def _load_dataset(path: Path) -> List[EvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases: List[EvalCase] = []
    for index, item in enumerate(raw, start=1):
        cases.append(
            EvalCase(
                case_id=item.get("id") or f"case_{index}",
                question=item["question"],
                document_filenames=item.get("document_filenames", []),
                expected_sources=item.get("expected_sources", []),
                expected_answer_contains=item.get("expected_answer_contains", []),
                should_answer=bool(item.get("should_answer", True)),
                question_type=item.get("question_type", "fact"),
                notes=item.get("notes", ""),
            )
        )
    return cases


def _resolve_user(session, user_email: Optional[str], user_id: Optional[int]) -> User:
    if user_email:
        user = session.query(User).filter(User.email == user_email).first()
    elif user_id is not None:
        user = session.query(User).filter(User.id == user_id).first()
    else:
        raise ValueError("Provide either --user-email or --user-id.")

    if not user:
        raise ValueError("Could not find the requested user.")
    return user


def _normalise_filename(name: str) -> str:
    return name.strip().lower()


def _resolve_doc_ids(session, user_id: int, namespace: str, filenames: List[str]) -> Tuple[List[int], List[str]]:
    docs = (
        session.query(Document)
        .filter(Document.user_id == user_id, Document.namespace == namespace, Document.status == "ready")
        .all()
    )
    filename_map = {_normalise_filename(doc.filename): doc.id for doc in docs}

    resolved_ids: List[int] = []
    missing: List[str] = []
    for filename in filenames:
        doc_id = filename_map.get(_normalise_filename(filename))
        if doc_id is None:
            missing.append(filename)
        else:
            resolved_ids.append(doc_id)
    return list(dict.fromkeys(resolved_ids)), missing


def _source_matches_expected(source: Dict[str, Any], expected_sources: List[Dict[str, Any]]) -> bool:
    source_filename = _normalise_filename(source.get("filename", ""))
    source_page = source.get("page_num")
    for expected in expected_sources:
        expected_filename = _normalise_filename(expected.get("filename", ""))
        expected_page = expected.get("page_num")
        if source_filename == expected_filename and source_page == expected_page:
            return True
    return False


def _first_hit_rank(retrieved_sources: List[Dict[str, Any]], expected_sources: List[Dict[str, Any]]) -> Optional[int]:
    for index, source in enumerate(retrieved_sources, start=1):
        if _source_matches_expected(source, expected_sources):
            return index
    return None


def _extract_citations(answer: str) -> List[Tuple[str, int]]:
    citations: List[Tuple[str, int]] = []
    for match in re.finditer(r"\[([^,\]]+),\s*Page\s+(\d+)\]", answer):
        citations.append((_normalise_filename(match.group(1)), int(match.group(2))))
    return citations


def _citation_hit(answer: Optional[str], expected_sources: List[Dict[str, Any]]) -> bool:
    if not answer or not expected_sources:
        return False
    expected_pairs = {
        (_normalise_filename(source.get("filename", "")), int(source.get("page_num", 0)))
        for source in expected_sources
    }
    return any(pair in expected_pairs for pair in _extract_citations(answer))


def _phrase_match_fraction(answer: Optional[str], phrases: List[str]) -> Optional[float]:
    if answer is None or not phrases:
        return None
    lowered = answer.lower()
    matched = sum(1 for phrase in phrases if phrase.lower() in lowered)
    return matched / len(phrases)


def _no_answer_correct(answer: Optional[str], should_answer: bool) -> Optional[bool]:
    if answer is None:
        return None
    detected_no_answer = any(pattern in answer.lower() for pattern in NO_ANSWER_PATTERNS)
    return not detected_no_answer if should_answer else detected_no_answer


def _run_case(case: EvalCase, user: User, namespace: str, top_k: int, with_llm: bool) -> CaseResult:
    session = SessionLocal()
    try:
        doc_ids, missing_documents = _resolve_doc_ids(session, user.id, namespace, case.document_filenames)
        if missing_documents:
            return CaseResult(
                case_id=case.case_id,
                question=case.question,
                question_type=case.question_type,
                should_answer=case.should_answer,
                document_filenames=case.document_filenames,
                resolved_doc_ids=doc_ids,
                retrieved_sources=[],
                answer=None,
                retrieval_hit_rank=None,
                recall_at_1=False,
                recall_at_3=False,
                recall_at_5=False,
                reciprocal_rank=0.0,
                citation_hit=False,
                no_answer_correct=None,
                phrase_match_fraction=None,
                missing_documents=missing_documents,
                error="Missing one or more referenced documents for this user.",
            )

        query_embedding = embed_query(case.question)
        retrieved = hybrid_search(
            query=case.question,
            query_embedding=query_embedding,
            user_id=user.id,
            namespace=namespace,
            doc_ids=doc_ids,
            n_results=max(top_k, 5),
        )[:top_k]

        answer: Optional[str] = None
        if with_llm:
            answer = "".join(
                stream_chat(
                    question=case.question,
                    context_chunks=retrieved,
                    chat_history=[],
                )
            ).strip()

        hit_rank = _first_hit_rank(retrieved, case.expected_sources)
        return CaseResult(
            case_id=case.case_id,
            question=case.question,
            question_type=case.question_type,
            should_answer=case.should_answer,
            document_filenames=case.document_filenames,
            resolved_doc_ids=doc_ids,
            retrieved_sources=[
                {
                    "rank": index,
                    "filename": item.get("filename", ""),
                    "page_num": item.get("page_num", 0),
                    "score": round(float(item.get("score", 0.0)), 6),
                    "text_excerpt": item.get("text", "")[:240],
                }
                for index, item in enumerate(retrieved, start=1)
            ],
            answer=answer,
            retrieval_hit_rank=hit_rank,
            recall_at_1=hit_rank == 1,
            recall_at_3=hit_rank is not None and hit_rank <= 3,
            recall_at_5=hit_rank is not None and hit_rank <= 5,
            reciprocal_rank=0.0 if hit_rank is None else 1.0 / hit_rank,
            citation_hit=_citation_hit(answer, case.expected_sources),
            no_answer_correct=_no_answer_correct(answer, case.should_answer),
            phrase_match_fraction=_phrase_match_fraction(answer, case.expected_answer_contains),
            missing_documents=[],
            error=None,
        )
    except Exception as exc:
        return CaseResult(
            case_id=case.case_id,
            question=case.question,
            question_type=case.question_type,
            should_answer=case.should_answer,
            document_filenames=case.document_filenames,
            resolved_doc_ids=[],
            retrieved_sources=[],
            answer=None,
            retrieval_hit_rank=None,
            recall_at_1=False,
            recall_at_3=False,
            recall_at_5=False,
            reciprocal_rank=0.0,
            citation_hit=False,
            no_answer_correct=None,
            phrase_match_fraction=None,
            missing_documents=[],
            error=str(exc),
        )
    finally:
        session.close()


def _mean(values: List[float]) -> float:
    return 0.0 if not values else statistics.fmean(values)


def _build_summary(results: List[CaseResult], with_llm: bool) -> Dict[str, Any]:
    valid_results = [result for result in results if result.error is None]
    answerable = [result for result in valid_results if result.should_answer]
    no_answer_cases = [result for result in valid_results if not result.should_answer]
    phrase_scores = [r.phrase_match_fraction for r in valid_results if r.phrase_match_fraction is not None]
    no_answer_scores = [r.no_answer_correct for r in no_answer_cases if r.no_answer_correct is not None]

    summary = {
        "total_cases": len(results),
        "successful_cases": len(valid_results),
        "error_cases": len(results) - len(valid_results),
        "answerable_cases": len(answerable),
        "no_answer_cases": len(no_answer_cases),
        "recall_at_1": round(_mean([1.0 if r.recall_at_1 else 0.0 for r in answerable]), 4),
        "recall_at_3": round(_mean([1.0 if r.recall_at_3 else 0.0 for r in answerable]), 4),
        "recall_at_5": round(_mean([1.0 if r.recall_at_5 else 0.0 for r in answerable]), 4),
        "mrr": round(_mean([r.reciprocal_rank for r in answerable]), 4),
    }

    if with_llm:
        generated_answers = [result.answer for result in valid_results if result.answer]
        approx_input_tokens = sum(max(1, len(result.question) // APPROX_TOKEN_CHARS) for result in valid_results)
        approx_output_tokens = sum(max(1, len(answer) // APPROX_TOKEN_CHARS) for answer in generated_answers)
        approx_total_cost_usd = (
            (approx_input_tokens / 1000) * MODEL_COSTS_PER_1K_TOKENS["input_usd"] +
            (approx_output_tokens / 1000) * MODEL_COSTS_PER_1K_TOKENS["output_usd"]
        )
        summary.update(
            {
                "citation_hit_rate": round(_mean([1.0 if r.citation_hit else 0.0 for r in answerable]), 4),
                "answer_phrase_coverage": round(_mean([float(score) for score in phrase_scores]), 4) if phrase_scores else None,
                "no_answer_accuracy": round(
                    _mean([1.0 if bool(score) else 0.0 for score in no_answer_scores]),
                    4,
                ) if no_answer_scores else None,
                "approx_input_tokens": approx_input_tokens,
                "approx_output_tokens": approx_output_tokens,
                "approx_total_cost_usd": round(approx_total_cost_usd, 6),
                "approx_cost_per_case_usd": round(
                    approx_total_cost_usd / len(valid_results),
                    6,
                ) if valid_results else None,
            }
        )

    return summary


def _build_markdown_report(
    dataset_path: Path,
    user: User,
    namespace: str,
    summary: Dict[str, Any],
    results: List[CaseResult],
    with_llm: bool,
) -> str:
    lines = [
        "# ScaleRAG Evaluation Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Dataset: `{dataset_path}`",
        f"- User: `{user.email}` (id={user.id})",
        f"- Namespace: `{namespace}`",
        f"- LLM scoring enabled: `{with_llm}`",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary['total_cases']}",
        f"- Successful cases: {summary['successful_cases']}",
        f"- Error cases: {summary['error_cases']}",
        f"- Answerable cases: {summary['answerable_cases']}",
        f"- No-answer cases: {summary['no_answer_cases']}",
        f"- Recall@1: {summary['recall_at_1']}",
        f"- Recall@3: {summary['recall_at_3']}",
        f"- Recall@5: {summary['recall_at_5']}",
        f"- MRR: {summary['mrr']}",
    ]

    if with_llm:
        lines.extend(
            [
                f"- Citation hit rate: {summary.get('citation_hit_rate')}",
                f"- Answer phrase coverage: {summary.get('answer_phrase_coverage')}",
                f"- No-answer accuracy: {summary.get('no_answer_accuracy')}",
                f"- Approx input tokens: {summary.get('approx_input_tokens')}",
                f"- Approx output tokens: {summary.get('approx_output_tokens')}",
                f"- Approx total cost (USD): {summary.get('approx_total_cost_usd')}",
                f"- Approx cost per case (USD): {summary.get('approx_cost_per_case_usd')}",
            ]
        )

    lines.extend(
        [
            "",
            "## Case Results",
            "",
            "| Case | Type | Hit Rank | R@1 | R@3 | R@5 | Citation Hit | Error |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )

    for result in results:
        lines.append(
            "| {case_id} | {question_type} | {hit_rank} | {r1} | {r3} | {r5} | {citation} | {error} |".format(
                case_id=result.case_id,
                question_type=result.question_type,
                hit_rank=result.retrieval_hit_rank if result.retrieval_hit_rank is not None else "-",
                r1="Y" if result.recall_at_1 else "N",
                r3="Y" if result.recall_at_3 else "N",
                r5="Y" if result.recall_at_5 else "N",
                citation="Y" if result.citation_hit else "N",
                error=result.error or "",
            )
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    create_tables()
    cases = _load_dataset(dataset_path)

    session = SessionLocal()
    try:
        user = _resolve_user(session, args.user_email, args.user_id)
    finally:
        session.close()

    results = [_run_case(case, user, args.namespace, args.top_k, args.with_llm) for case in cases]
    summary = _build_summary(results, args.with_llm)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_report_path = output_dir / f"eval_report_{timestamp}.json"
    md_report_path = output_dir / f"eval_report_{timestamp}.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "user_email": user.email,
        "user_id": user.id,
        "namespace": args.namespace,
        "with_llm": args.with_llm,
        "summary": summary,
        "results": [asdict(result) for result in results],
    }

    json_report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_report_path.write_text(
        _build_markdown_report(dataset_path, user, args.namespace, summary, results, args.with_llm),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"JSON report: {json_report_path}")
    print(f"Markdown report: {md_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
