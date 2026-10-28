"""Offline regression tests for public-page fallback and its network guards."""

import socket
import time
from unittest.mock import MagicMock, patch

import pytest
from urllib3._collections import HTTPHeaderDict
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import webpage_fetch
from app.admin.routes import administrator, router
from app.auth import AuthenticatedUser


WORDS = ('A personal budget helps a person understand their income and spending. '
         'It supports saving for important goals and makes regular financial decisions clearer. '
         'Reviewing the budget regularly can help people adapt when their circumstances change.')
PAGE = (f'<html><head><title>Budget guide</title><script>secret script</script></head>'
        f'<body><nav>Navigation menu</nav><main><article><h1>Budget guide</h1>'
        f'<p>{WORDS}</p><div class="adslot">ADVERTISEMENT</div><aside>Side menu</aside>'
        f'<p>{WORDS}</p></article></main><footer>Footer text</footer></body></html>')


class FakeResponse:
    def __init__(self, status=200, body=b'', headers=None):
        self.status = status
        self.body = body
        self.headers = HTTPHeaderDict({key: str(value) for key, value in (headers or {}).items()})

    def getheader(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def read1(self, size, decode_content=False):
        data, self.body = self.body[:size], self.body[size:]
        return data


def install_fake_network(monkeypatch, responses, blocked=()):
    connections = []

    def resolve(host, port):
        if host in blocked:
            raise ValueError('non-public')
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', port))]

    def make_connection(parsed, infos, deadline):
        conn = MagicMock()
        conn.sock = MagicMock()
        conn.getresponse.return_value = responses[parsed.geturl()]
        connections.append((parsed.geturl(), infos, conn))
        return conn

    monkeypatch.setattr(webpage_fetch, '_public_addresses', resolve)
    monkeypatch.setattr(webpage_fetch, '_connection', make_connection)
    return connections


def html_response(html=PAGE, headers=None):
    body = html.encode()
    return FakeResponse(body=body, headers={'Content-Type': 'text/html; charset=utf-8',
                                            'Content-Length': len(body), **(headers or {})})


def test_fallback_extracts_article_and_excludes_surrounding_material(monkeypatch):
    url = 'https://example.org/article'
    connections = install_fake_network(monkeypatch, {url: html_response()})
    page = webpage_fetch.fetch_public_webpage(url)
    assert page['title'] == 'Budget guide'
    assert page['content'].count(WORDS) == 2
    assert '# Budget guide' in page['content']
    for excluded in ('Navigation menu', 'secret script', 'ADVERTISEMENT', 'Side menu', 'Footer text'):
        assert excluded not in page['content']
    connections[0][2].close.assert_called_once()


def test_redirect_is_revalidated_before_connecting(monkeypatch):
    url = 'https://example.org/article'
    response = FakeResponse(status=302, headers={'Location': 'https://internal.example/secrets'})
    connections = install_fake_network(monkeypatch, {url: response}, blocked={'internal.example'})
    assert webpage_fetch.fetch_public_webpage(url) is None
    assert [item[0] for item in connections] == [url]


def test_safe_redirect_preserves_target_and_original_import_provenance(monkeypatch):
    source, target = 'https://example.org/start', 'https://example.org/final'
    connections = install_fake_network(monkeypatch, {
        source: FakeResponse(status=301, headers={'Location': '/final'}),
        target: html_response(),
    })
    page = webpage_fetch.fetch_public_webpage(source)
    assert page['title'] == 'Budget guide'
    assert [item[0] for item in connections] == [source, target]


@pytest.mark.parametrize('target', [
    'http://example.org/unsafe', 'https://user:secret@example.org/',
    'http://127.0.0.1:8000/', 'file:///secret', 'https://example.org:444/',
])
def test_unsafe_redirects_never_connect(monkeypatch, target):
    source = 'https://example.org/start'
    connections = install_fake_network(monkeypatch, {
        source: FakeResponse(status=302, headers={'Location': target})
    }, blocked={'127.0.0.1'})
    assert webpage_fetch.fetch_public_webpage(source) is None
    assert len(connections) == 1


def test_mixed_public_and_private_dns_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(webpage_fetch.socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443)),
    ])
    with pytest.raises(ValueError):
        webpage_fetch._public_addresses('example.org', 443)


def test_ipv4_mapped_private_ipv6_is_rejected(monkeypatch):
    monkeypatch.setattr(webpage_fetch.socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::ffff:127.0.0.1', 443, 0, 0)),
    ])
    with pytest.raises(ValueError):
        webpage_fetch._public_addresses('example.org', 443)


def test_multicast_dns_address_is_rejected(monkeypatch):
    monkeypatch.setattr(webpage_fetch.socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('224.0.0.1', 443)),
    ])
    with pytest.raises(ValueError):
        webpage_fetch._public_addresses('example.org', 443)


def test_connect_uses_the_validated_ip_without_another_dns_lookup(monkeypatch):
    fake_socket = MagicMock()
    monkeypatch.setattr(webpage_fetch.socket, 'socket', lambda *args: fake_socket)
    monkeypatch.setattr(webpage_fetch.socket, 'getaddrinfo', lambda *a, **k: pytest.fail('DNS lookup after validation'))
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]
    assert webpage_fetch._connect_pinned(infos, time.monotonic() + 5) is fake_socket
    fake_socket.connect.assert_called_once_with(('8.8.8.8', 443))


def test_tls_verifies_original_hostname(monkeypatch):
    parsed = webpage_fetch._parse_public_url('https://example.org/path')
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]
    conn = webpage_fetch._connection(parsed, infos, time.monotonic() + 5)
    assert conn.host == 'example.org'
    assert conn.cert_reqs == webpage_fetch.ssl.CERT_REQUIRED
    assert conn.ca_certs == webpage_fetch.certifi.where()
    conn.close()


@pytest.mark.parametrize('response', [
    FakeResponse(status=403, body=b'blocked', headers={'Content-Type': 'text/html'}),
    FakeResponse(body=b'binary', headers={'Content-Type': 'application/octet-stream'}),
    FakeResponse(body=b'compressed', headers={'Content-Type': 'text/html', 'Content-Encoding': 'gzip'}),
    FakeResponse(body=b'short', headers={'Content-Type': 'text/html', 'Content-Length': '100'}),
    FakeResponse(body=b'short', headers={'Content-Type': 'text/html', 'Content-Length': '1500001'}),
    FakeResponse(body=b'<html><title>Just a moment</title><body>Wait</body></html>', headers={'Content-Type': 'text/html'}),
])
def test_unreadable_unsafe_or_truncated_responses_are_rejected(monkeypatch, response):
    url = 'https://example.org/article'
    install_fake_network(monkeypatch, {url: response})
    assert webpage_fetch.fetch_public_webpage(url) is None


def test_streamed_body_over_limit_is_rejected_without_truncation(monkeypatch):
    url = 'https://example.org/article'
    response = FakeResponse(body=b'x' * (webpage_fetch.MAX_BODY_BYTES + 1),
                            headers={'Content-Type': 'text/html'})
    install_fake_network(monkeypatch, {url: response})
    assert webpage_fetch.fetch_public_webpage(url) is None


def test_page_with_too_much_readable_text_is_not_silently_truncated(monkeypatch):
    url = 'https://example.org/article'
    response = html_response('<html><body><article>' + WORDS * 1000 + '</article></body></html>')
    install_fake_network(monkeypatch, {url: response})
    assert webpage_fetch.fetch_public_webpage(url) is None


def test_admin_route_returns_fallback_page_after_provider_failure(monkeypatch):
    url = 'https://example.org/article'
    install_fake_network(monkeypatch, {url: html_response()})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[administrator] = lambda: AuthenticatedUser('admin', 'token')
    tavily_client = MagicMock()
    tavily_client.extract.side_effect = RuntimeError('provider error')
    with patch('app.admin.routes.config.TAVILY_API_KEY', 'test-key'), \
         patch('app.admin.link_import._resolves_publicly', return_value=True), \
         patch('tavily.TavilyClient', return_value=tavily_client):
        response = TestClient(app).post('/api/admin/imports/link', json={'url': url})
    assert response.status_code == 200
    assert response.json()['source_urls'] == [url]
    assert response.json()['title'] == 'Budget guide'
    assert response.json()['content'].count(WORDS) == 2
