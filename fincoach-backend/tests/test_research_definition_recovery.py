"""Definitions require relevant evidence, full public identities and honest cards."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json
import pytest

from app.llm import CoachRequestBudget, AgentLLMResult
from app.rag import research_policy as p, service
from app.rag.research_coverage import PartCoverage
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import ResearchOutcome


IDENTITY = 'The Example Coordination Unit (ECU PMD) is a government agency.'
PURPOSE = 'ECU PMD coordinates and monitors government development projects.'
TEXT = IDENTITY + ' ' + PURPOSE


def test_stalled_identity_search_does_not_broaden_untried_purpose_search():
    modes = []
    assessment = p.EvidenceAssessment('partial', p._DEFINITIONAL_FACTS,
        supported_sources=(1,), supported_quotes=((1,TEXT),),
        parts=(PartCoverage('p1','missing'), PartCoverage('p2','missing')))
    def search(*args, **kwargs):
        modes.append(kwargs.get('discovery_mode', 'institution'))
        return ResearchOutcome([], True, 'no_results')
    run(definition(), [chunk(web=True)], lambda *a,**k: assessment, search)
    assert modes[:3] == ['institution', 'institution', 'institution']


def test_extracted_footer_cannot_replace_substantive_search_evidence():
    from app.rag import web_research as web
    result = web.WebResult('ECU PMD', 'https://ecu.gov.my/profile', TEXT, .8)
    with patch.object(web, 'search_web', return_value=[result]), \
         patch.object(web, 'extract_passages', return_value={result.url: 'Copyright ECU PMD. Site disclaimer.'}):
        outcome = web.research_evidence('ECU PMD full name', api_key='test', public_policy=True)
    assert TEXT in outcome.chunks[0].content
    assert outcome.chunks[0].url == result.url


def test_agency_search_does_not_add_an_inferred_parent_as_a_second_subject():
    plan = definition(entities=('ECU PMD', 'Prime Ministers Department'))
    for query in (p.research_query(plan), *(p.part_research_query(plan, part) for part in p.requested_parts(plan))):
        assert 'ECU' in query and 'PMD' in query
        assert 'Prime Ministers Department' not in query
    multiple = definition(entities=('ECU PMD', 'BNM'), original_question='what are ECU PMD and BNM')
    assert 'BNM' in p.research_query(multiple)
    assert p._discovery_domains(plan, [chunk(web=True)]) == ('ecu.gov.my',)


def test_official_domain_search_does_not_also_apply_country_reranking():
    from app.rag.web_research import _search_pass
    client = MagicMock()
    client.search.return_value = {'results': []}
    _search_pass(client, 'ECU PMD fungsi', caged=True, max_results=4, timeout=3,
                 public_policy=True, official_domains=('ecu.gov.my',))
    options = client.search.call_args.kwargs
    assert options['include_domains'] == ['ecu.gov.my']
    assert options['include_domains_mode'] == 'restrict'
    assert 'country' not in options
    _search_pass(client, 'ECU PMD fungsi Malaysia', caged=True, max_results=4, timeout=3,
                 public_policy=True)
    assert client.search.call_args.kwargs['country'] == 'malaysia'
    assert {'facebook.com', 'instagram.com', 'tiktok.com'} <= set(client.search.call_args.kwargs['exclude_domains'])


def test_full_agency_name_search_keeps_derived_institution_initials():
    plan = definition(entities=('Example Coordination Unit',))
    query = p.research_query(plan)
    assert 'Example Coordination Unit' in query
    assert 'ECU' in query.split()


def test_identified_official_host_retry_uses_short_subject_query():
    plan = definition()
    source = chunk(web=True)
    query = p.part_research_query(plan, p.requested_parts(plan)[1])
    assert p._institution_query(plan, query, [source]) == 'ECU PMD fungsi peranan tugas'
    assert p._institution_query(plan, query, []) == query
    historical = definition(time_scope='historical', period='2023')
    historical_query = p.part_research_query(historical, p.requested_parts(historical)[1])
    assert p._institution_query(historical, historical_query, [source]) == historical_query


def test_stable_recovery_admits_new_web_pages_without_losing_corpus_or_proof():
    corpus = chunk('Internal verified definition.')
    old = [chunk('Old search snippet.', web=True, url=f'https://ecu.gov.my/old-{i}') for i in range(6)]
    fresh = chunk(TEXT, web=True, url='https://ecu.gov.my/full-profile')
    result = p._balanced_evidence([corpus, *old], [fresh], prefer_corpus=True,
                                 preserved=((old[0], ('Old search snippet.',)),))
    assert corpus in result
    assert old[0] in result
    assert fresh in result
    assert len(result) == 6


def test_unapproved_corpus_cannot_crowd_out_definition_recovery():
    old = [replace(chunk('Unrelated budgeting text.'), id=i) for i in range(6)]
    fresh = [chunk(TEXT, web=True, url=f'https://ecu.gov.my/profile-{i}') for i in range(2)]
    result = p._balanced_evidence(old, fresh, prefer_corpus=True)
    assert all(value in result for value in fresh)


def definition(**overrides):
    return replace(p.QuestionPlan('ECU PMD', False, True, 'stable',
        entities=('ECU PMD',), required_facts=p._DEFINITIONAL_FACTS,
        interpreted=True, definitional=True, part_tracking=True,
        subject_kind='agency', original_question='what is ecu pmd'), **overrides)


def chunk(text=TEXT, *, web=False, url='https://ecu.gov.my/profile', title='ECU PMD'):
    return RetrievedChunk(1, title, 'official', None, 0, text, .85,
        source_type='web' if web else 'corpus', url=url if web else None,
        tier=1 if web else None)


def approved(text=TEXT, *, complete=True):
    return p.EvidenceAssessment('sufficient' if complete else 'partial',
        () if complete else (p._DEFINITIONAL_FACTS[1],), supported_sources=(1,),
        supported_quotes=((1, text),), parts=(
            PartCoverage('p1', 'confirmed', (1,), complete=True),
            PartCoverage('p2', 'confirmed' if complete else 'missing',
                         (1,) if complete else (), complete=complete)))


def run(plan, candidates, assessor, search=None, **extra):
    # Only external model/network boundaries are replaced. Policy selection,
    # snapshots, quotation remapping and coverage are the production code.
    with patch.object(p, 'assess_evidence', side_effect=assessor), \
         patch.object(p, 'research_evidence', side_effect=search or [ResearchOutcome([], True, 'no_results')]*4), \
         patch('app.rag.research_windows.bootstrap_public_sources', return_value=[]):
        return p.run_research_policy(plan, candidates, generate=MagicMock(),
            budget=CoachRequestBudget.start(), api_key='test', web_enabled=True,
            max_results=4, timeout=8, **extra)


def test_unrelated_nonempty_definition_corpus_requires_recovery():
    unrelated=chunk('An intensive care unit treats critically ill hospital patients.')
    missing=p.EvidenceAssessment('insufficient', p._DEFINITIONAL_FACTS)
    def assess(plan,candidates,**kwargs):
        index=next((i for i,c in enumerate(candidates,1) if c.content==TEXT),None)
        return replace(approved(),supported_sources=(index,),supported_quotes=((index,TEXT),)) if index else missing
    result=run(definition(), [unrelated], assess,
               [ResearchOutcome([chunk(web=True)], True, 'ok')])
    assert result.web_used
    assert [c.source_type for c in result.chunks] == ['web']
    assert result.assessment.supported_quotes == ((1,TEXT),)


def test_sufficient_definition_corpus_is_assessed_without_web():
    seen=[]
    def assess(plan, candidates, **kwargs):
        seen.append(candidates)
        return approved()
    def no_web(*a, **k):
        raise AssertionError('Sufficient checked corpus should not search')
    result=run(definition(), [chunk()], assess, no_web)
    assert seen and result.assessment.parts[1].complete
    assert result.assessment.supported_quotes == ((1,TEXT),)
    assert not result.web_used


def test_programme_only_definition_retains_partial_and_searches_purpose():
    text='ECU PMD administers the Example Community Programme.'
    attempts=[]
    def search(*a,**k):
        attempts.append(a[0])
        return ResearchOutcome([],True,'no_results')
    result=run(definition(), [chunk(text)], lambda *a,**k:approved(text,complete=False),search)
    assert attempts
    assert result.assessment.status=='partial'
    assert result.assessment.supported_quotes==((1,text),)
    assert not result.assessment.parts[1].complete


def test_definition_failure_keeps_missing_part_ids():
    result=run(definition(), [], lambda *a,**k:p.EvidenceAssessment('insufficient',failure='assessment_unavailable'))
    assert [part.part_id for part in result.assessment.parts]==['p1','p2']
    assert result.diagnostics['requested_part_labels']==list(p._DEFINITIONAL_FACTS)


def test_definition_cached_source_is_reassessed():
    seen=[]
    with patch('app.rag.research_windows.bootstrap_public_sources', return_value=[chunk(web=True)]) as bootstrap, \
         patch.object(p,'assess_evidence',side_effect=lambda plan,candidates,**kw: seen.append(candidates) or (
             approved() if candidates else p.EvidenceAssessment('insufficient',p._DEFINITIONAL_FACTS))), \
         patch.object(p,'research_evidence',side_effect=AssertionError('Checked cached evidence is enough')), \
         patch('app.config.COACH_PUBLIC_SOURCE_CACHE_ENABLED',True):
        result=p.run_research_policy(definition(),[],generate=MagicMock(),budget=CoachRequestBudget.start(),
            api_key='test',web_enabled=True,max_results=4,timeout=8,source_store=MagicMock())
    assert bootstrap.called and seen and result.chunks
    assert result.assessment.supported_quotes


def test_definition_checker_failure_preserves_prior_valid_quotes_within_budget():
    text='ECU PMD administers the Example Community Programme.'
    failure=p.EvidenceAssessment('insufficient',failure='assessment_timeout')
    result=run(definition(),[chunk(text)], [approved(text,complete=False),failure,failure],
        [ResearchOutcome([chunk('New page about the agency.',web=True)],True,'ok')])
    assert result.assessment.supported_quotes==((1,text),)
    assert result.assessment.status=='partial'
    assert result.diagnostics['assessment_calls']<=6


@pytest.mark.parametrize('entity',['ICU JPM','ECU PMD','Implementation Coordination Unit (ICU), JPM'])
def test_definition_queries_preserve_unit_and_parent_identity(entity):
    plan=definition(topic=entity,entities=(entity,))
    queries=[p.research_query(plan),*(p.part_research_query(plan,part) for part in p.requested_parts(plan))]
    for query in queries:
        assert all(word.lower() in query.lower() for word in entity.replace('(','').replace(')','').replace(',','').split())


def test_definition_queries_omit_coverage_schema_phrases():
    queries=[p.research_query(definition()),*(p.part_research_query(definition(),part) for part in p.requested_parts(definition()))]
    assert all('what the topic is' not in q and 'including its full name' not in q for q in queries)
    assert 'nama penuh' in queries[1] and 'fungsi' in queries[2]


def test_malaysian_definition_targets_institution_profile_and_functions():
    query=p.research_query(definition())
    assert 'profil' in query and 'fungsi' in query
    assert 'ECU' in query and 'PMD' in query


def test_observed_public_numeric_redirect_selector_preserves_url_guards():
    from app.rag.web_research import is_public_guidance_url
    assert is_public_guidance_url('https://agency.gov.my/pg/get_url.php?id=3159')
    for url in ('https://agency.gov.my/pg/get_url.php?id=private',
                'https://agency.gov.my/pg/get_url.php?id=3159&token=secret',
                'https://agency.gov.my/pg/get_url.php?id=3159&id=2',
                'https://unknown.example/get_url.php?id=3159'):
        assert not is_public_guidance_url(url)


def test_role_retry_preserves_period_and_jurisdiction():
    plan=definition(time_scope='historical',period='2023')
    query=p.part_research_query(plan,p.requested_parts(plan)[1])
    assert 'ECU' in query and 'PMD' in query and '2023' in query and 'Malaysia' in query


def test_parent_acronym_alone_cannot_select_official_domain():
    source=chunk('JPM investment funds and asset holdings.',web=True,url='https://agency.gov.my/funds',title='JPM')
    assert p._official_domains(definition(entities=('ICU JPM',)),[source])==()


def test_medical_icu_passage_cannot_cover_government_agency_definition():
    payload=dict(status='insufficient',missing=['Agency identity','Agency purpose'],
        conflicting=False,jurisdiction_matches=True,period_matches=True,support=[],
        coverage=[dict(part_id=f'p{i}',status='missing',support_indices=[],resolution='direct',complete=False)
                  for i in (1,2)])
    result=p.assess_evidence(definition(entities=('ICU JPM',)),
        [chunk('An ICU treats critically ill hospital patients.')],
        generate=lambda *a,**k:SimpleNamespace(content=json.dumps(payload)),budget=CoachRequestBudget.start())
    assert result.status=='insufficient' and not result.supported_sources
    assert all(not part.complete for part in result.parts)


def test_checked_translated_agency_identity_can_support_definition():
    text='Unit Penyelarasan Pelaksanaan menyelaras dan memantau projek pembangunan kerajaan.'
    payload=dict(status='sufficient',missing=[],conflicting=False,jurisdiction_matches=True,
        period_matches=True,support=[dict(source_id=1,quote=text)],
        coverage=[dict(part_id=f'p{i}',status='confirmed',support_indices=[1],resolution='direct',complete=True)
                  for i in (1,2)])
    result=p.assess_evidence(definition(entities=('ICU JPM',)),
        [chunk(text,web=True,url='https://icu.gov.my/functions')],
        generate=lambda *a,**k:SimpleNamespace(content=json.dumps(payload)),budget=CoachRequestBudget.start())
    assert result.status=='sufficient' and result.supported_quotes==((1,text),)


def test_definition_topic_change_does_not_reuse_previous_programme():
    payload=dict(topic='ICU JPM',needs_personal=False,needs_external=True,time_scope='stable',
        entities=['ICU JPM','SejaTi MADANI'],required_facts=['identity','purpose'],
        clarification=None,clarification_facts=[],subject_kind='agency',application_subject=None,
        jurisdiction='Malaysia')
    history=[{'role':'assistant','content':'Previous programme reply.', 'ui_payload':{'research_context':
        {'topic':'SejaTi MADANI','entities':['ICU JPM','SejaTi MADANI'],'subject_kind':'programme'}}}]
    plan=p.interpret_question('what is ICU JPM',history,base_personal=False,base_external=True,
        generate=lambda *a,**k:SimpleNamespace(content=json.dumps(payload)))
    assert plan.definitional and plan.entities==('ICU JPM',)
    assert 'SejaTi' not in p.research_query(plan)


def service_reply(decision, *, unavailable=False, indices=(1,), capture=False):
    from app.rag.grounding import DISCLAIMER
    repo=MagicMock(user_id='public-definition-test')
    repo.require_session.return_value={'id':'s','title':'Existing'}
    repo.find_user_message.return_value=None
    repo.list_messages.return_value=[]
    repo.complete_turn.side_effect=lambda **kw:kw['assistant_payload']
    text=('Could not complete the explanation.' if unavailable else
          '**Insight**\n'+TEXT+f' [S{indices[0]}]\n\n**Educational guidance**\n'+DISCLAIMER)
    outcome=SimpleNamespace(result=AgentLLMResult(text,'definition-test-model'),
        mode='research_explanation_unavailable' if unavailable else 'research_explanation',
        diagnostics={'used_source_indices':[] if unavailable else list(indices),'complete':not unavailable})
    with patch.object(service,'COACH_RESEARCH_POLICY_ENABLED',True), \
         patch.object(service,'interpret_question',return_value=definition()), \
         patch.object(service,'retrieve',return_value=decision.chunks), \
         patch.object(service,'run_research_policy',return_value=decision), \
         patch.object(service,'generate_result',return_value=AgentLLMResult('Legacy reply.','legacy')), \
         patch.object(service,'_research_explanation_result',return_value=outcome), \
         patch.object(service,'_ground_educational_answer',side_effect=lambda result,*a,**k:(result,False,False)):
        reply=service.CoachingService(repo,MagicMock()).send_message('s','m','what is ecu pmd')
    return (reply,repo.complete_turn.call_args.kwargs['retrieval_rows']) if capture else reply


def test_corpus_only_definition_uses_research_explanation_owner():
    reply=service_reply(p.ResearchDecision([chunk()],approved()))
    assert TEXT in reply['assistant_message']['content']
    assert reply['assistant_message']['model']=='definition-test-model'


def test_definition_sources_match_displayed_verified_claims():
    extra=replace(chunk('Unrelated grant programme.'),id=2,title='Other scheme')
    reply=service_reply(p.ResearchDecision([chunk(),extra],approved()))
    assert len(reply['sources'])==1 and reply['sources'][0]['title']=='ECU PMD'
    assert len(reply['assistant_message']['ui_payload']['source_snapshot'])==1


def test_unavailable_definition_has_no_claim_source_cards_or_snapshot():
    reply=service_reply(p.ResearchDecision([chunk(web=True)],approved()),unavailable=True)
    assert reply['sources']==[]
    assert not reply['assistant_message']['ui_payload'].get('source_snapshot')


def test_optional_action_definition_keeps_natural_explanation():
    reply=service_reply(p.ResearchDecision([chunk()],approved()))
    assert TEXT in reply['assistant_message']['content']
    assert 'Recommended action' not in reply['assistant_message']['content']


def test_filtered_corpus_sources_persist_the_matching_document_identity():
    first=replace(chunk('Unrelated programme.',title='Wrong document'),id=101)
    second=replace(chunk(title='Correct document'),id=202)
    assessment=replace(approved(),supported_sources=(2,),supported_quotes=((2,TEXT),))
    reply,rows=service_reply(p.ResearchDecision([first,second],assessment),indices=(2,),capture=True)
    assert reply['sources'][0]['rank']==2
    assert [(r['knowledge_document_id'],r['title'],r['rank']) for r in rows]==[(202,'Correct document',2)]


@pytest.mark.parametrize('topic,entity,words',[
    ('AKPK Debt Management Programme (DMP)','AKPK',('Debt','Management','Programme')),
    ('EPF Education Withdrawal','EPF',('Education','Withdrawal'))])
def test_programme_definition_searches_preserve_subject(topic,entity,words):
    plan=definition(topic=topic,entities=(entity,),subject_kind='programme')
    queries=[p.research_query(plan),*(p.part_research_query(plan,part) for part in p.requested_parts(plan))]
    for query in queries:
        assert all(word.casefold() in query.casefold() for word in words)
        assert entity in query
        assert 'profil' not in query


def test_observed_government_public_news_gallery_is_extractable():
    from app.rag.web_research import is_public_guidance_url
    assert is_public_guidance_url('https://agency.gov.my/pg/main.php?pg=galeri&type=berita&list=akt24&id=3943')
    assert not is_public_guidance_url('https://agency.gov.my/pg/main.php?pg=galeri&token=secret&id=3943')


def test_malaysian_agency_gap_queries_use_profile_and_role_vocabulary():
    parts=p.requested_parts(definition())
    identity=p.part_research_query(definition(),parts[0])
    purpose=p.part_research_query(definition(),parts[1])
    assert 'nama penuh' in identity and 'profil' in identity
    assert all(word in purpose for word in ('fungsi','peranan','tugas'))


def test_corpus_definition_is_explained_and_verified_without_quote_substitution():
    from app.rag import research_answer
    from app.rag.verifier import GroundingVerification
    prose='ECU PMD is the Example Coordination Unit, a government agency that oversees implementation of development projects.'
    def supported(claims,*a,**k):
        return GroundingVerification({c.id:'supported' for c in claims},
            {c.id:1 for c in claims},requested_scope_covered=True,answered_part_ids=('p1','p2'))
    with patch.object(service,'generate_result',return_value=AgentLLMResult(prose+' [S1]','primary')), \
         patch.object(research_answer,'verify_grounding_claims',side_effect=supported), \
         patch.object(research_answer,'generate_fallback_result',side_effect=AssertionError('Valid prose needs no rewrite')):
        outcome=service._research_explanation_result(plan=definition(),
            decision=p.ResearchDecision([chunk()],approved()),budget=CoachRequestBudget.start(),question='what is ecu pmd')
    assert prose.rstrip('.') in outcome.result.content and TEXT not in outcome.result.content
    assert outcome.diagnostics['used_source_indices']==[1]
    assert 'Recommended action' not in outcome.result.content
