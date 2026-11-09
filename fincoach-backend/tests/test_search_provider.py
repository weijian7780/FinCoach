import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from app import config
from app.search_provider import ExaProvider, ProviderError, configured_key, country_code, provider
from app.rag.web_research import WebResearchCache, _safe_error, search_web, extract_passages, to_retrieved_chunks


@pytest.fixture
def exa(monkeypatch):
    monkeypatch.setattr(config, 'WEB_SEARCH_PROVIDER', 'exa')
    return ExaProvider('synthetic-secret')


def test_search_privacy_and_preference(exa, monkeypatch):
    post = Mock(return_value=httpx.Response(200, json={'results': [
        {'url': 'https://guide.example/one', 'title': 'Guide', 'text': 'Complete page text.'}],
        'costDollars': {'total': .007}}))
    monkeypatch.setattr(httpx, 'post', post)
    result = exa.search(query='public education', max_results=4, country='malaysia',
                        include_domains=['guide.example'], include_domains_mode='prefer',
                        userIdentifier='must-not-leave', conversation='private', balance=123)
    body = post.call_args.kwargs['json']
    assert body == {'query': 'public education', 'numResults': 4, 'type': 'auto',
                    'contents': {'text': {'maxCharacters': 2000}}, 'userLocation': 'MY'}
    assert result['results'][0]['score'] is None
    assert result['results'][0]['content']
    exa.search(query='public education', include_domains=['guide.example'], include_domains_mode='restrict')
    assert post.call_args.kwargs['json']['includeDomains'] == ['guide.example']


@pytest.mark.parametrize('status,code', [(401,'auth_error'),(403,'auth_error'),(402,'quota'),
                                       (429,'rate_limited'),(500,'search_failed'),(503,'search_failed')])
def test_errors_are_safe(exa, monkeypatch, caplog, status, code):
    monkeypatch.setattr(httpx, 'post', Mock(return_value=httpx.Response(status, text='synthetic-secret')))
    with pytest.raises(ProviderError) as caught:
        exa.search(query='public education')
    assert _safe_error(caught.value) == code
    assert 'synthetic-secret' not in str(caught.value) + caplog.text
    errors = []
    assert search_web('public education', api_key='synthetic-secret', errors=errors, single_search=True) == []
    assert errors == [code]


@pytest.mark.parametrize('error,code', [(httpx.ReadTimeout('synthetic-secret'),'timeout'),
                                      (httpx.ConnectError('synthetic-secret'),'network_error')])
def test_network_errors(exa, monkeypatch, error, code):
    monkeypatch.setattr(httpx, 'post', Mock(side_effect=error))
    with pytest.raises(ProviderError) as caught:
        exa.extract(urls=['https://guide.example/one'])
    assert str(caught.value) == code


def test_partial_page_results_and_events(exa, monkeypatch):
    first, second = 'https://guide.example/one', 'https://guide.example/two'
    def post(url, **kwargs):
        assert set(kwargs['json']) == {'urls', 'text', 'maxAgeHours', 'livecrawlTimeout'}
        assert kwargs['json']['text']['verbosity'] == 'full'
        assert kwargs['json']['maxAgeHours'] == 24
        selected = kwargs['json']['urls']
        return httpx.Response(200, json={'results': [{'url':first,'text':'# Steps\n\nSubmit the complete application.'}] if first in selected else [],
            'statuses': [{'id':u,'status':'success' if u == first else 'error',
                          'error':None if u == first else {'tag':'FETCH_ERROR','httpStatusCode':403}} for u in selected]})
    monkeypatch.setattr(httpx, 'post', post)
    cache = WebResearchCache()
    result = extract_passages([first,second], api_key='synthetic-secret', cache=cache)
    assert first in result and second not in result
    assert {r['url']:r['success'] for r in cache.extraction_events} == {first:True,second:False}
    assert cache.last_error == 'extraction_failed'


def test_tavily_selection_never_dispatches_exa(monkeypatch):
    monkeypatch.setattr(config,'WEB_SEARCH_PROVIDER','tavily')
    client = Mock()
    monkeypatch.setitem(sys.modules,'tavily',SimpleNamespace(TavilyClient=Mock(return_value=client)))
    post = Mock(side_effect=AssertionError('Unexpected HTTP'))
    monkeypatch.setattr(httpx,'post',post)
    instance = provider('synthetic-secret')
    instance.search(query='public education', topic='finance')
    instance.extract(urls=['https://guide.example/one'])
    client.search.assert_called_once_with(query='public education', topic='finance')
    client.extract.assert_called_once()
    post.assert_not_called()


def test_country_and_active_key(exa, monkeypatch):
    assert country_code('malaysia') == country_code('my') == 'MY'
    assert country_code('unmapped') is None
    monkeypatch.setattr(config,'EXA_API_KEY','candidate')
    assert configured_key('legacy') == 'candidate'


def test_unscored_search_order_is_stable(exa, monkeypatch):
    monkeypatch.setattr('app.embeddings.embed_texts', Mock(side_effect=RuntimeError('Unavailable')))
    urls = ['https://second.example/guide', 'https://first.example/guide']
    monkeypatch.setattr(httpx, 'post', Mock(return_value=httpx.Response(200, json={
        'results': [{'url':url, 'text':'A complete explanatory sentence.'} for url in urls]})))
    results = search_web('public education', api_key='synthetic-secret', single_search=True)
    assert [r.url for r in results] == urls
    assert all(r.score is None for r in results)
    assert [c.url for c in to_retrieved_chunks(results)] == urls


def test_configured_payload_flag_tracks_selected_provider(exa, monkeypatch):
    monkeypatch.setattr(config, 'TAVILY_API_KEY', 'legacy')
    monkeypatch.setattr(config, 'EXA_API_KEY', '')
    assert not configured_key()
    monkeypatch.setattr(config, 'EXA_API_KEY', 'candidate')
    assert configured_key() == 'candidate'
    monkeypatch.setattr(config, 'WEB_SEARCH_PROVIDER', 'tavily')
    assert configured_key() == 'legacy'


def test_cost_units_do_not_mix_or_accept_invalid_values():
    cache = WebResearchCache()
    cache.note_usage({'usage': {'credits': 2}})
    cache.note_usage({'costDollars': {'total': .007}})
    cache.note_usage({'costDollars': {'total': .001}})
    for invalid in (float('nan'), float('inf'), -1, True, 'synthetic-secret'):
        cache.note_usage({'costDollars': {'total': invalid}})
    assert cache.credits == 2
    assert cache.exa_cost_dollars == .008


@pytest.mark.parametrize('url', ['http://localhost/private','https://guide.example/?account=123',
                               'https://name:password@guide.example/one'])
def test_private_urls_never_dispatched(exa, monkeypatch, url):
    post = Mock()
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(ProviderError):
        exa.extract(urls=[url])
    post.assert_not_called()
