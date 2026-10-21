"""Admin boundaries and ingestion regressions without external provider calls."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException


class AdminPermissionTests(unittest.TestCase):
    def test_student_cannot_gain_access_through_user_metadata(self):
        from app.admin.service import require_administrator
        from app.auth import AuthenticatedUser
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
            "role": "student", "status": "active", "user_metadata": {"role": "admin"},
        }
        with patch("app.admin.service.get_supabase", return_value=client):
            with self.assertRaises(HTTPException) as caught:
                require_administrator(AuthenticatedUser("student", "token"))
        self.assertEqual(caught.exception.status_code, 403)

    def test_suspended_administrator_is_rejected(self):
        from app.admin.service import require_administrator
        from app.auth import AuthenticatedUser
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
            "role": "admin", "status": "suspended",
        }
        with patch("app.admin.service.get_supabase", return_value=client):
            with self.assertRaises(HTTPException):
                require_administrator(AuthenticatedUser("admin", "token"))


class DocumentValidationTests(unittest.TestCase):
    def test_utf8_markdown_has_no_invented_pdf_page(self):
        from app.admin.documents import extract_document
        self.assertEqual(extract_document("guide.md", b"# Guide\nBudget safely."), "# Guide\nBudget safely.")

    def test_rejects_unsupported_and_empty_files(self):
        from app.admin.documents import extract_document
        for name, content in (("guide.exe", b"binary"), ("guide.txt", b" "), ("guide.txt", b"\xff")):
            with self.subTest(name=name, content=content), self.assertRaises(ValueError):
                extract_document(name, content)

    def test_requires_sources_and_non_future_check_date(self):
        from app.admin.documents import RevisionInput
        for patch_data in ({"checked_at": "2999-01-01"}, {"source_urls": ["javascript:alert(1)"]}):
            data = dict(title="Guide", content="Verified guidance", source_urls=["https://example.org/guide"], checked_at=str(date.today()))
            data.update(patch_data)
            with self.subTest(patch=patch_data), self.assertRaises(ValueError):
                RevisionInput(**data)

    def test_import_without_accuracy_claim(self):
        from app.admin.documents import RevisionInput, build_revision_chunks
        value = RevisionInput(title="Uploaded guide", content="Build an emergency fund.")
        chunks = build_revision_chunks(value.model_dump(mode="json"), "guide.md")
        self.assertNotIn("Official source checked:", chunks[0].content)
        self.assertIn("not independently verified", chunks[0].content)

    def test_identical_content_from_two_sources_remains_distinct(self):
        from app.admin.documents import build_revision_chunks
        first = build_revision_chunks({"title": "A", "content": "Shared guidance", "source_urls": ["https://example.org/a"], "checked_at": "2026-09-01"}, "a.md")
        second = build_revision_chunks({"title": "B", "content": "Shared guidance", "source_urls": ["https://example.org/a"], "checked_at": "2026-09-01"}, "b.md")
        self.assertEqual(first[0].source, "a.md")
        self.assertEqual(second[0].source, "b.md")


class WorkerSafetyTests(unittest.TestCase):
    def test_partial_embeddings_never_mark_revision_ready(self):
        from app.admin.worker import process_revision
        client = MagicMock()
        revision = dict(id="revision", lease_token="lease", source_key="guide.md", title="Guide", content="Guidance", source_urls=["https://example.org"], checked_at="2026-09-01")
        with patch("app.admin.worker.embed_texts", return_value=[]):
            with self.assertRaises(ValueError):
                process_revision(client, revision)
        client.rpc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
