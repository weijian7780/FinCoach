import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class NativeIngestionTests(unittest.TestCase):
    def test_loads_text_and_markdown_in_stable_path_order(self):
        from app.rag.ingestion import load_documents

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z-notes.md").write_text("# Budget notes", encoding="utf-8")
            (root / "a-guide.txt").write_text("Student finance guide", encoding="utf-8")

            documents = load_documents(root)

        self.assertEqual([item.title for item in documents], ["A Guide", "Budget notes"])
        self.assertEqual(documents[0].content, "Student finance guide")
        self.assertEqual(documents[0].source, "a-guide.txt")

    def test_loads_each_non_empty_pdf_page_with_page_number(self):
        from app.rag.ingestion import load_documents

        pages = [
            SimpleNamespace(extract_text=lambda: "Page one"),
            SimpleNamespace(extract_text=lambda: "   "),
            SimpleNamespace(extract_text=lambda: "Page three"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.pdf").write_bytes(b"fake-pdf")
            with patch("pypdf.PdfReader", return_value=SimpleNamespace(pages=pages)):
                documents = load_documents(root)

        self.assertEqual([item.page for item in documents], [1, 3])
        self.assertEqual([item.content for item in documents], ["Page one", "Page three"])

    def test_ignores_unsupported_files_and_empty_documents(self):
        from app.rag.ingestion import load_documents

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty.txt").write_text("  \n", encoding="utf-8")
            (root / "image.png").write_bytes(b"not-text")

            self.assertEqual(load_documents(root), [])

    def test_repository_corpus_contains_no_placeholder_document(self):
        from app.rag.ingestion import load_documents

        corpus = Path(__file__).resolve().parents[1] / "corpus"
        documents = load_documents(corpus)

        self.assertGreaterEqual(len(documents), 3)
        self.assertFalse(any("sample_" in item.source.lower() for item in documents))
        self.assertTrue(all("official source" in item.content.lower() for item in documents))


class DeterministicChunkingTests(unittest.TestCase):
    def test_keeps_a_short_document_as_one_complete_chunk(self):
        from app.rag.chunking import chunk_document
        from app.rag.ingestion import LoadedDocument

        document = LoadedDocument(
            content="First paragraph.\n\nSecond paragraph.",
            source="guide.md",
            title="Guide",
            page=None,
        )

        chunks = chunk_document(document, max_document_chars=3000)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, document.content)
        self.assertEqual(chunks[0].chunk_index, 0)

    def test_splits_an_oversized_document_at_paragraph_boundaries_without_overlap(self):
        from app.rag.chunking import chunk_document
        from app.rag.ingestion import LoadedDocument

        document = LoadedDocument(
            content="Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph.",
            source="guide.md",
            title="Guide",
            page=None,
        )

        chunks = chunk_document(document, max_document_chars=32)

        self.assertEqual(
            [chunk.content for chunk in chunks],
            ["Alpha paragraph.", "Beta paragraph.", "Gamma paragraph."],
        )
        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1, 2])

    def test_chunks_with_overlap_and_stable_metadata(self):
        from app.rag.chunking import chunk_document
        from app.rag.ingestion import LoadedDocument

        document = LoadedDocument(
            content="abcdefghij",
            source="guide.txt",
            title="guide.txt",
            page=None,
        )

        chunks = chunk_document(document, chunk_size=6, overlap=2)

        self.assertEqual([item.content for item in chunks], ["abcdef", "efghij"])
        self.assertEqual([item.chunk_index for item in chunks], [0, 1])
        self.assertEqual([item.source for item in chunks], ["guide.txt", "guide.txt"])
        self.assertTrue(all(len(item.content_hash) == 64 for item in chunks))

    def test_prefers_paragraph_boundary_without_losing_text(self):
        from app.rag.chunking import chunk_document
        from app.rag.ingestion import LoadedDocument

        document = LoadedDocument(
            content="First paragraph.\n\nSecond paragraph is longer.",
            source="guide.md",
            title="guide.md",
            page=None,
        )

        chunks = chunk_document(document, chunk_size=28, overlap=0)

        self.assertEqual([item.content for item in chunks], ["First paragraph.", "Second paragraph is longer."])

    def test_rejects_invalid_chunk_configuration(self):
        from app.rag.chunking import chunk_document
        from app.rag.ingestion import LoadedDocument

        document = LoadedDocument("text", "guide.txt", "guide.txt", None)
        for chunk_size, overlap in [(0, 0), (5, -1), (5, 5), (5, 6)]:
            with self.subTest(chunk_size=chunk_size, overlap=overlap):
                with self.assertRaises(ValueError):
                    chunk_document(document, chunk_size=chunk_size, overlap=overlap)

    def test_content_hash_normalizes_whitespace(self):
        from app.rag.chunking import content_hash

        self.assertEqual(content_hash("A  budget\nplan"), content_hash("A budget plan"))


class KnowledgeSynchronizationTests(unittest.TestCase):
    def test_migrated_database_blocks_legacy_writes_even_with_admin_flag_off(self):
        from ingest import main
        from app.rag.ingestion import LoadedDocument
        client = MagicMock()
        documents = [LoadedDocument('Official source checked: 1 October 2026\nBody', 'test.md', 'Test')]
        with patch('app.config.ADMIN_PANEL_ENABLED', False), patch('ingest.load_documents', return_value=documents), patch('ingest.get_supabase', return_value=client), patch('ingest.embed_texts') as embed:
            with self.assertRaisesRegex(RuntimeError, 'database uses versioned knowledge'):
                main(prune=True, verify=True)
        embed.assert_not_called()
        client.table.return_value.upsert.assert_not_called()
        client.table.return_value.delete.assert_not_called()

    def test_local_validation_remains_available_without_database_access(self):
        from ingest import main
        from app.rag.ingestion import LoadedDocument
        documents = [LoadedDocument('Official source checked: 1 October 2026\nBody', 'test.md', 'Test')]
        with patch('app.config.ADMIN_PANEL_ENABLED', True), patch('ingest.load_documents', return_value=documents), patch('ingest.get_supabase') as database, patch('ingest.embed_texts') as embed:
            main(validate_only=True)
        database.assert_not_called()
        embed.assert_not_called()

    def test_only_missing_revision_column_allows_legacy_schema(self):
        from ingest import require_legacy_knowledge_schema
        from postgrest.exceptions import APIError
        for code in ('42703', 'PGRST204'):
            client = MagicMock()
            client.table.return_value.select.return_value.limit.return_value.execute.side_effect = APIError({'code': code, 'message': 'revision_id column missing', 'details': None, 'hint': None})
            require_legacy_knowledge_schema(client)
        for code in ('42501', 'PGRST205'):
            client = MagicMock()
            client.table.return_value.select.return_value.limit.return_value.execute.side_effect = APIError({'code': code, 'message': 'database unavailable', 'details': None, 'hint': None})
            with self.assertRaisesRegex(RuntimeError, 'Cannot verify knowledge schema'):
                require_legacy_knowledge_schema(client)

    def test_unmigrated_ingestion_still_writes_legacy_chunks(self):
        from ingest import main
        from app.rag.ingestion import LoadedDocument
        from postgrest.exceptions import APIError
        client = MagicMock()
        client.table.return_value.select.return_value.limit.return_value.execute.side_effect = APIError({'code': '42703', 'message': 'revision_id column missing', 'details': None, 'hint': None})
        documents = [LoadedDocument('Official source checked: 1 October 2026\nBody', 'test.md', 'Test')]
        with patch('app.config.ADMIN_PANEL_ENABLED', False), patch('ingest.load_documents', return_value=documents), patch('ingest.get_supabase', return_value=client), patch('ingest.embed_texts', return_value=[[0.1]*1024]):
            main()
        self.assertEqual(client.table.return_value.upsert.call_count, 1)

    def test_rejects_incomplete_embedding_results_before_pruning(self):
        from ingest import build_rows
        from app.rag.chunking import DocumentChunk

        chunks = [
            DocumentChunk("One", "one.md", "One", None, 0, "hash-one"),
            DocumentChunk("Two", "two.md", "Two", None, 0, "hash-two"),
        ]

        with self.assertRaisesRegex(RuntimeError, "embedding count"):
            build_rows(chunks, [[0.1, 0.2]])

    def test_rejects_prune_without_verification(self):
        from ingest import main

        with self.assertRaisesRegex(ValueError, "--prune requires --verify"):
            main(prune=True)

    def test_current_official_corpus_builds_one_chunk_per_document(self):
        from ingest import build_chunks
        from app.rag.ingestion import load_documents

        corpus = Path(__file__).resolve().parents[1] / "corpus"
        documents = load_documents(corpus)

        chunks = build_chunks(documents)

        self.assertEqual(len(documents), 17)
        self.assertEqual(len(chunks), 17)
        self.assertEqual(
            {chunk.source for chunk in chunks},
            {document.source for document in documents},
        )

    def test_validates_official_source_check_dates_and_warns_when_stale(self):
        from ingest import validate_corpus_documents
        from app.rag.ingestion import LoadedDocument

        valid = LoadedDocument(
            "# Guide\nOfficial source checked: 22 July 2026\nBody",
            "valid.md",
            "Guide",
        )
        stale = LoadedDocument(
            "# Guide\nOfficial sources checked: 1 January 2026\nBody",
            "stale.md",
            "Guide",
        )
        missing = LoadedDocument("# Guide\nBody", "missing.md", "Guide")

        validation = validate_corpus_documents(
            [valid, stale, missing],
            today=date(2026, 8, 5),
        )

        self.assertEqual(validation.errors, ("missing.md is missing Official source checked date",))
        self.assertEqual(validation.warnings, ("stale.md source check is older than 90 days",))

    def test_prune_detects_removed_and_replaced_corpus_chunks(self):
        from ingest import stale_knowledge_ids

        existing = [
            {
                "id": 1,
                "source": r"corpus\sample_my_student_finance.md",
                "content_hash": "old-sample",
            },
            {
                "id": 2,
                "source": "official_budgeting.md",
                "content_hash": "current",
            },
            {
                "id": 3,
                "source": "official_budgeting.md",
                "content_hash": "old-version",
            },
            {
                "id": 4,
                "source": "removed_document.pdf",
                "content_hash": "removed",
            },
        ]
        current = {"official_budgeting.md": {"current"}}

        self.assertEqual(stale_knowledge_ids(existing, current), [1, 3, 4])


if __name__ == "__main__":
    unittest.main()
