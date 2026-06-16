import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.rag_production_smoke_test import (
    build_namespace,
    create_manifest_entry,
    generate_documents,
    answer_contains_only_expected_canary,
    citations_contain_document,
    sources_contain_document,
)


class RagSmokeHarnessTests(unittest.TestCase):
    def test_namespace_has_expected_prefix(self):
        namespace = build_namespace("RUN-20260616T120000Z")
        self.assertEqual(namespace, "rag-smoke-20260616t120000z")

    def test_manifest_entry_has_expected_question(self):
        entry = create_manifest_entry(1, "RUN-20260616T120000Z", Path("docs"))
        self.assertEqual(entry.document_id, "RAG-SMOKE-DOC-0001")
        self.assertIn(entry.document_id, entry.question)
        self.assertTrue(entry.expected_answer.startswith("CANARY-"))

    def test_answer_match_rejects_cross_document_canary(self):
        all_canaries = ["CANARY-AAAA1111", "CANARY-BBBB2222"]
        self.assertTrue(
            answer_contains_only_expected_canary(
                "The code is CANARY-AAAA1111.",
                "CANARY-AAAA1111",
                all_canaries,
            )
        )
        self.assertFalse(
            answer_contains_only_expected_canary(
                "The code is CANARY-AAAA1111 and maybe CANARY-BBBB2222.",
                "CANARY-AAAA1111",
                all_canaries,
            )
        )

    def test_source_and_citation_helpers(self):
        sources = [{"filename": "RAG-SMOKE-DOC-0001.pdf"}]
        self.assertTrue(sources_contain_document(sources, "RAG-SMOKE-DOC-0001.pdf"))
        self.assertTrue(citations_contain_document("See [RAG-SMOKE-DOC-0001.pdf, Page 1]", "RAG-SMOKE-DOC-0001.pdf"))

    def test_generate_documents_writes_manifest_and_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_docs = Path(tmpdir) / "docs"
            temp_docs.mkdir(parents=True, exist_ok=True)
            with patch("scripts.rag_production_smoke_test.GENERATED_DOCS_DIR", temp_docs), \
                    patch("scripts.rag_production_smoke_test.MANIFEST_PATH", Path(tmpdir) / "manifest.jsonl"):
                docs = generate_documents("RUN-20260616T120000Z", 6, docs_dir=temp_docs)
            self.assertEqual(len(docs), 6)
            self.assertEqual(len(list(temp_docs.iterdir())), 6)


if __name__ == "__main__":
    unittest.main()
