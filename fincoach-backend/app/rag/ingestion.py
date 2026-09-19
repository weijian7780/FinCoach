"""Native document loading for the FinCoach knowledge corpus."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class LoadedDocument:
    content: str
    source: str
    title: str
    page: int | None = None


def _document_title(path: Path, content: str) -> str:
    if path.suffix.lower() == ".md":
        heading = re.search(r"^#\s+(.+?)\s*$", content, flags=re.MULTILINE)
        if heading:
            return heading.group(1).strip()
    words = re.sub(r"[-_]+", " ", path.stem).strip()
    return words.title()


def load_documents(root: Path) -> list[LoadedDocument]:
    """Load supported corpus files in deterministic relative-path order."""
    if not root.exists():
        return []
    supported = {".txt", ".md", ".pdf"}
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in supported),
        key=lambda path: path.relative_to(root).as_posix().lower(),
    )
    documents: list[LoadedDocument] = []
    for path in paths:
        source = path.relative_to(root).as_posix()
        if path.suffix.lower() in {".txt", ".md"}:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                documents.append(LoadedDocument(content, source, _document_title(path, content)))
            continue

        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            content = (page.extract_text() or "").strip()
            if content:
                documents.append(
                    LoadedDocument(content, source, _document_title(path, content), page_number)
                )
    return documents
