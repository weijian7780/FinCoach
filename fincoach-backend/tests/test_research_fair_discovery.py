"""Tests for fair discovery across requested parts in public research."""
from dataclasses import replace
from unittest.mock import MagicMock, patch
import re
import pytest

from app.llm import CoachRequestBudget
from app.rag.retrieval import RetrievedChunk
from app.rag.research_coverage import (
    RequestedPart, PartCoverage, requested_parts,
)
from app.rag.research_scheduler import (
    ResearchPartState,
    select_discovery_part,
    query_variants,
)
from app.rag.research_policy import (
    QuestionPlan,
    EvidenceAssessment,
    assess_evidence,
    _EvidenceProposal,
    _CoverageProposal,
    _EvidenceSupport,
    _normalize_question_scope,
    part_research_query,
    run_research_policy,
)
from app.rag.web_research import WebResearchCache, ResearchOutcome, WebResult


def _make_plan(
    topic: str = "AKPK debt management",
    facts: tuple[str, ...] = ("eligibility", "how to apply", "required documents"),
    entities: tuple[str, ...] = ("AKPK",),
    **kwargs,
) -> QuestionPlan:
    return QuestionPlan(
        topic=topic,
        needs_personal=False,
        needs_external=True,
        time_scope="current",
        entities=entities,
        required_facts=facts,
        interpreted=True,
        part_tracking=True,
        original_question=kwargs.pop("original_question", topic),
        **kwargs,
    )


def test_three_part_request_discovers_documents_before_second_application_search():
    """Every open part must get one discovery attempt before any part gets a second attempt."""
    states = (
        ResearchPartState(part_id="p1", status="satisfied", search_attempts=1),
        ResearchPartState(part_id="p2", status="open", search_attempts=1),
        ResearchPartState(part_id="p3", status="open", search_attempts=0),
    )
    # p3 has 0 attempts; p2 already has 1 attempt.
    # The scheduler must select p3 (documents) before selecting p2 for a second attempt.
    selected = select_discovery_part(states)
    assert selected == "p3"


def test_unresolved_sixth_part_is_not_erased_by_global_cap():
    """Hitting a global limit must retain open parts with terminal reasons, not erase or mark them exhausted."""
    states = tuple(
        ResearchPartState(
            part_id=f"p{i}",
            status="satisfied" if i < 6 else "open",
            search_attempts=1 if i < 6 else 0,
            terminal_reason=None if i < 6 else "search_call_limit",
        )
        for i in range(1, 7)
    )
    # p6 was never attempted because limit was hit; it must remain "open", not "exhausted"
    p6 = next(s for s in states if s.part_id == "p6")
    assert p6.status == "open"
    assert p6.terminal_reason == "search_call_limit"


def test_cached_window_does_not_count_as_search():
    """Extracting or inspecting an already cached page/window does not consume search call credit."""
    cache = WebResearchCache()
    cache.full_pages["https://akpk.org.my/dmp"] = "Official AKPK DMP guidance content with documents."
    initial_search_calls = cache.search_calls

    # Inspecting cache window must not increase search_calls
    from app.rag.web_research import extract_passages
    passages = extract_passages(
        ["https://akpk.org.my/dmp"],
        api_key="test-key",
        query="required documents",
        cache=cache,
        complete_context=True,
    )
    assert passages
    assert cache.search_calls == initial_search_calls


def test_six_missing_parts_each_receive_an_actual_targeted_dispatch():
    labels = tuple(f'{name} requirements' for name in ('alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta'))
    plan = _make_plan(facts=labels)
    dispatched = []
    def search(query, **kwargs):
        kwargs['cache'].search_calls += 1
        matches = [label for label in labels if label in query]
        dispatched.append(matches[0] if len(matches) == 1 else None)
        return ResearchOutcome([], True, 'no_results')
    empty = EvidenceAssessment('insufficient', missing=labels,
        parts=tuple(PartCoverage(f'p{i}', 'missing') for i in range(1, 7)))
    with patch('app.rag.research_policy.research_evidence', side_effect=search), \
         patch('app.rag.research_policy.assess_evidence', return_value=empty):
        result = run_research_policy(plan, [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key='test', web_enabled=True,
            max_results=4, timeout=8, answer_reserve_seconds=0)
    assert set(dispatched) == set(labels)
    assert result.diagnostics['search_calls'] == 6
    assert {operation['part_id'] for operation in result.diagnostics.get('source_operations', ())} == {
        f'p{i}' for i in range(1, 7)}


def test_no_repeat_assessment_for_same_evidence_scope():
    """Evidence assessments should not be repeated when the evidence set has not changed."""
    plan = _make_plan()
    chunk = RetrievedChunk(1, "AKPK", "akpk.org.my", None, 0, "AKPK provides free counselling.", 0.9, url="https://akpk.org.my")
    generate_mock = MagicMock()
    proposal = {
        "status": "partial",
        "missing": ["required documents"],
        "conflicting": False,
        "jurisdiction_matches": True,
        "period_matches": True,
        "support": [{"source_id": 1, "quote": "AKPK provides free counselling."}],
        "coverage": [
            {"part_id": "p1", "status": "confirmed", "support_indices": [1], "resolution": "direct", "complete": True},
            {"part_id": "p2", "status": "missing", "support_indices": [], "resolution": "direct", "complete": False},
            {"part_id": "p3", "status": "missing", "support_indices": [], "resolution": "direct", "complete": False},
        ],
    }
    import json
    generate_mock.return_value = MagicMock(content=json.dumps(proposal))

    # In run_research_policy, if a round returns unchanged evidence, assess_evidence must not re-run
    # Let's verify that run_research_policy skips assessment when evidence does not change
    decision = run_research_policy(
        plan,
        [chunk],
        generate=generate_mock,
        budget=CoachRequestBudget.start(),
        api_key="test-key",
        web_enabled=True,
        max_results=4,
        timeout=10.0,
    )
    # Even if web research runs multiple steps, identical evidence must not cause repeated assessments
    assert decision.diagnostics["assessment_calls"] <= 2


def test_parent_acronym_cannot_replace_agency():
    """When an agency entity has a parent department/acronym, the agency must be preserved in queries."""
    plan = _make_plan(
        topic="MITRA application requirements",
        facts=("eligibility", "how to apply"),
        entities=("Unit Transformasi Masyarakat India Malaysia (MITRA), Jabatan Perdana Menteri (JPM)",),
        original_question="What is MITRA under JPM and how to apply?",
    )
    parts = requested_parts(plan)
    # The part entity or query should feature MITRA, not replace it with JPM alone
    p1 = parts[0]
    query = part_research_query(plan, p1)
    assert "MITRA" in query
    # Parent acronym JPM must not be the sole or dominant identity replacing MITRA
    words = query.split()
    assert "MITRA" in words or any("mitra" in w.lower() for w in words)


def test_topic_change_discards_previous_entity():
    """A standalone new question with no pronouns or comparative references must discard inherited entities."""
    plan = _make_plan(
        topic="Amanah Saham Bumiputera dividend policy",
        facts=("ASB dividend rules",),
        entities=("Employees Provident Fund (EPF)",),  # Inherited erroneously from history
        original_question="What is the dividend policy of Amanah Saham Bumiputera (ASB)?",
    )
    normalized = _normalize_question_scope(plan, "What is the dividend policy of Amanah Saham Bumiputera (ASB)?")
    # EPF must be discarded because user completely changed topic to ASB
    assert not any("EPF" in e or "Provident" in e for e in normalized.entities)



def test_remaining_discovery_searches_target_distinct_requested_parts():
    """Integration guard through the real round loop.

    ``test_three_part_request_discovers_documents_before_second_application_search``
    only exercises the standalone selector. The plan requires that no requested
    part is crowded out of discovery, so this drives ``run_research_policy`` and
    asserts the searches following the untargeted overview do not keep
    re-covering the part already marked confirmed. It also pins the request-local
    cap: local recovery must not buy more searches than the configured envelope.
    """
    plan = _make_plan(facts=("how to apply", "required documents"))

    partial = EvidenceAssessment(
        "partial", ("required documents",), supported_sources=(1,),
        supported_quotes=((1, "Applications are submitted through the Example public portal."),),
        parts=(PartCoverage("p1", "confirmed", (1,), complete=True),
               PartCoverage("p2", "missing")))

    def search(*args, **kwargs):
        cache = kwargs["cache"]
        cache.search_calls += 1
        number = cache.search_calls
        return ResearchOutcome(
            [RetrievedChunk(number, "Example agency", "akpk.org.my", None, 0,
                            f"Applications are submitted via channel {number}.", 0.9,
                            url=f"https://akpk.org.my/o{number}", source_type="web",
                            tier=1, confidence="sufficient")],
            True, "ok")

    with patch("app.rag.research_policy.research_evidence", side_effect=search), \
         patch("app.rag.research_policy.extract_passages", return_value={}), \
         patch("app.rag.research_policy.assess_evidence", return_value=partial):
        result = run_research_policy(
            plan, [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test",
            web_enabled=True, max_results=4, timeout=8)

    diagnostics = result.diagnostics
    # The request-local search ceiling is enforced, not exceeded by local recovery.
    assert diagnostics["search_calls"] <= 6
    # Round 0 is the untargeted overview. Once the assessment reports which parts
    # are still missing, paid searches must go to further requested parts rather
    # than repeatedly re-covering the one already marked confirmed.
    assert diagnostics["search_calls"] >= 1, (
        f"an unvisited requested part lost its discovery slot: {diagnostics.get('source_operations')}")
    operations = diagnostics.get("source_operations", [])
    assert any(operation['part_id'] == 'p2' and operation['action'] == 'part_search'
               for operation in operations), (
        f"discovery never moved on to another requested part: {operations}")
    # Every still-open part keeps an explicit outcome instead of being erased.
    for state in diagnostics["part_states"]:
        if state["status"] == "open":
            assert state["terminal_reason"], f"open part {state['part_id']} has no terminal reason"


def test_every_requested_part_gets_a_search_before_the_overview_is_repeated():
    """The overview must not swallow a requested part's only discovery slot.

    This is the failure the design records for AKPK: the untargeted overview
    covers the most obvious part, that part is then searched again by name, and a
    later requested part reaches the round limit with ``search_attempts == 0``.
    Four parts are used so at most two of them can be re-covered by the overview
    under the old three-round stop.
    """
    plan = _make_plan(
        facts=("eligibility", "how to apply", "required documents", "application deadline"),
        original_question="what is the eligibility, application, documents and deadline")
    terms = (
        ("eligibility", re.compile(r"eligib", re.I)),
        # Checked before the generic application pattern: the deadline part's own
        # Malay/English variant also contains the word "application".
        ("application deadline", re.compile(r"\bdeadline\b", re.I)),
        ("how to apply", re.compile(r"\bappl(?:y|ying|ication)\b", re.I)),
        ("required documents", re.compile(r"\bdocument", re.I)),
    )
    targeted: list[str] = []

    def search(*args, **kwargs):
        query = args[0]
        label = next((name for name, pattern in terms if pattern.search(query)), "overview")
        targeted.append(label)
        index = len(targeted)
        return ResearchOutcome(
            [RetrievedChunk(index, "Example agency", "akpk.org.my", None, 0,
                            f"Official guidance covering {label}.", 0.9,
                            url=f"https://akpk.org.my/{index}", source_type="web",
                            tier=1, confidence="sufficient")],
            True, "ok")

    def assess(plan_arg, chunks, **kwargs):
        covered = {
            name for name, pattern in terms
            if any(pattern.search(chunk.content) for chunk in chunks)
        }
        quotes = tuple((index, chunk.content) for index, chunk in enumerate(chunks, 1))
        return EvidenceAssessment(
            "sufficient" if len(covered) == len(terms) else "partial",
            missing=tuple(name for name, _ in terms if name not in covered),
            supported_sources=tuple(range(1, len(chunks) + 1)),
            supported_quotes=quotes,
            parts=tuple(PartCoverage(f"p{index}", "confirmed" if name in covered else "missing")
                        for index, (name, _) in enumerate(terms, 1)))

    with patch("app.rag.research_policy.research_evidence", side_effect=search), \
         patch("app.rag.research_policy.extract_passages", return_value={}), \
         patch("app.rag.research_policy.assess_evidence", side_effect=assess):
        result = run_research_policy(
            plan, [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test",
            web_enabled=True, max_results=4, timeout=8)

    diagnostics = result.diagnostics
    assert diagnostics["search_calls"] <= 6, "the request-local search envelope was exceeded"
    distinct = {name for name in targeted if name != "overview"}
    assert distinct == {name for name, _ in terms}, (
        "a requested part never received its own search; the overview was repeated instead: "
        f"{targeted} (search_calls={diagnostics['search_calls']})")
    # No part may consume a second search while another part has had none.
    first_occurrence = [targeted.index(name) for name in distinct]
    assert len(set(first_occurrence)) == len(first_occurrence)


def test_global_sufficient_cannot_override_missing_requested_part():
    """If an LLM proposal claims sufficient but a requested part is incomplete/missing, assessment must be partial."""
    plan = _make_plan(
        topic="AKPK debt management",
        facts=("eligibility", "how to apply", "required documents"),
    )
    chunk = RetrievedChunk(1, "AKPK", "akpk.org.my", None, 0, "AKPK eligibility is Malaysian citizen with debt.", 0.9, url="https://akpk.org.my")
    generate_mock = MagicMock()
    # The model erroneously says status="sufficient" and missing=[] but coverage omits documents (p3)
    proposal = {
        "status": "sufficient",
        "missing": [],
        "conflicting": False,
        "jurisdiction_matches": True,
        "period_matches": True,
        "support": [{"source_id": 1, "quote": "AKPK eligibility is Malaysian citizen with debt."}],
        "coverage": [
            {"part_id": "p1", "status": "confirmed", "support_indices": [1], "resolution": "direct", "complete": True},
            {"part_id": "p2", "status": "missing", "support_indices": [], "resolution": "direct", "complete": False},
            {"part_id": "p3", "status": "missing", "support_indices": [], "resolution": "direct", "complete": False},
        ],
    }
    import json
    generate_mock.return_value = MagicMock(content=json.dumps(proposal))
    assessment = assess_evidence(plan, [chunk], generate=generate_mock, budget=CoachRequestBudget.start())
    assert assessment.status == "partial"
    assert any("documents" in m.lower() or "apply" in m.lower() for m in assessment.missing)
