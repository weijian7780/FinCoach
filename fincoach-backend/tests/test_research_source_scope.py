from dataclasses import replace
from unittest.mock import Mock
from app.rag.research_policy import QuestionPlan, assess_evidence
from app.rag.retrieval import RetrievedChunk
from app.rag.research_source_scope import source_workflow_conflicts


def test_existing_facility_documents_cannot_answer_new_programme_application():
    plan = QuestionPlan('Public debt programme', False, True, 'current',
        required_facts=('application steps', 'required documents'), part_tracking=True)
    chunk = RetrievedChunk(-1, 'Add Facility | Public Agency', 'agency', None, None,
        'Upload a credit statement and click Submit.', .8,
        url='https://example.gov.my/add-facility', source_type='web', tier=1, confidence='established')
    unexpected = Mock(return_value=None)
    result = assess_evidence(plan, [chunk], generate=unexpected)
    assert unexpected.call_count == 0
    assert not result.supported_quotes and result.status == 'insufficient'
    assert source_workflow_conflicts(plan, chunk)
    assert not source_workflow_conflicts(replace(plan, topic='How to add a facility to the programme'), chunk)
    assert not source_workflow_conflicts(replace(plan, required_facts=('agency services',)), chunk)


def test_mixed_application_and_appeal_guide_keeps_owned_application_section():
    plan = QuestionPlan('Public assistance', False, True, 'current',
        required_facts=('application steps',), part_tracking=True)
    chunk = RetrievedChunk(-1, 'Application and appeal guide', 'agency', None, None,
        'New applications: Apply through the official portal.', .8)
    assert not source_workflow_conflicts(plan, chunk)
    assert source_workflow_conflicts(plan, replace(chunk, title='Appeal application guide'))
