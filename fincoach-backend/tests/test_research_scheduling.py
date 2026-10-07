"""The research path reserves writing/recovery time on one original clock."""
from unittest.mock import patch
import pytest

from app import llm
from app.llm import CoachRequestBudget
from app.rag import research_answer_budget as scheduling


def test_research_then_writer_preserves_full_recovery_path():
    with patch.object(llm, "monotonic", return_value=0), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        total = CoachRequestBudget(0)
        work = scheduling.research_work_budget(total)
        research = scheduling.research_phase_budget(work)
        assert total.remaining_seconds() == 120
        assert work.stage_deadline_at == 110
        assert research.stage_deadline_at == 35
        with patch.object(llm, "monotonic", return_value=35):
            writer = scheduling.initial_writer_budget(work)
            assert writer.remaining_seconds() == 35
            assert work.remaining_seconds() - writer.remaining_seconds() == 40


def test_expired_child_cannot_extend_parent_deadline():
    with patch.object(llm, "monotonic", return_value=40), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        parent = CoachRequestBudget(0, stage_deadline_at=35)
        child = parent.for_stage(max_seconds=15)
        assert child.stage_deadline_at <= parent.stage_deadline_at
        assert child.remaining_seconds() == 0


def test_late_evidence_retains_a_checker_and_does_not_extend_work():
    with patch.object(llm, "monotonic", return_value=90), patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120):
        work = CoachRequestBudget(0, stage_deadline_at=110)
        writer = scheduling.initial_writer_budget(work)
        assert writer is None or writer.stage_deadline_at <= 102


@pytest.mark.parametrize('failure', ['assessment_invalid_json', 'assessment_evidence_rejected'])
def test_schema_repair_does_not_consume_a_substantive_assessment_slot(failure):
    from app.rag import research_policy as policy
    from app.rag.retrieval import RetrievedChunk
    from app.rag.web_research import ResearchOutcome
    source = RetrievedChunk(-1, 'Programme official', 'example.gov.my', None, 0,
        'Programme initial guidance.', .8, url='https://example.gov.my/programme',
        source_type='web', tier=1, confidence='sufficient')
    count = []
    def assess(plan, chunks, **kwargs):
        count.append(len(chunks))
        if len(count) == 1:
            return policy.EvidenceAssessment('insufficient', failure=failure)
        if len(count) < 4:
            return policy.EvidenceAssessment('partial', missing=('documents',))
        return policy.EvidenceAssessment('sufficient', supported_sources=(1,),
            supported_quotes=((1, chunks[0].content),))
    plan = policy.QuestionPlan('Programme', False, True, 'current', required_facts=('documents',))
    with patch.object(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 120), \
         patch.object(llm, 'monotonic', return_value=0), \
         patch.object(policy, 'assess_evidence', side_effect=assess), \
         patch.object(policy, 'research_evidence', return_value=ResearchOutcome([source], True, 'ok')), \
         patch.object(policy, 'extract_passages', return_value={source.url: 'Programme document instructions are now present.'}):
        result = policy.run_research_policy(plan, [source], generate=lambda *a, **k: None,
            budget=CoachRequestBudget(0, stage_deadline_at=110), api_key='test',
            web_enabled=True, max_results=4, timeout=4)
    assert len(count) == 4 and result.assessment.status == 'sufficient'
    assert result.diagnostics['checker_retries'] == 1
