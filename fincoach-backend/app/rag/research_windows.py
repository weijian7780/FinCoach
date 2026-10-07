"""Independent contiguous public evidence windows for each requested part."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from dataclasses import replace
from typing import TYPE_CHECKING

from app.rag.public_source_store import PublicSourcePage, PublicSourceSpec, PublicSourceStore, load_catalog, matching_sources
from app.rag.retrieval import RetrievedChunk

if TYPE_CHECKING:
    from app.rag.research_policy import QuestionPlan
    from app.rag.web_research import WebResearchCache
    from app.llm import CoachRequestBudget


def select_part_windows(pages: tuple[PublicSourcePage, ...], plan: QuestionPlan, *,
                        max_windows: int = 6, max_chars: int = 1800) -> list[RetrievedChunk]:
    from app.rag.research_policy import part_research_query, _research_subject
    from app.rag.research_coverage import researchable_parts
    from app.rag.web_research import _complete_page_window, classify_tier, tier_to_confidence
    # Round-robin requested parts, then source alternatives. URL alone must not
    # discard a document list because instructions from that PDF came first.
    result, seen = [], set()
    if max_windows <= 0 or max_chars <= 0:
        return []
    for page in pages[:6]:
        for part in researchable_parts(plan):
            text = _complete_page_window(page.content, part_research_query(plan, part),
                                         subject_query=_research_subject(plan))[:min(1800, max_chars)]
            key = (page.url, text)
            tier = classify_tier(page.url)
            if not text or key in seen or tier not in {1, 2, 3, 4}:
                continue
            seen.add(key)
            identity = sha256((page.url + page.content_sha256 + text).encode()).hexdigest()
            result.append(RetrievedChunk(-len(result)-1, page.title, page.url.split('/')[2], None, len(result),
                text, .8, url=page.url, source_type="web", tier=tier, confidence=tier_to_confidence(tier),
                published_date=page.published_date, checked_at=page.fetched_at.date().isoformat(),
                evidence_window_id=identity))
            if len(result) >= min(6, max_windows):
                return result
    return result


def bootstrap_public_sources(plan: QuestionPlan, *, store: PublicSourceStore,
        catalog: tuple[PublicSourceSpec, ...], cache: WebResearchCache, budget: CoachRequestBudget,
        api_key: str, timeout: float, reserve_after_seconds: float) -> list[RetrievedChunk]:
    from app.rag.web_research import extract_passages
    from app.rag.research_policy import research_query
    specs = matching_sources(plan, catalog)
    diagnostics = cache.public_source_diagnostics
    diagnostics.update(catalogue_match=bool(specs), cache_pages_used=0,
                       cache_pages_refreshed=0, direct_extract_calls=0, source_window_count=0)
    # Explicit fresh searches and bank comparisons always use live discovery.
    comparison = any(word in plan.topic.casefold() for word in ("compare", "comparison", "best bank", "interest rate"))
    import re
    fresh_intent = plan.explicit_search or bool(re.search(
        r"\b(?:latest|today|right now|updated|changed recently)\b", plan.original_question, re.I))
    if comparison:
        return []
    now = datetime.now(timezone.utc)
    urls = list(dict.fromkeys(url for spec in specs for url in spec.urls))[:4]
    periods = {url: spec.period for spec in specs for url in spec.urls}
    pages = {}
    for url in urls:
        page = None if fresh_intent else store.get(url, now=now)
        period = plan.period or (str(now.year) if plan.time_scope == "current" else None)
        if page and (not period or not page.declared_period or page.declared_period == period):
            pages[url] = page
    # Intent words such as "general role and functions" are not the subject's
    # identity. Find cached pages by the explicit public entities, then assess
    # their relevance to the actual question rather than automatically approving.
    cache_plan = replace(plan, topic=" ".join(plan.entities)) if plan.entities else plan
    for page in (() if fresh_intent else store.find(cache_plan, now=now)):
        if len(pages) < 4:
            pages.setdefault(page.url, page)
    diagnostics["cache_pages_used"] = len(pages)
    missing = [url for url in urls if url not in pages]
    allowance = min(timeout, budget.remaining_seconds() - reserve_after_seconds - 1)
    if missing and api_key and cache.extract_calls < 4 and allowance >= 1:
        before = cache.extract_calls
        extract_passages(missing, api_key=api_key, query=research_query(plan), timeout=allowance,
                         cache=cache, complete_context=True, subject_query=plan.topic)
        diagnostics["direct_extract_calls"] = cache.extract_calls - before
        for url in missing:
            page = cache.fetched_pages.get(url)
            if page:
                page = replace(page, declared_period=periods.get(url))
                pages[url] = page
                cache.fetched_pages[url] = page
                store.put(page)
                diagnostics["cache_pages_refreshed"] += 1
    for page in pages.values():
        if len(cache.full_pages) < 6:
            cache.full_pages[page.url] = page.content
    windows = select_part_windows(tuple(pages.values()), plan)
    diagnostics["source_window_count"] = len(windows)
    return windows
