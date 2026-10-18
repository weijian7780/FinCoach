"""General receipt category classifier.

Jev (TypeSafe Choice) is the primary classifier: it maps a receipt to exactly one
of FinCoach's fixed categories by MEANING, not by hardcoded merchant keywords.
When Jev is disabled, times out, errors, or is low-confidence, an optional BGE-M3
semantic fallback runs; if that is off too, the caller keeps its own baseline.

This module never raises into the receipt pipeline: category detection must never
block receipt creation.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from app import config

LOGGER = logging.getLogger("uvicorn.error")

# The app's fixed expense categories, defined semantically so the classifier
# judges by what was bought — never by merchant name. "Others" is the no-match.
CATEGORIES: dict[str, str] = {
    "Food": "Food and drink: restaurants, cafes, coffee shops, kopitiam, mamak, "
            "fast food, bakeries, groceries, supermarkets, beverages, snacks.",
    "Transport": "Getting around: petrol/fuel, tolls, parking, ride-hailing (Grab), "
                 "taxi, bus, train, flights, vehicle and travel costs.",
    "Education": "Learning: tuition, school/college/university fees, textbooks, "
                 "stationery, courses, exam fees.",
    "Entertainment": "Leisure and recreation: cinema, streaming, games, concerts, "
                     "events, hobbies, sports, subscriptions.",
    "Rent": "Housing: rent, rental, deposits, and housing-related utility bills.",
    "Others": "Anything that does not clearly fit the other categories.",
}


def _receipt_text(merchant: str, items: list[dict[str, Any]]) -> str:
    names = [str(item.get("description", "")).strip() for item in items or []]
    names = [name for name in names if name]
    body = ", ".join(names[:20]) if names else "(no itemised lines)"
    return f"Merchant: {merchant or '(unknown)'}. Items: {body}."


def _jev_classify(merchant: str, items: list[dict[str, Any]]) -> tuple[str, float]:
    """Ask Jev for one category. Runs under a hard timeout; may raise."""
    from typesafe_sdk import Choice, TypeSafeClient  # lazy: optional dependency

    state = {
        "merchant": merchant or "",
        "items": [str(item.get("description", "")) for item in (items or [])][:20],
    }
    question = Choice(
        instructions=(
            "Which single expense category best describes this receipt? "
            "Judge by what was bought, not only the merchant name."
        ),
        criteria=dict(CATEGORIES),
    )

    def _run() -> Any:
        kwargs: dict[str, Any] = {"state": state, "questions": {"category": question}}
        if config.TYPESAFE_MODEL:
            kwargs["model"] = config.TYPESAFE_MODEL
        with TypeSafeClient() as client:
            return client.system_one(**kwargs)

    with ThreadPoolExecutor(max_workers=1) as pool:
        response = pool.submit(_run).result(timeout=config.TYPESAFE_TIMEOUT_SECONDS)

    answer = response.choices["category"]
    choice = str(answer.choice)
    confidence = getattr(answer, "confidence", None)
    if confidence is None:
        probabilities = getattr(answer, "probabilities", {}) or {}
        confidence = max(probabilities.values()) if probabilities else 0.0
    return choice, float(confidence)


@lru_cache(maxsize=1)
def _category_vectors() -> tuple[list[str], list[list[float]]]:
    from app.embeddings import embed_texts

    names = list(CATEGORIES)
    vectors = embed_texts([f"{name}: {CATEGORIES[name]}" for name in names])
    return names, vectors


def _embedding_classify(text: str) -> tuple[str, float]:
    """Cosine-match the receipt against category prototypes (normalised vectors)."""
    from app.embeddings import embed_query

    names, vectors = _category_vectors()
    query = embed_query(text)
    sims = [sum(a * b for a, b in zip(query, vector)) for vector in vectors]
    best = max(range(len(names)), key=lambda index: sims[index])
    return names[best], float(sims[best])


def classify_category(
    merchant: str, items: list[dict[str, Any]]
) -> tuple[str, float, str]:
    """Return (category, confidence, source). Never raises.

    source is one of: "jev", "bge-m3", "unavailable".
    """
    if config.TYPESAFE_CATEGORY_ENABLED and config.TYPESAFE_API_KEY:
        try:
            category, confidence = _jev_classify(merchant, items)
            if (
                category in CATEGORIES
                and confidence >= config.TYPESAFE_CATEGORY_MIN_CONFIDENCE
            ):
                return category, confidence, "jev"
            LOGGER.info(
                "receipt category: jev low-confidence (%s @ %.2f), falling back",
                category,
                confidence,
            )
        except Exception as error:  # noqa: BLE001 - never block receipt creation
            LOGGER.warning("receipt category: jev failed (%s), falling back", error)

    if config.RECEIPT_CATEGORY_EMBED_FALLBACK:
        try:
            category, similarity = _embedding_classify(_receipt_text(merchant, items))
            return category, similarity, "bge-m3"
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("receipt category: embedding fallback failed (%s)", error)

    return "", 0.0, "unavailable"
