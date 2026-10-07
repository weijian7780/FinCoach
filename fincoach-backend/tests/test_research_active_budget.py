"""Active-service budget tests ensuring absolute bounds and stage margins.

These drive the real budget helpers and the real ``run_research_policy`` with a
fake clock. Only the external transports (model generation, Tavily search and
extraction) are stubbed, so a reservation bug in the production path fails here.
"""
import ast
from pathlib import Path
from unittest.mock import patch

from app import llm
from app.llm import CoachRequestBudget
from app.rag import research_answer_budget as scheduling
from app.rag import research_policy as policy
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import ResearchOutcome


def test_model_work_stops_at_115():
    with patch.object(llm, "monotonic", return_value=0), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        assert work.started_at == 0
        assert work.stage_deadline_at == 115
        assert work.remaining_seconds() == 115


def test_service_research_stops_at_absolute_second_75():
    # Even if interpretation finishes at second 15 or second 5, research stops at second 75
    with patch.object(llm, "monotonic", return_value=15), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        research = scheduling.research_phase_budget(work)
        assert research.started_at == 0
        assert research.stage_deadline_at == 75
        assert research.remaining_seconds() == 60

    with patch.object(llm, "monotonic", return_value=5), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        research = scheduling.research_phase_budget(work)
        assert research.started_at == 0
        assert research.stage_deadline_at == 75
        assert research.remaining_seconds() == 70


def test_writer_at_75_retains_check_and_ten_second_correction():
    # At research second 75, work has 40s remaining (until 115).
    # Allocation: 20s writer + 5s check + 10s correction + 5s check = 40s.
    with patch.object(llm, "monotonic", return_value=75), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        writer = scheduling.initial_writer_budget(work)
        assert writer is not None
        assert writer.stage_deadline_at == 95  # 75 + 20
        assert writer.remaining_seconds() == 20

    # At second 95 (writer finishes), first check takes 5s -> second 100.
    # At second 100, correction gets 10s and leaves 5s for final check.
    with patch.object(llm, "monotonic", return_value=100), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        correction = scheduling.correction_budget(work)
        assert correction is not None
        assert correction.stage_deadline_at == 110  # 100 + 10
        assert correction.remaining_seconds() == 10


def test_fast_research_allows_fifteen_second_correction():
    # Research finishes early at second 40.
    # Writer runs for 20s (until 60), check runs for 5s (until 65).
    # At second 65, work has 50s left (until 115).
    # Correction can use the full 15 seconds!
    with patch.object(llm, "monotonic", return_value=65), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        correction = scheduling.correction_budget(work)
        assert correction is not None
        assert correction.stage_deadline_at == 80  # 65 + 15
        assert correction.remaining_seconds() == 15


def test_provider_retry_cannot_reset_stage_clock():
    # Child stage cannot reset or extend deadline when retrying.
    with patch.object(llm, "monotonic", return_value=0), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        stage = total.for_stage(max_seconds=15, stage_name="answer_recovery")
        assert stage.stage_deadline_at == 15

    # 10 seconds later, same stage budget has only 5s remaining
    with patch.object(llm, "monotonic", return_value=10), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        assert stage.remaining_seconds() == 5
        # Attempting to allocate another child cannot exceed stage deadline
        retry_child = stage.for_stage(max_seconds=15)
        assert retry_child.stage_deadline_at <= stage.stage_deadline_at
        assert retry_child.remaining_seconds() == 5


def _web_source(url: str = "https://example.gov.my/programme", content: str = "Programme initial guidance."):
    return RetrievedChunk(-1, "Programme official", "example.gov.my", None, 0, content, .8,
                          url=url, source_type="web", tier=1, confidence="sufficient")


def _search_plan():
    # part_tracking is off: this is the overview path, matching the active
    # service call for an interpreted plan.
    return policy.QuestionPlan("Programme", False, True, "current", required_facts=("documents",))


def _service_and_phase_budgets(clock):
    """Reproduce exactly what the active service builds before the policy call."""
    total = CoachRequestBudget(0)
    work = scheduling.research_work_budget(total)
    research = scheduling.research_phase_budget(work)
    return work, research


def test_research_child_does_not_reserve_writer_time_twice():
    """At second 60 the research child still owns 15 seconds of real work.

    The stage-derived answer reserve is 40s on a 120s request. A second
    subtraction inside ``run_research_policy`` would exceed the 15s still left
    and stop research at second 60. The active service therefore passes an
    explicit 0.0, and the real policy must actually spend the remaining time on
    discovery instead of idling for a writer that already has its own budget.
    """
    source = _web_source()
    searched = []

    def fake_search(query, **kwargs):
        searched.append(query)
        return ResearchOutcome([source], True, "ok")

    plan = _search_plan()
    with patch.object(llm, "monotonic", return_value=60), \
         patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120), \
         patch.object(policy, "research_evidence", side_effect=fake_search), \
         patch.object(policy, "assess_evidence", return_value=policy.EvidenceAssessment(
             "sufficient", supported_sources=(1,), supported_quotes=((1, source.content),))), \
         patch.object(policy, "extract_passages", return_value={}):
        _work, research = _service_and_phase_budgets(60)
        assert research.remaining_seconds() == 15
        policy.run_research_policy(plan, [source], generate=lambda *a, **k: None,
                                   budget=research, api_key="test", web_enabled=True,
                                   max_results=4, timeout=4, answer_reserve_seconds=0.0)

    assert searched, "research must still be allowed to discover at second 60"


def test_stage_derived_reserve_would_have_stopped_research_at_60():
    """Regression guard for the duplicate-reservation defect, stated positively.

    The same call without the explicit 0.0 keeps the legacy stage-derived
    reserve. Before any evidence is validated that reserve is
    ``min(20, deadline/3)`` = 20s, and once evidence is validated it becomes
    ``min(COACH_RESEARCH_ANSWER_RESERVE_SECONDS, deadline/2)`` = 40s. Either way
    it is larger than the 15s the research child still owns at second 60, so the
    legacy path stops before spending a paid search. That is exactly why the
    active service must pass an explicit 0.0.
    """
    source = _web_source()
    searched = []

    def fake_search(query, **kwargs):
        searched.append(query)
        return ResearchOutcome([source], True, "ok")

    plan = _search_plan()
    with patch.object(llm, "monotonic", return_value=60), \
         patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120), \
         patch.object(policy, "research_evidence", side_effect=fake_search), \
         patch.object(policy, "assess_evidence", return_value=policy.EvidenceAssessment(
             "sufficient", supported_sources=(1,), supported_quotes=((1, source.content),))), \
         patch.object(policy, "extract_passages", return_value={}):
        _work, research = _service_and_phase_budgets(60)
        # The pre-evidence reserve alone exceeds the research child's 15s.
        assert llm.research_answer_reserve_seconds(has_evidence=False) == 20
        assert research.remaining_seconds() == 15
        result = policy.run_research_policy(plan, [source], generate=lambda *a, **k: None,
                                            budget=research, api_key="test", web_enabled=True,
                                            max_results=4, timeout=4)

    assert not searched, "a 20s reserve cannot fit in the 15s the research child leaves"
    assert result.failure == "search_deadline"


def test_explicit_zero_reserve_is_not_replaced_by_default():
    """Explicit zero is a value, never a missing argument."""
    import inspect
    parameter = inspect.signature(policy.run_research_policy).parameters["answer_reserve_seconds"]
    assert parameter.default is None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_active_service_call_site_passes_explicit_zero_reserve():
    """The production call site must bind 0.0, not rely on legacy defaults."""
    source = Path(policy.__file__).with_name("service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", None)
        if name == "run_research_policy":
            matches.append(node)
    assert matches, "the active service must call run_research_policy"
    for call in matches:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert "answer_reserve_seconds" in keywords, (
            "run_research_policy call site must explicitly own its answer reserve")
        value = keywords["answer_reserve_seconds"]
        assert isinstance(value, ast.Constant) and value.value == 0.0, (
            "the active service must pass an explicit 0.0 after creating the research child")
