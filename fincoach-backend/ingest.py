"""Phase 1 — build the knowledge base.

Loads documents from ./corpus, chunks them, embeds with bge-m3, and stores the
vectors in Supabase (knowledge_documents). Run once, and again whenever you add docs.
After the admin migration, use the website's versioned publishing workflow;
this legacy command supports local --validate checks only on that schema.

    python ingest.py
    python ingest.py --validate
    python ingest.py --prune --verify

Document loading and chunking are implemented with native Python and pypdf.
"""
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

from app.embeddings import embed_texts
from app.rag.chunking import DEFAULT_MAX_DOCUMENT_CHARS, DocumentChunk, chunk_document
from app.rag.ingestion import LoadedDocument, load_documents
from app.supabase_client import get_supabase

CORPUS_DIR = Path("corpus")
MAX_DOCUMENT_CHARS = DEFAULT_MAX_DOCUMENT_CHARS
BATCH = 100
SOURCE_CHECKED_DATE = re.compile(
    r"^Official sources? checked:\s*(?P<date>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class CorpusValidation:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def validate_corpus_documents(
    documents: list[LoadedDocument],
    *,
    today: date | None = None,
    max_source_age_days: int = 90,
) -> CorpusValidation:
    """Require dated official-source evidence without silently blocking refreshes."""
    errors: list[str] = []
    warnings: list[str] = []
    today = today or date.today()
    for document in documents:
        match = SOURCE_CHECKED_DATE.search(document.content)
        if not match:
            errors.append(f"{document.source} is missing Official source checked date")
            continue
        try:
            checked_date = datetime.strptime(
                match.group("date").strip(),
                "%d %B %Y",
            ).date()
        except ValueError:
            errors.append(f"{document.source} has an invalid Official source checked date")
            continue
        if (today - checked_date).days > max_source_age_days:
            warnings.append(
                f"{document.source} source check is older than {max_source_age_days} days"
            )
    return CorpusValidation(tuple(errors), tuple(warnings))


def build_chunks(documents: list[LoadedDocument]) -> list[DocumentChunk]:
    """Build complete short documents and bounded future document sections."""
    return [
        chunk
        for document in documents
        for chunk in chunk_document(
            document,
            max_document_chars=MAX_DOCUMENT_CHARS,
        )
    ]


def build_rows(
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> list[dict]:
    """Refuse partial embedding batches so prune cannot delete valid knowledge."""
    if len(chunks) != len(embeddings):
        raise RuntimeError(
            f"embedding count {len(embeddings)} does not match chunk count {len(chunks)}"
        )
    return [
        {
            "content": chunk.content,
            "title": chunk.title,
            "source": chunk.source,
            "page_number": chunk.page,
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
            "embedding": embedding,
        }
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]


def _normalize_source(value: Any) -> str:
    source = str(value or "").replace("\\", "/").lstrip("./")
    if source.lower().startswith("corpus/"):
        source = source[len("corpus/"):]
    return source


def stale_knowledge_ids(
    existing_rows: list[dict],
    current_hashes_by_source: dict[str, set[str]],
) -> list[int]:
    """Return database rows that are no longer represented by the corpus."""
    normalized_current = {
        _normalize_source(source): hashes
        for source, hashes in current_hashes_by_source.items()
    }
    stale: list[int] = []
    for row in existing_rows:
        source = _normalize_source(row.get("source"))
        valid_hashes = normalized_current.get(source)
        if valid_hashes is None or row.get("content_hash") not in valid_hashes:
            stale.append(int(row["id"]))
    return sorted(stale)


def _existing_knowledge_rows(client: Any) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            client.table("knowledge_documents")
            .select("id, source, content_hash")
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def _current_hashes(rows: list[dict]) -> dict[str, set[str]]:
    hashes: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        hashes[str(row["source"])].add(str(row["content_hash"]))
    return dict(hashes)


def require_legacy_knowledge_schema(client: Any) -> None:
    """Detect revision ownership independently of an environment feature flag.

    A zero-row projection checks the database contract without downloading text
    or embeddings. Only a missing revision_id column means the legacy schema;
    connection/authentication errors must not silently permit writes/pruning.
    """
    try:
        client.table("knowledge_documents").select("revision_id").limit(0).execute()
    except Exception as exc:
        if getattr(exc, "code", None) in {"42703", "PGRST204"}:
            return
        raise RuntimeError("Cannot verify knowledge schema; ingestion was stopped before embeddings or database writes.") from exc
    raise RuntimeError("The database uses versioned knowledge. Publish through /admin, or use --validate for local corpus checks. Legacy ingestion and pruning are unavailable after the admin migration.")


def _missing_knowledge_hashes(
    existing_rows: list[dict],
    current_hashes_by_source: dict[str, set[str]],
) -> list[str]:
    actual = {
        (_normalize_source(row.get("source")), str(row.get("content_hash")))
        for row in existing_rows
    }
    required = {
        (_normalize_source(source), content_hash)
        for source, hashes in current_hashes_by_source.items()
        for content_hash in hashes
    }
    return sorted(f"{source}:{content_hash}" for source, content_hash in required - actual)


def main(
    prune: bool = False,
    *,
    verify: bool = False,
    validate_only: bool = False,
):
    if prune and not verify:
        raise ValueError("--prune requires --verify to prevent accidental knowledge loss")
    documents = load_documents(CORPUS_DIR)
    if not documents:
        print(f"No documents found in ./{CORPUS_DIR}. Add .txt/.md/.pdf files and re-run.")
        return

    validation = validate_corpus_documents(documents)
    for warning in validation.warnings:
        print(f"WARNING: {warning}")
    if validation.errors:
        raise RuntimeError("Corpus validation failed: " + "; ".join(validation.errors))

    chunks = build_chunks(documents)
    if validate_only:
        print(
            f"Validated {len(documents)} document section(s) -> {len(chunks)} chunk(s)."
        )
        return
    # Stop the legacy writer before computing embeddings. Panel deployments use
    # revision-scoped, atomic publishing; global pruning would destroy revisions.
    from app.config import ADMIN_PANEL_ENABLED
    if ADMIN_PANEL_ENABLED:
        raise RuntimeError("Knowledge is managed by the admin panel. Use --validate for local corpus checks; publish changes through the panel.")
    sb = get_supabase()
    require_legacy_knowledge_schema(sb)
    print(
        f"Loaded {len(documents)} document section(s) -> {len(chunks)} chunk(s). "
        "Embedding with bge-m3..."
    )

    embeddings = embed_texts([chunk.content for chunk in chunks])

    rows = build_rows(chunks, embeddings)

    for i in range(0, len(rows), BATCH):
        (
            sb.table("knowledge_documents")
            .upsert(rows[i : i + BATCH], on_conflict="content_hash")
            .execute()
        )

    current_hashes = _current_hashes(rows)
    if verify:
        missing = _missing_knowledge_hashes(
            _existing_knowledge_rows(sb),
            current_hashes,
        )
        if missing:
            raise RuntimeError(
                "Refusing to prune because replacement knowledge chunks are missing: "
                + ", ".join(missing)
            )

    deleted = 0
    if prune:
        stale_ids = stale_knowledge_ids(
            _existing_knowledge_rows(sb),
            current_hashes,
        )
        for i in range(0, len(stale_ids), BATCH):
            batch_ids = stale_ids[i : i + BATCH]
            if batch_ids:
                sb.table("knowledge_documents").delete().in_("id", batch_ids).execute()
                deleted += len(batch_ids)

    if verify and prune:
        existing_rows = _existing_knowledge_rows(sb)
        missing = _missing_knowledge_hashes(existing_rows, current_hashes)
        stale = stale_knowledge_ids(existing_rows, current_hashes)
        if missing or stale:
            details = []
            if missing:
                details.append("missing=" + ", ".join(missing))
            if stale:
                details.append("stale_ids=" + ", ".join(str(item) for item in stale))
            raise RuntimeError("Knowledge verification failed after prune: " + "; ".join(details))

    print(f"Stored {len(rows)} chunks in knowledge_documents.")
    if prune:
        print(f"Removed {deleted} stale chunk(s) not present in the current corpus.")


if __name__ == "__main__":
    parser = ArgumentParser(description="Ingest FinCoach knowledge documents.")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove database chunks that are no longer present in ./corpus.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify replacement chunks exist before pruning and verify the final corpus after pruning.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate source dates and chunking without embeddings or database writes.",
    )
    arguments = parser.parse_args()
    main(
        prune=arguments.prune,
        verify=arguments.verify,
        validate_only=arguments.validate,
    )
