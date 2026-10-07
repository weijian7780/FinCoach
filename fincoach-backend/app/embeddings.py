"""bge-m3 embeddings (local). Uses the GPU if available, else CPU.

bge-m3 does NOT need query:/passage: prefixes (unlike the E5 family), so we embed
documents and questions the same way.
"""
from functools import lru_cache

from app.config import EMBEDDING_MODEL


@lru_cache
def _model():
    # Imported lazily so importing this module (e.g. for the API) doesn't block on
    # loading the model until the first embedding is actually needed.
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL, device=device)


def warm_embeddings() -> None:
    """Load the embedding model during API startup, before accepting requests."""
    _model()


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = _model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
