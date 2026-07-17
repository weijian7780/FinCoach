"""Phase 1 — build the knowledge base.

Loads documents from ./corpus, chunks them, embeds with bge-m3, and stores the
vectors in Supabase (knowledge_documents). Run once, and again whenever you add docs.

    python ingest.py

Document loading and chunking are implemented with native Python and pypdf.
"""
from pathlib import Path

from app.embeddings import embed_texts
from app.rag.chunking import chunk_document
from app.rag.ingestion import load_documents
from app.supabase_client import get_supabase

CORPUS_DIR = Path("corpus")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
BATCH = 100
def main():
    documents = load_documents(CORPUS_DIR)
    if not documents:
        print(f"No documents found in ./{CORPUS_DIR}. Add .txt/.md/.pdf files and re-run.")
        return

    chunks = [
        chunk
        for document in documents
        for chunk in chunk_document(document, CHUNK_SIZE, CHUNK_OVERLAP)
    ]
    print(
        f"Loaded {len(documents)} document section(s) -> {len(chunks)} chunk(s). "
        "Embedding with bge-m3..."
    )

    embeddings = embed_texts([chunk.content for chunk in chunks])

    rows = [
        {
            "content": chunk.content,
            "title": chunk.title,
            "source": chunk.source,
            "page_number": chunk.page,
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
            "embedding": embedding,
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]

    sb = get_supabase()
    for i in range(0, len(rows), BATCH):
        (
            sb.table("knowledge_documents")
            .upsert(rows[i : i + BATCH], on_conflict="content_hash")
            .execute()
        )

    print(f"Stored {len(rows)} chunks in knowledge_documents.")


if __name__ == "__main__":
    main()
