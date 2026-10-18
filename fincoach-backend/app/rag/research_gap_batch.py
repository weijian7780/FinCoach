"""Parallel discovery restricted to public catalog names and fixed search terms.

No raw question, LLM-generated query, user identifier or financial field is
accepted by this boundary. Programme selection never enters the search payload.
"""
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from urllib.parse import urlparse
from app.llm import CoachRequestBudget
from app import llm as clock
from app.rag.public_source_store import PublicSourceSpec
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import WebResearchCache, research_evidence, _safe_error

_TERMS = {
    'application': 'application steps',
    'documents': 'required supporting documents',
    'eligibility': 'eligibility requirements',
    'general': 'official programme guidance',
}


@dataclass(frozen=True)
class PublicQueryTask:
    part_id: str
    programme_id: str
    kind: str

    def __post_init__(self):
        if self.kind not in _TERMS:
            raise ValueError('Only fixed public research categories are accepted.')


@dataclass(frozen=True)
class PublicQueryResult:
    part_id: str
    chunks: tuple[RetrievedChunk, ...]
    search_calls: int
    extract_calls: int
    failure: str | None
    full_pages: tuple[tuple[str, str], ...] = ()
    fetched_pages: tuple = ()
    credits: float | None = None
    finished_at: float = 0


def research_gap_batch(tasks: tuple[PublicQueryTask, ...], *, budget: CoachRequestBudget,
    remaining_searches: int, remaining_extractions: int, api_key: str,
    catalog: tuple[PublicSourceSpec, ...], discovery_mode: str = 'institution') -> tuple[PublicQueryResult, ...]:
    if discovery_mode not in {'institution', 'broader'}:
        raise ValueError('Unknown public discovery mode')
    specs = {s.programme_id: s for s in catalog}
    admitted, seen = [], set()
    for task in tasks:
        spec = specs.get(task.programme_id)
        if spec is None or not spec.aliases:
            continue
        key = (spec.programme_id, task.kind)
        if key in seen:
            continue
        seen.add(key)
        if len(admitted) >= max(0, min(3, remaining_searches, remaining_extractions)):
            break
        admitted.append((task, spec))
    if not admitted or budget.remaining_seconds() <= 0:
        return ()

    def worker(task, spec):
        cache = WebResearchCache(max_search_calls=1, max_extract_calls=1)
        # Every string sent to Tavily comes from checked-in public metadata or
        # this fixed vocabulary, not from the question or conversation.
        # Preserve the identifying alias when the final alias is generic (for
        # example "Education Withdrawal"). Broader search drops host limits,
        # so losing the institution here changes the subject of the question.
        subject = spec.aliases[0]
        if spec.aliases[-1].casefold() not in subject.casefold():
            subject += ' ' + spec.aliases[-1]
        query = ' '.join(p for p in (subject, spec.jurisdiction,
            spec.period or '', _TERMS[task.kind]) if p)
        domains = tuple(dict.fromkeys(urlparse(u).hostname for u in spec.urls if urlparse(u).hostname))
        try:
            outcome = research_evidence(query, api_key=api_key, max_results=4,
                timeout=budget.timeout_for('research'), single_search=True,
                public_policy=True, official_domains=domains,
                cache=cache, subject_query=spec.aliases[-1], discovery_mode=discovery_mode)
            failure = outcome.reason if outcome.reason != 'ok' else outcome.extraction_reason
            return PublicQueryResult(task.part_id, tuple(outcome.chunks), cache.search_calls,
                cache.extract_calls, failure, tuple(cache.full_pages.items()),
                tuple(cache.fetched_pages.items()), cache.credits, clock.monotonic())
        except Exception as error:
            return PublicQueryResult(task.part_id, (), cache.search_calls, cache.extract_calls,
                _safe_error(error), finished_at=clock.monotonic())

    pool = ThreadPoolExecutor(max_workers=min(2, len(admitted)), thread_name_prefix='public-research')
    futures = [pool.submit(worker, task, spec) for task, spec in admitted]
    try:
        done, _ = wait(futures, timeout=budget.remaining_seconds())
        deadline = min(budget.stage_deadline_at or float('inf'),
            budget.started_at + clock.COACH_REQUEST_DEADLINE_SECONDS)
        return tuple(r for f in futures if f in done for r in (f.result(),) if r.finished_at <= deadline)
    finally:
        # Late work owns only private request caches; it cannot publish evidence.
        pool.shutdown(wait=False, cancel_futures=True)
