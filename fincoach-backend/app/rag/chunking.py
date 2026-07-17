"""Deterministic text chunking with overlap and stable content hashes."""

from dataclasses import dataclass
from hashlib import sha256
import re

from app.rag.ingestion import LoadedDocument


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


def chunk_document(
    document: LoadedDocument,
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]:
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
