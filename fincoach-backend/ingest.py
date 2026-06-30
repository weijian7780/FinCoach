"""Phase 1 — build the knowledge base.

Loads documents from ./corpus, chunks them, embeds with bge-m3, and stores the
vectors in Supabase (knowledge_documents). Run once, and again whenever you add docs.

    python ingest.py

LangChain is used here (and ONLY here) for document loading + chunking.
"""
import glob
import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.embeddings import embed_texts
from app.supabase_client import get_supabase

CORPUS_DIR = "corpus"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
BATCH = 100


def load_documents():
    docs = []
    for path in glob.glob(os.path.join(CORPUS_DIR, "**", "*"), recursive=True):
        lower = path.lower()
        if lower.endswith((".txt", ".md")):
            docs.extend(TextLoader(path, encoding="utf-8").load())
        elif lower.endswith(".pdf"):
            docs.extend(PyPDFLoader(path).load())
    return docs


def main():
    docs = load_documents()
    if not docs:
        print(f"No documents found in ./{CORPUS_DIR}. Add .txt/.md/.pdf files and re-run.")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(docs)
    print(f"Loaded {len(docs)} document(s) -> {len(chunks)} chunk(s). Embedding with bge-m3...")

    embeddings = embed_texts([c.page_content for c in chunks])

    rows = [
        {
            "content": c.page_content,
            "title": os.path.basename(c.metadata.get("source", "")) or None,
            "source": c.metadata.get("source"),
            "embedding": emb,
        }
        for c, emb in zip(chunks, embeddings)
    ]

    sb = get_supabase()
    for i in range(0, len(rows), BATCH):
        sb.table("knowledge_documents").insert(rows[i : i + BATCH]).execute()

    print(f"Stored {len(rows)} chunks in knowledge_documents.")


if __name__ == "__main__":
    main()
