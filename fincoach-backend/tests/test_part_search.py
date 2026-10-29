"""Each requested part of a question is searched in the knowledge base, a passage
found by several searches fills one slot, and searches without a curated topic keep
the relative margin."""
from app.rag import retrieval, service
from app.rag.query_analysis import SearchSubquery, analyze_knowledge_query
from app.rag.retrieval import RetrievedChunk, _select_hybrid_chunks, select_retrieved_chunks
from test_kb_nonfinance import _plan, _public


def _chunk(chunk_id, source, similarity, text="passage"):
    return RetrievedChunk(chunk_id, source, source, None, chunk_id, text, similarity)


def _definition(topic, **public):
    return _plan(_public(topic, definitional=True, question=f"What is {topic} and what can it do?", **public),
                 f"what is {topic} and what can it do")


# ---- Part searches --------------------------------------------------------------------

def test_reviewer_repro_definition_parts_are_searched_with_their_subject():
    # Live trace: "what is cash flow and what can it do" searched only "cash flow";
    # passages that repeat the term beat the one explaining its purpose.
    plan = _definition("cash flow")
    texts = [s.text for s in service._part_subqueries(plan)]
    assert len(texts) == 2
    assert all(text.startswith("cash flow: ") for text in texts)
    assert any("used for" in text for text in texts)


def test_part_searches_are_plain_searches_never_curated_topic_rules():
    plan = _definition("cash flow")
    assert all(s.topic_id is None and s.source is None for s in service._part_subqueries(plan))


def test_a_label_that_already_names_the_subject_is_searched_as_it_is():
    plan = _plan(_public("cash flow", required_facts=["what cash flow is", "how cash flow differs from profit"]), "q")
    assert [s.text for s in service._part_subqueries(plan)] == [
        "what cash flow is", "how cash flow differs from profit"]


def test_a_single_part_question_adds_no_part_search():
    plan = _plan(_public("cash flow", required_facts=["why cash flow is important"]), "q")
    assert service._part_subqueries(plan) == []


def test_part_searches_follow_the_configured_limit(monkeypatch):
    facts = [f"cash flow fact {n}" for n in range(1, 7)]
    plan = _plan(_public("cash flow", required_facts=facts), "q")
    assert len(service._part_subqueries(plan)) == service.RETRIEVE_PART_SEARCHES
    monkeypatch.setattr(service, "RETRIEVE_PART_SEARCHES", 2)
    assert len(service._part_subqueries(plan)) == 2
    monkeypatch.setattr(service, "RETRIEVE_PART_SEARCHES", 0)
    assert service._part_subqueries(plan) == []  # setting 0 turns part searches off


def test_part_searches_follow_topic_and_subject_searches_without_repeats():
    plan = _plan(_public("EPF", entities=["EPF"], definitional=True, question="What is EPF?"), "q")
    base = analyze_knowledge_query(plan.topic)
    analysis = service._plan_retrieval_analysis(plan, base)
    assert analysis.subqueries[:len(base.subqueries)] == base.subqueries
    texts = [" ".join(s.text.casefold().split()) for s in analysis.subqueries]
    assert len(texts) == len(set(texts))
    assert any(text.startswith("epf: ") for text in texts)


def test_no_part_searches_when_the_topic_has_no_search():
    empty = analyze_knowledge_query("")
    assert service._plan_retrieval_analysis(_definition("cash flow"), empty) is empty


def test_remaining_parts_are_still_searched_by_their_facts(monkeypatch):
    seen = {}

    def fake_retrieve(question, *, analysis, title_sources):
        seen["texts"] = [s.text for s in analysis.subqueries]
        return []

    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    plan = _plan(_public("cash flow", required_facts=["what cash flow is", "how cash flow differs from profit"]), "q")
    service._retrieve_remaining_parts(plan, [], ())
    texts = [" ".join(t.casefold().split()) for t in seen["texts"]]
    assert "how cash flow differs from profit" in texts
    assert len(texts) == len(set(texts))


# ---- Selection ------------------------------------------------------------------------

def test_a_passage_found_by_several_searches_fills_one_slot():
    chunks = [_chunk(1, "wiki", 0.70), _chunk(1, "wiki", 0.68), _chunk(2, "chase", 0.67), _chunk(3, "wiki", 0.66)]
    selected = select_retrieved_chunks(chunks, k=3, threshold=0.45, score_margin=0.10)
    assert [c.id for c in selected] == [1, 2, 3]
    assert selected[0].similarity == 0.70  # its best similarity


def test_the_relative_margin_still_applies_after_removing_repeats():
    chunks = [_chunk(1, "a", 0.70), _chunk(1, "a", 0.69), _chunk(2, "b", 0.55)]
    assert [c.id for c in select_retrieved_chunks(chunks, k=3, threshold=0.45, score_margin=0.10)] == [1]


def test_reviewer_repro_part_search_brings_the_purpose_passage(monkeypatch):
    # The topic search returns three passages from one page; the part search
    # finds the passage that says what the subject is used for.
    topic = SearchSubquery(None, None, "cash flow")
    part = SearchSubquery(None, None, "cash flow: what it does and what it is used for (purpose)")
    found = {
        topic.text: [_chunk(194, "wiki", 0.696), _chunk(189, "wiki", 0.678), _chunk(193, "wiki", 0.670)],
        part.text: [_chunk(193, "wiki", 0.711), _chunk(197, "chase", 0.700), _chunk(194, "wiki", 0.690)],
    }
    monkeypatch.setattr(retrieval, "embed_texts", lambda texts: [[0.0] for _ in texts])
    monkeypatch.setattr(retrieval, "_hybrid_candidates", lambda subquery, embedding, count: found[subquery.text])
    base = analyze_knowledge_query("cash flow")
    only_topic = retrieval.retrieve("cash flow", analysis=base.__class__(
        base.original, base.normalized, base.topic_matches, (topic,)))
    with_part = retrieval.retrieve("cash flow", analysis=base.__class__(
        base.original, base.normalized, base.topic_matches, (topic, part)))
    assert "chase" not in [c.source for c in only_topic]
    assert [c.id for c in with_part] == [193, 197, 194]


def test_untopiced_searches_keep_the_margin_beside_a_curated_topic():
    curated = SearchSubquery("epf", "epf.md", "EPF KWSP Employees Provident Fund")
    part = SearchSubquery(None, None, "EPF: what it does and what it is used for (purpose)")
    per = [
        (curated, [_chunk(91, "epf.md", 0.637)]),
        (part, [_chunk(91, "epf.md", 0.60), _chunk(172, "finance.md", 0.472), _chunk(87, "budget.md", 0.458)]),
    ]
    selected = _select_hybrid_chunks(per, k=3, threshold=0.45, score_margin=0.10)
    assert [c.id for c in selected] == [91]


def test_untopiced_passage_within_the_margin_still_fills_a_slot():
    curated = SearchSubquery("epf", "epf.md", "EPF KWSP Employees Provident Fund")
    part = SearchSubquery(None, None, "EPF: what it is used for")
    per = [(curated, [_chunk(91, "epf.md", 0.637)]), (part, [_chunk(95, "epf-guide.md", 0.60)])]
    assert [c.id for c in _select_hybrid_chunks(per, k=3, threshold=0.45, score_margin=0.10)] == [91, 95]
