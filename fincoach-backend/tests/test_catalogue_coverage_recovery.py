from unittest.mock import patch
from app import llm
from app.llm import CoachRequestBudget
from app.rag import research_policy as policy
from app.rag.research_coverage import PartCoverage
from app.rag.retrieval import RetrievedChunk
from tests.test_research_gap_batch import CATALOG


def test_catalogue_recovers_remaining_part_in_second_broader_batch():
    from app.rag.research_gap_batch import PublicQueryResult
    application = RetrievedChunk(-1, 'Application', 'official', None, None,
        'Apply online through the portal.', .8, url='https://example.gov.my/application',
        source_type='web', tier=1, confidence='established')
    fragment = RetrievedChunk(-2, 'Documents', 'official', None, None,
        'Required documents include', .8, url='https://example.gov.my/fragment',
        source_type='web', tier=1, confidence='established')
    documents = RetrievedChunk(-3, 'Documents', 'official', None, None,
        'Provide identification and an income statement.', .8, url='https://example.gov.my/documents',
        source_type='web', tier=1, confidence='established')
    plan = policy.QuestionPlan('Example public assistance', False, True, 'current',
        required_facts=('application', 'documents'), part_tracking=True)
    partial = policy.EvidenceAssessment('partial', missing=('documents',),
        supported_sources=(1,), supported_quotes=((1, application.content),),
        parts=(PartCoverage('p1','confirmed',(1,),complete=True), PartCoverage('p2','missing')))
    def assess(_plan, evidence, **kwargs):
        app_id = next(i for i,c in enumerate(evidence,1) if c.content == application.content)
        doc_id = next((i for i,c in enumerate(evidence,1) if c.content == documents.content), None)
        if doc_id is None:
            from dataclasses import replace
            return replace(partial, supported_sources=(app_id,), supported_quotes=((app_id,application.content),))
        return policy.EvidenceAssessment('sufficient', supported_sources=(app_id,doc_id),
            supported_quotes=((app_id,application.content),(doc_id,documents.content)),
            parts=(PartCoverage('p1','confirmed',(1,),complete=True),PartCoverage('p2','confirmed',(2,),complete=True)))
    batches = [(PublicQueryResult('p2',(fragment,),1,1,None,finished_at=0),),
        (PublicQueryResult('p2',(documents,),1,1,None,finished_at=0),)]
    with patch.object(llm,'monotonic',return_value=0), \
         patch.object(llm,'COACH_REQUEST_DEADLINE_SECONDS',120), \
         patch('app.config.COACH_REQUEST_DEADLINE_SECONDS',120), \
         patch('app.config.COACH_PUBLIC_SOURCE_CACHE_ENABLED',True), \
         patch('app.rag.public_source_store.matching_sources',return_value=CATALOG), \
         patch('app.rag.research_windows.bootstrap_public_sources',return_value=[application]), \
         patch.object(policy,'assess_evidence',side_effect=assess), \
         patch('app.rag.research_gap_batch.research_gap_batch',side_effect=batches) as search:
        result = policy.run_research_policy(plan,[],generate=lambda *a,**kw:None,
            budget=CoachRequestBudget(0,stage_deadline_at=110),api_key='unused',web_enabled=True,
            max_results=4,timeout=4,source_store=object())
    assert search.call_count == 2
    assert search.call_args_list[1].kwargs['discovery_mode'] == 'broader'
    assert [[t.part_id for t in c.args[0]] for c in search.call_args_list] == [['p2'],['p2']]
    assert documents.content in result.source_quotes


def test_two_windows_do_not_replace_missing_part_recovery():
    chunks = [RetrievedChunk(-i, 'Guidance', 'official', None, None,
        'Apply online through the portal.', .8, url=f'https://example.gov.my/{i}',
        source_type='web', tier=1, confidence='sufficient') for i in (1, 2)]
    plan = policy.QuestionPlan('Example public assistance', False, True, 'current',
        entities=('Example',), required_facts=('application', 'documents'), part_tracking=True)
    partial = policy.EvidenceAssessment('partial', missing=('documents',),
        supported_sources=(1,), supported_quotes=((1, chunks[0].content),),
        parts=(PartCoverage('p1', 'confirmed', (1,), complete=True), PartCoverage('p2', 'missing')))
    with patch.object(llm, 'monotonic', return_value=0), \
         patch.object(llm, 'COACH_REQUEST_DEADLINE_SECONDS', 120), \
         patch('app.config.COACH_REQUEST_DEADLINE_SECONDS', 120), \
         patch('app.config.COACH_PUBLIC_SOURCE_CACHE_ENABLED', True), \
         patch('app.rag.public_source_store.matching_sources', return_value=CATALOG), \
         patch('app.rag.research_windows.bootstrap_public_sources', return_value=chunks), \
         patch.object(policy, 'assess_evidence', return_value=partial), \
         patch('app.rag.research_gap_batch.research_gap_batch', return_value=()) as search:
        policy.run_research_policy(plan, [], generate=lambda *a, **kw: None,
            budget=CoachRequestBudget(0, stage_deadline_at=110), api_key='unused',
            web_enabled=True, max_results=4, timeout=4, source_store=object())
    assert search.call_count == 1
    tasks = search.call_args.args[0]
    assert [t.part_id for t in tasks] == ['p2']
