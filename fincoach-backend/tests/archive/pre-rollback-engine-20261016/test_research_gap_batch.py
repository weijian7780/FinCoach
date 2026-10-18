from dataclasses import replace
from time import sleep
from app.llm import CoachRequestBudget
from app.rag.web_research import ResearchOutcome
from app.rag.retrieval import RetrievedChunk
from app.rag.public_source_store import PublicSourceSpec
import pytest

CATALOG = (PublicSourceSpec('example', ('Example public assistance',), 'Malaysia', '2026',
    ('https://example.gov.my/guidance',)),)


def test_broader_search_preserves_institution_when_last_alias_is_generic(monkeypatch):
    from app.rag import research_gap_batch as batch
    queries = []
    def fetch(query, **kw):
        queries.append(query)
        return ResearchOutcome([], True, 'no_results')
    monkeypatch.setattr(batch, 'research_evidence', fetch)
    catalog = (PublicSourceSpec('education', ('EPF education withdrawal', 'Education Withdrawal'),
        'Malaysia', None, ('https://www.kwsp.gov.my/education',)),)
    batch.research_gap_batch((batch.PublicQueryTask('p1','education','application'),),
        budget=CoachRequestBudget.start(), remaining_searches=1, remaining_extractions=1,
        api_key='unused', catalog=catalog, discovery_mode='broader')
    assert 'EPF' in queries[0]


def test_batch_deduplicates_queries_and_reserves_operation_slots(monkeypatch):
    from app.rag import research_gap_batch as batch
    queries = []
    def fetch(query, **kw):
        queries.append(query)
        kw['cache'].search_calls = kw['cache'].extract_calls = 1
        return ResearchOutcome([RetrievedChunk(-1, 'Guidance', 'official', None, None,
            query, .8, url='https://example.gov.my/' + str(len(query)), source_type='web', tier=1)], True, 'ok')
    monkeypatch.setattr(batch, 'research_evidence', fetch)
    tasks = (batch.PublicQueryTask('p1', 'example', 'application'),
             batch.PublicQueryTask('p2', 'example', 'documents'),
             batch.PublicQueryTask('p3', 'example', 'documents'))
    results = batch.research_gap_batch(tasks, budget=CoachRequestBudget.start(),
        remaining_searches=2, remaining_extractions=2, api_key='unused', catalog=CATALOG)
    assert [r.part_id for r in results] == ['p1', 'p2']
    assert len(queries) == 2 and all(q.startswith('Example public assistance Malaysia 2026 ') for q in queries)
    assert sum(r.search_calls for r in results) == 2
    assert sum(r.extract_calls for r in results) == 2


def test_late_worker_cannot_publish_evidence(monkeypatch):
    from app.rag import research_gap_batch as batch
    def fetch(*args, **kw):
        sleep(.03)
        kw['cache'].full_pages['https://example.gov.my'] = 'late content'
        return ResearchOutcome([], True, 'ok')
    monkeypatch.setattr(batch, 'research_evidence', fetch)
    budget = CoachRequestBudget.start().for_stage(max_seconds=.005)
    result = batch.research_gap_batch((batch.PublicQueryTask('p1', 'example', 'application'),),
        budget=budget, remaining_searches=1, remaining_extractions=1, api_key='unused', catalog=CATALOG)
    sleep(.04)
    assert result == ()


def test_batch_cannot_accept_user_text_as_query_payload(monkeypatch):
    from app.rag import research_gap_batch as batch
    sent = []
    def fetch(query, **kw):
        sent.append(query)
        return ResearchOutcome([], True, 'no_results')
    monkeypatch.setattr(batch, 'research_evidence', fetch)
    with pytest.raises(ValueError):
        batch.PublicQueryTask('p1', 'example', 'STR documents RM5000 user@example.com')
    result = batch.research_gap_batch((batch.PublicQueryTask('p1', 'unknown-private-name', 'documents'),),
        budget=CoachRequestBudget.start(), remaining_searches=1, remaining_extractions=1,
        api_key='unused', catalog=CATALOG)
    assert result == () and sent == []


def test_broader_recovery_uses_same_fixed_query_and_one_call_slot(monkeypatch):
    from app.rag import research_gap_batch as batch
    captured = []
    def fetch(query, **kw):
        captured.append((query, kw['discovery_mode']))
        kw['cache'].search_calls = kw['cache'].extract_calls = 1
        return ResearchOutcome([], True, 'no_results')
    monkeypatch.setattr(batch, 'research_evidence', fetch)
    results = batch.research_gap_batch((batch.PublicQueryTask('p1','example','documents'),),
        budget=CoachRequestBudget.start(), remaining_searches=1, remaining_extractions=1,
        api_key='unused', catalog=CATALOG, discovery_mode='broader')
    assert captured == [('Example public assistance Malaysia 2026 required supporting documents', 'broader')]
    assert sum(r.search_calls for r in results) == 1


def test_fast_evidence_survives_another_worker_reaching_the_deadline(monkeypatch):
    from app.rag import research_gap_batch as batch
    def fetch(query, **kw):
        if 'documents' in query:
            sleep(.04)
        return ResearchOutcome([], True, 'ok')
    monkeypatch.setattr(batch, 'research_evidence', fetch)
    budget = CoachRequestBudget.start().for_stage(max_seconds=.015)
    result = batch.research_gap_batch((batch.PublicQueryTask('p1', 'example', 'application'),
        batch.PublicQueryTask('p2', 'example', 'documents')), budget=budget,
        remaining_searches=2, remaining_extractions=2, api_key='unused', catalog=CATALOG)
    assert [r.part_id for r in result] == ['p1']
