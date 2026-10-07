"""Bounded local document extraction; uploaded text is never executed."""
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from app.rag.chunking import LoadedDocument, chunk_document

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_CONTENT_CHARS = 200_000


class RevisionInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    source_urls: list[str] = Field(min_length=1, max_length=20)
    checked_at: date
    expected_revision_id: UUID | None = None
    upload_id: UUID | None = None

    @field_validator("title", "content")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Text must be non-empty and contain no NUL characters.")
        return value

    @field_validator("source_urls")
    @classmethod
    def safe_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value)
            if len(value) > 2048 or parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Sources must be HTTP(S) URLs without credentials.")
        return list(dict.fromkeys(values))

    @field_validator("checked_at")
    @classmethod
    def past_date(cls, value: date) -> date:
        if value > datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date():
            raise ValueError("Source check date cannot be in the future.")
        return value


def extract_document(filename: str, data: bytes) -> str:
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload a non-empty document of at most 10 MiB.")
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".txt"}:
        try:
            text = data.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Text documents must use UTF-8 encoding.") from exc
    elif suffix == ".pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ValueError("PDFs must be unencrypted and contain at most 100 pages.")
            pages, size = [], 0
            for page in reader.pages:
                value = (page.extract_text() or "").strip()
                size += len(value)
                if size > MAX_CONTENT_CHARS:
                    raise ValueError("Extracted document exceeds 200,000 characters.")
                pages.append(value)
            text = "\n\n".join(pages).strip()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("PDF could not be read. Upload a text-based PDF.") from exc
    else:
        raise ValueError("Supported files are Markdown, UTF-8 text, and text-based PDFs.")
    if not text or "\x00" in text or len(text) > MAX_CONTENT_CHARS:
        raise ValueError("Document must contain readable text, up to 200,000 characters. Scanned-only PDFs are unsupported.")
    return text


def build_revision_chunks(revision: dict, source_key: str):
    from dataclasses import replace
    from app.rag.chunking import content_hash
    checked = date.fromisoformat(str(revision["checked_at"])[:10])
    # Each chunk carries the existing corpus provenance format so freshness
    # checks still work when the source is maintained through this panel.
    prefix = f"Official source checked: {checked.strftime('%d %B %Y')}\n\n"
    prefix += "\n".join(revision["source_urls"]) + "\n\n"
    chunks = chunk_document(LoadedDocument(revision["content"], source_key, revision["title"]))
    return [replace(chunk, content=prefix + chunk.content, content_hash=content_hash(prefix + chunk.content)) for chunk in chunks]
