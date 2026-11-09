from dataclasses import replace
from threading import Event
from time import monotonic
from unittest.mock import Mock, patch

import httpx
import pytest
from app import config
from app.search_provider import ExaProvider, country_code
from app.rag.search_similarity import score_unscored
from app.rag.web_research import WebResult, WebResearchCache, search_web, extract_passages, research_evidence, to_retrieved_chunks
from app.rag.research_policy import QuestionPlan, ResearchDecision, EvidenceAssessment
from app.rag.research_answer import recover_research_answer
from app.llm import CoachRequestBudget


@pytest.fixture
def exa(monkeypatch):
    monkeypatch.setattr(config,'WEB_SEARCH_PROVIDER','exa')
    return ExaProvider('synthetic-key')


@pytest.mark.parametrize('country',['Japan','China','Hong Kong','South Korea','global','international'])
def test_other_jurisdictions_send_search_without_location(exa,monkeypatch,country):
    post=Mock(return_value=httpx.Response(200,json={'results':[]}))
    monkeypatch.setattr(httpx,'post',post)
    exa.search(query='public education '+country,country=country)
    assert 'userLocation' not in post.call_args.kwargs['json']
    assert country.casefold() in post.call_args.kwargs['json']['query'].casefold()


def test_default_country_is_configuration_not_country_list(monkeypatch):
    monkeypatch.setattr(config,'WEB_SEARCH_DEFAULT_COUNTRY','deployment country')
    monkeypatch.setattr(config,'WEB_SEARCH_DEFAULT_COUNTRY_CODE','ZZ')
    assert country_code('deployment country')=='ZZ'
    assert country_code('jp')=='JP'
    assert country_code('Malaysia') is None
    monkeypatch.setattr(config,'WEB_SEARCH_DEFAULT_COUNTRY_CODE','mistyped')
    assert country_code('deployment country') is None


def test_cosine_values_are_measured_and_existing_score_preserved(monkeypatch):
    embed=Mock(return_value=[[1.,0.],[.6,.8],[0.,1.]])
    monkeypatch.setattr('app.embeddings.embed_texts',embed)
    rows=[WebResult('a','https://a.example','source a',None),
          WebResult('b','https://b.example','source b',None),
          WebResult('c','https://c.example','source c',.91)]
    scored=score_unscored('public query',rows,1)
    assert [r.score for r in scored]==[.6,0.,.91]
    embed.assert_called_once_with(['public query','source a','source b'])
    assert [round(r.score*100) for r in scored]==[60,0,91]


def test_slow_embedding_cannot_overrun_search_deadline(monkeypatch):
    release=Event()
    def delayed(texts):
        release.wait(5)
        return [[1.,0.],[1.,0.]]
    monkeypatch.setattr('app.embeddings.embed_texts',delayed)
    rows=[WebResult('a','https://a.example','source a',None)]
    start=monotonic()
    try:
        assert score_unscored('query',rows,.02)==rows
        assert monotonic()-start < 2.3
    finally:
        release.set()


def test_scoring_embeds_bounded_source_text(monkeypatch):
    seen=[]
    def embed(texts):
        seen.extend(texts)
        return [[1.,0.],[1.,0.]]
    monkeypatch.setattr('app.embeddings.embed_texts',embed)
    rows=[WebResult('a','https://a.example','x'*5000,None)]
    assert score_unscored('query',rows,1)[0].score==1.0
    assert seen==['query','x'*600]


def test_embedding_failure_retains_unknown_not_invented(monkeypatch):
    monkeypatch.setattr('app.embeddings.embed_texts',Mock(side_effect=RuntimeError()))
    rows=[WebResult('a','https://a.example','source a',None)]
    assert score_unscored('query',rows,1)[0].score is None


@pytest.mark.parametrize('fresh,age',[(False,24),(True,0)])
def test_freshness_applies_only_to_page_reads(exa,monkeypatch,fresh,age):
    post=Mock(return_value=httpx.Response(200,json={'results':[],'statuses':[]}))
    monkeypatch.setattr(httpx,'post',post)
    exa.search(query='public query',fresh_required=fresh)
    assert 'maxAgeHours' not in post.call_args.kwargs['json']['contents']
    exa.extract(urls=['https://guide.example/page'],fresh_required=fresh,timeout=2)
    assert post.call_args.kwargs['json']['maxAgeHours']==age
    assert post.call_args.kwargs['json']['livecrawlTimeout']==2000


def test_website_denial_does_not_become_technical_reply(exa,monkeypatch):
    url='https://guide.example/page'
    monkeypatch.setattr(httpx,'post',Mock(return_value=httpx.Response(200,json={
        'results':[],'statuses':[{'id':url,'status':'error','error':{'httpStatusCode':403}}]})))
    cache=WebResearchCache()
    assert extract_passages([url],api_key='synthetic-key',cache=cache)=={}
    assert cache.last_error=='extraction_failed'
    answer=recover_research_answer(plan=QuestionPlan('public query',False,True,'stable'),
        decision=ResearchDecision([],EvidenceAssessment('insufficient'),failure=cache.last_error),
        budget=CoachRequestBudget.start(),public_question='public query',draft=None)
    assert answer.diagnostics['reply_reason']!='technical'


def test_bad_provider_degrades_every_entrypoint(monkeypatch):
    monkeypatch.setattr(config,'WEB_SEARCH_PROVIDER','mistyped')
    errors=[]
    assert search_web('public query',api_key='synthetic-key',errors=errors)==[]
    assert errors==['invalid_provider']
    assert extract_passages(['https://guide.example/page'],api_key='synthetic-key')=={}
    from app.admin import link_import
    monkeypatch.setattr(link_import,'_resolves_publicly',lambda host:True)
    fallback=Mock(return_value={'title':'Guide','content':'Complete public page.'})
    monkeypatch.setattr(link_import,'fetch_public_webpage',fallback)
    assert link_import.extract_link('https://guide.example/page','synthetic-key')['content']=='Complete public page.'
    fallback.assert_called_once()


def test_measured_scores_reach_source_cards(exa,monkeypatch):
    monkeypatch.setattr('app.embeddings.embed_texts',Mock(return_value=[[1.,0.],[.6,.8],[0.,1.]]))
    urls=['https://first.example/guide','https://second.example/guide']
    monkeypatch.setattr(httpx,'post',Mock(return_value=httpx.Response(200,json={
        'results':[{'url':urls[0],'title':'First','text':'source one'},
                   {'url':urls[1],'title':'Second','text':'source two'}]})))
    results=search_web('public query',api_key='synthetic-key',single_search=True)
    assert [round(result.score*100) for result in results]==[60,0]
    chunks=to_retrieved_chunks(results)
    assert [round(chunk.similarity*100) for chunk in chunks]==[60,0]


def test_restricted_envelope_preserves_domain_boundaries(exa,monkeypatch):
    post=Mock(return_value=httpx.Response(200,json={'results':[]}))
    monkeypatch.setattr(httpx,'post',post)
    exa.search(query='public query',include_domains=['guide.example'],include_domains_mode='restrict',
               exclude_domains=['excluded.example'])
    body=post.call_args.kwargs['json']
    assert body['includeDomains']==['guide.example']
    assert 'excludeDomains' not in body
    assert set(body) <= {'query','numResults','type','contents','includeDomains','excludeDomains','userLocation'}


@pytest.mark.parametrize('overrides',[
    {'time_scope':'current'}, {'time_scope':'historical','period':'2025'},
    {'verify_current':True}, {'explicit_search':True},
])
def test_plan_requires_fresh_provider_reads(monkeypatch, overrides):
    from app.rag import research_policy as policy
    base=QuestionPlan('public query',False,True,'stable')
    plan=replace(base,**overrides)
    factory=Mock(wraps=WebResearchCache)
    monkeypatch.setattr(policy,'WebResearchCache',factory)
    policy.run_research_policy(plan,[],generate=None,budget=CoachRequestBudget.start(),
        api_key='synthetic-key',web_enabled=False,max_results=4,timeout=1)
    assert factory.call_args.kwargs['fresh_required'] is True
