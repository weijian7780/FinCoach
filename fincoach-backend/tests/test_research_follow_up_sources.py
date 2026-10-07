"""Research uses safe, unambiguous part queries and keeps factual coverage honest."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json
from app.llm import CoachRequestBudget, AgentLLMResult
from app.rag import research_policy as p, service
from app.rag.research_coverage import PartCoverage
from app.rag.retrieval import RetrievedChunk


def plan():
    return p.QuestionPlan('ICU JPM', False, True, 'stable', entities=('ICU JPM',),
        required_facts=('main duties', 'application procedure'), part_tracking=True,
        clarification='Which programme would you like to apply for?',
        clarification_facts=('application procedure',))


def test_duties_query_does_not_search_programme_application():
    assert 'application' not in p.research_query(plan()).lower()


def test_agency_role_queries_use_identity_and_one_intent_not_schema_labels():
    value = replace(plan(), topic='Implementation Coordination Unit general role and functions',
                    entities=('Implementation Coordination Unit',),
                    required_facts=('main role and functions of the institution',),
                    clarification=None, clarification_facts=())
    query = p.research_query(value)
    assert 'institution' not in query and 'general' not in query
    assert len(query.split()) <= 9
    targeted = p.part_research_query(value, p.requested_parts(value)[0])
    assert targeted != query
    assert 'fungsi' in targeted
    historical = replace(value, time_scope='historical', period='2023')
    assert '2023' in p.research_query(historical)
    assert '2023' in p.part_research_query(historical, p.requested_parts(historical)[0])


def test_observed_official_public_navigation_and_document_links_are_reachable():
    from app.rag.web_research import is_public_guidance_url, linked_guidance_urls
    target = 'https://example.gov.my/pg/main.php?pg=profil&list=fungsi'
    assert is_public_guidance_url(target)
    assert is_public_guidance_url('https://example.gov.my/pg/get_dl.php?id=4837')
    assert linked_guidance_urls('https://example.gov.my', f'[Agency functions]({target})',
        subject_query='Agency', part_label='functions', visited=frozenset()) == (target,)
    for unsafe in ('https://example.gov.my/account?id=4837',
                   'https://example.gov.my/pg/main.php?pg=profil&token=secret',
                   'https://example.gov.my/pg/get_dl.php?id=private',
                   'https://example.gov.my/main.php?pg=account&id=12345678',
                   'https://maybank2u.com.my/main.php?pg=account&id=12345678',
                   'https://versa.com.my/get_dl.php?id=12345678',
                   'https://unknown.example/pg/get_dl.php?id=4837'):
        assert not is_public_guidance_url(unsafe)


def test_role_window_selects_duties_section_over_navigation_footer():
    from app.rag.web_research import _complete_page_window
    raw = ('# Agency\n\n' + 'Unrelated background. ' * 120 +
           '\n\n## Fungsi\n\nAgency monitors government projects and coordinates implementation.\n\n' +
           'Archive navigation. ' * 120 + '\n\n## Footer\n\nAgency functions role institution Malaysia links.')
    text = _complete_page_window(raw, 'Agency fungsi Malaysia', subject_query='Agency')
    assert 'monitors government projects' in text


def test_blocked_part_cannot_be_confirmed_by_assessor():
    text = 'The agency coordinates the implementation of government development projects.'
    source = RetrievedChunk(1,'Agency duties','official',None,0,text,.8,
        url='https://agency.gov.my/duties',source_type='web',tier=1)
    payload = dict(status='sufficient', missing=[], conflicting=False,
        jurisdiction_matches=True,period_matches=True,support=[dict(source_id=1,quote=text)],
        coverage=[dict(part_id=f'p{i}',status='confirmed',support_indices=[1],
                       resolution='direct',complete=True) for i in (1,2)])
    result=p.assess_evidence(plan(),[source],generate=lambda *a,**k:SimpleNamespace(content=json.dumps(payload)),
        budget=CoachRequestBudget.start())
    assert result.parts[0].complete
    assert not result.parts[1].complete
    assert result.status == 'partial'


def test_resolved_part_does_not_buy_search_for_ambiguous_programme():
    value=plan()
    text='The agency coordinates the implementation of government development projects.'
    source=RetrievedChunk(1,'Agency','official',None,0,text,.8,
        url='https://agency.gov.my/duties',source_type='web',tier=1)
    assessment=p.EvidenceAssessment('partial',('application procedure',),supported_sources=(1,),
        supported_quotes=((1,text),),parts=(PartCoverage('p1','confirmed',(1,),complete=True),PartCoverage('p2','missing')))
    with patch.object(p,'assess_evidence',return_value=assessment), patch.object(p,'research_evidence') as search:
        result=p.run_research_policy(value,[source],generate=MagicMock(),budget=CoachRequestBudget.start(),
            api_key='test',web_enabled=True,max_results=4,timeout=8)
    search.assert_not_called()
    assert result.assessment.supported_quotes
    assert result.diagnostics['clarification_part_ids']==['p2']


def test_mixed_question_reaches_research_service():
    repo=MagicMock(user_id='public-test'); repo.require_session.return_value={'id':'s','title':'Existing'}
    repo.find_user_message.return_value=None; repo.list_messages.return_value=[]
    repo.complete_turn.side_effect=lambda **kw:kw['assistant_payload']
    decision=p.ResearchDecision([],p.EvidenceAssessment('insufficient'))
    with patch.object(service,'COACH_RESEARCH_POLICY_ENABLED',True), \
         patch.object(service,'interpret_question',return_value=plan()), \
         patch.object(service,'retrieve',return_value=[]) as retrieval, \
         patch.object(service,'run_research_policy',return_value=decision) as research:
        reply=service.CoachingService(repo,MagicMock()).send_message('s','m','confirm duties or application for ICU JPM')
    assert research.call_count==1
    assert retrieval.call_count==1
    context=reply['assistant_message']['ui_payload']['research_context']
    assert context['clarification_facts']==['application procedure']
    assert context['required_facts']==['main duties','application procedure']


def test_private_history_not_sent_to_search_context():
    captured=[]
    history=[{'role':'assistant','content':'private balance RM99999', 'ui_payload':{'research_context':
        {'topic':'ICU JPM','required_facts':['main duties','application procedure'],
         'clarification_facts':['application procedure'],'clarification':'Which programme?'}}}]
    def generate(prompt,**kwargs):
        captured.append(prompt)
        raise TimeoutError
    p.interpret_question('SejaTi MADANI',history,base_personal=False,base_external=True,generate=generate)
    assert 'application procedure' in captured[0]
    assert 'RM99999' not in captured[0]


def test_fresh_agency_page_reused_without_search_or_extract(tmp_path):
    from datetime import datetime, timezone
    from hashlib import sha256
    from app.rag.public_source_store import PublicSourceStore, PublicSourcePage
    from app.rag.research_windows import bootstrap_public_sources
    from app.rag.web_research import WebResearchCache
    store=PublicSourceStore(tmp_path)
    content='ICU JPM coordinates implementation of government development projects.'
    page=PublicSourcePage('https://agency.gov.my/duties','ICU JPM',content,
        datetime.now(timezone.utc),sha256(content.encode()).hexdigest())
    assert store.put(page)
    value=replace(plan(),topic='ICU JPM general role and functions')
    with patch('app.rag.web_research.extract_passages',side_effect=AssertionError('Fresh page should be reused')):
        chunks=bootstrap_public_sources(value,store=store,catalog=(),cache=WebResearchCache(),
            budget=CoachRequestBudget.start(),api_key='test',timeout=8,reserve_after_seconds=30)
    assert chunks and chunks[0].url==page.url


def test_verifier_and_coverage_do_not_search_after_full_clarification():
    value=replace(plan(),clarification_facts=('main duties','application procedure'))
    with patch.object(p,'assess_evidence') as assess, patch.object(p,'research_evidence') as search:
        result=p.run_research_policy(value,[],generate=MagicMock(),budget=CoachRequestBudget.start(),
            api_key='test',web_enabled=True,max_results=4,timeout=8)
    assess.assert_not_called(); search.assert_not_called()
    assert result.failure=='clarification_required'


def test_window_boundary_partial_word_cannot_crash_source_extraction():
    from app.rag.web_research import _complete_page_window
    # A bounded literal slice ends midway through functionality. That boundary
    # creates a window token absent from the original full-page frequency table.
    raw='background '*162+'paddingxx '+'functionality explains the role.'+' other '*100
    result=_complete_page_window(raw,'function')
    assert result and result in raw
