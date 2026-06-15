"""
Synthetic document generator for 10K+ scale benchmarking.
Generates PDF, HTML, and CSV files using reportlab + faker.

Usage:
    python scripts/generate_test_docs.py --count 500 --output ./test_docs
"""
from __future__ import annotations

import argparse
import os
import random
from pathlib import Path

from faker import Faker
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

fake = Faker()
styles = getSampleStyleSheet()

TOPICS = [
    "machine learning", "cloud computing", "data engineering", "system design",
    "microservices", "kubernetes", "RAG pipelines", "vector databases",
    "transformer models", "financial analysis", "market research",
    "product management", "human resources", "legal compliance",
]


def _make_pdf(path: str, pages: int = 5) -> None:
    doc = SimpleDocTemplate(path, pagesize=letter)
    topic = random.choice(TOPICS)
    story = [Paragraph(f"<b>{fake.catch_phrase()} — {topic.title()}</b>", styles["Title"]), Spacer(1, 12)]
    for _ in range(pages):
        story.append(Paragraph(fake.sentence(nb_words=8), styles["Heading2"]))
        for _ in range(random.randint(3, 6)):
            story.append(Paragraph(fake.paragraph(nb_sentences=random.randint(4, 8)), styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)


def _make_html(path: str) -> None:
    topic = random.choice(TOPICS)
    paragraphs = "".join(
        f"<h2>{fake.sentence(nb_words=5)}</h2><p>{fake.paragraph(nb_sentences=5)}</p>"
        for _ in range(random.randint(4, 8))
    )
    html = f"""<!DOCTYPE html>
<html><head><title>{topic.title()}</title></head>
<body>
<h1>{fake.catch_phrase()} — {topic.title()}</h1>
{paragraphs}
</body></html>"""
    Path(path).write_text(html, encoding="utf-8")


def _make_csv(path: str, rows: int = 50) -> None:
    headers = ["id", "name", "department", "metric_a", "metric_b", "description"]
    lines = [",".join(headers)]
    for i in range(rows):
        row = [
            str(i + 1),
            fake.name().replace(",", ""),
            fake.job().replace(",", ""),
            str(round(random.uniform(10, 1000), 2)),
            str(round(random.uniform(0.1, 99.9), 2)),
            fake.sentence(nb_words=6).replace(",", ""),
        ]
        lines.append(",".join(row))
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic test documents.")
    parser.add_argument("--count", type=int, default=300, help="Total documents to generate")
    parser.add_argument("--output", type=str, default="./test_docs", help="Output directory")
    parser.add_argument("--pdf-ratio", type=float, default=0.6, help="Fraction of PDFs (0–1)")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    n_pdf = int(args.count * args.pdf_ratio)
    n_html = int(args.count * 0.2)
    n_csv = args.count - n_pdf - n_html

    print(f"Generating {n_pdf} PDFs, {n_html} HTMLs, {n_csv} CSVs in {out}/")

    for i in range(n_pdf):
        _make_pdf(str(out / f"doc_{i:05d}.pdf"), pages=random.randint(3, 10))
        if (i + 1) % 50 == 0:
            print(f"  PDFs: {i + 1}/{n_pdf}")

    for i in range(n_html):
        _make_html(str(out / f"page_{i:05d}.html"))
    print(f"  HTMLs: {n_html}")

    for i in range(n_csv):
        _make_csv(str(out / f"data_{i:05d}.csv"), rows=random.randint(20, 100))
    print(f"  CSVs: {n_csv}")

    print(f"\nDone. {args.count} documents in {out}/")
    print("Expected chunks: ~", args.count * 15, "(rough estimate)")


if __name__ == "__main__":
    main()
