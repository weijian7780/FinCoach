"""Measure unscored source relevance locally within the search deadline."""
from dataclasses import replace
from math import isfinite, sqrt
from threading import BoundedSemaphore

from app.rag.research_checker_deadline import _within_deadline

_slots = BoundedSemaphore(2)
_SCORE_CHARS = 600


def score_unscored(query, results, timeout):
    positions = [i for i,r in enumerate(results) if r.score is None]
    if not positions or timeout <= 0:
        return results
    def measure():
        from app.embeddings import embed_texts
        vectors = embed_texts([query, *(str(results[i].content or '')[:_SCORE_CHARS] for i in positions)])
        if len(vectors) != len(positions) + 1:
            raise ValueError('invalid_vectors')
        q = vectors[0]
        def cosine(v):
            if not q or len(q) != len(v) or not all(isfinite(x) for x in (*q, *v)):
                raise ValueError('invalid_vectors')
            denominator = sqrt(sum(x*x for x in q)) * sqrt(sum(x*x for x in v))
            if not denominator:
                raise ValueError('invalid_vectors')
            return max(-1.0, min(1.0, sum(a*b for a,b in zip(q,v)) / denominator))
        return [cosine(v) for v in vectors[1:]]
    try:
        scores = _within_deadline(measure, max(2.0, min(4.0, timeout)), _slots, 'embedding')
    except Exception:
        return results
    measured = dict(zip(positions, scores))
    return [replace(r, score=measured[i]) if i in measured else r for i,r in enumerate(results)]
