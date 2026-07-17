import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class NativeIngestionTests(unittest.TestCase):
    def test_loads_text_and_markdown_in_stable_path_order(self):
        from app.rag.ingestion import load_documents

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z-notes.md").write_text("# Budget notes", encoding="utf-8")
            (root / "a-guide.txt").write_text("Student finance guide", encoding="utf-8")

            documents = load_documents(root)

        self.assertEqual([item.title for item in documents], ["a-guide.txt", "z-notes.md"])
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


class DeterministicChunkingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
