"""Deterministic document chunking with stable content hashes."""

from dataclasses import dataclass
from hashlib import sha256
import re

from app.rag.ingestion import LoadedDocument


DEFAULT_MAX_DOCUMENT_CHARS = 3000


@dataclass(frozen=True)
class DocumentChunk:
    content: str
    source: str
    title: str
    page: int | None
    chunk_index: int
    content_hash: str


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return sha256(normalized.encode("utf-8")).hexdigest()


def _preferred_end(text: str, start: int, hard_end: int) -> int:
    if hard_end >= len(text):
        return len(text)
    window = text[start:hard_end]
    minimum = max(1, len(window) // 2)
    for separator in ("\n\n", ". ", "\n", " "):
        index = window.rfind(separator)
        if index >= minimum:
            return start + index + (1 if separator == ". " else 0)
    return hard_end


def _legacy_overlap_chunks(
    document: LoadedDocument,
    *,
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]:
    """Keep the former splitter available for non-corpus callers only."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between zero and chunk_size - 1")

    text = document.content.strip()
    if not text:
        return []

    chunks: list[DocumentChunk] = []
    start = 0
    while start < len(text):
        end = _preferred_end(text, start, min(len(text), start + chunk_size))
        content = text[start:end].strip()
        if content:
            chunks.append(DocumentChunk(
                content=content,
                source=document.source,
                title=document.title,
                page=document.page,
                chunk_index=len(chunks),
                content_hash=content_hash(content),
            ))
        if end >= len(text):
            break
        next_start = end - overlap
        while next_start < len(text) and text[next_start].isspace():
            next_start += 1
        start = max(start + 1, next_start)
    return chunks


def _split_long_paragraph(paragraph: str, max_document_chars: int) -> list[str]:
    """Split only at sentence or word boundaries; never duplicate overlap."""
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", paragraph)
        if item.strip()
    ]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_document_chars:
            words = sentence.split()
            if any(len(word) > max_document_chars for word in words):
                raise ValueError("A corpus word exceeds max_document_chars")
            sentence_parts: list[str] = []
            word_group = ""
            for word in words:
                candidate = f"{word_group} {word}".strip()
                if word_group and len(candidate) > max_document_chars:
                    sentence_parts.append(word_group)
                    word_group = word
                else:
                    word_group = candidate
            if word_group:
                sentence_parts.append(word_group)
        else:
            sentence_parts = [sentence]

        for part in sentence_parts:
            candidate = f"{current} {part}".strip()
            if current and len(candidate) > max_document_chars:
                chunks.append(current)
                current = part
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def _document_sections(text: str, max_document_chars: int) -> list[str]:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    sections: list[str] = []
    current = ""
    for paragraph in paragraphs:
        parts = (
            [paragraph]
            if len(paragraph) <= max_document_chars
            else _split_long_paragraph(paragraph, max_document_chars)
        )
        for part in parts:
            candidate = f"{current}\n\n{part}".strip()
            if current and len(candidate) > max_document_chars:
                sections.append(current)
                current = part
            else:
                current = candidate
    if current:
        sections.append(current)
    return sections


def chunk_document(
    document: LoadedDocument,
    chunk_size: int | None = None,
    overlap: int | None = None,
    *,
    max_document_chars: int | None = None,
) -> list[DocumentChunk]:
    """Return full current-corpus documents, with safe future fallback splits.

    ``chunk_size`` and ``overlap`` retain the old helper behavior only for
    callers that explicitly use both parameters. Corpus ingestion uses the
    document mode so overlapping near-duplicate vectors are no longer stored.
    """
    if max_document_chars is None and chunk_size is not None:
        if overlap is None:
            raise ValueError("overlap is required with legacy chunk_size")
        return _legacy_overlap_chunks(
            document,
            chunk_size=chunk_size,
            overlap=overlap,
        )

    limit = max_document_chars or DEFAULT_MAX_DOCUMENT_CHARS
    if limit <= 0:
        raise ValueError("max_document_chars must be greater than zero")
    text = document.content.strip()
    if not text:
        return []

    sections = [text] if len(text) <= limit else _document_sections(text, limit)
    return [
        DocumentChunk(
            content=content,
            source=document.source,
            title=document.title,
            page=document.page,
            chunk_index=index,
            content_hash=content_hash(content),
        )
        for index, content in enumerate(sections)
    ]
