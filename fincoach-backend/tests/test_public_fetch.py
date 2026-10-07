"""Guarded direct official fetch: offline tests (mock transport, stubbed DNS)."""
import ssl

import httpx
import pytest

from app.rag import public_fetch
from app.rag import web_research
from app.rag.web_research import WebResearchCache, extract_passages

_PAGE = ("<html><head><title>Profil</title><script>var x=1;</script></head><body>"
         "<nav><ul>" + "".join(f'<li><a href="/pg/main.php?pg=info&type=corp&list=m{i}">Menu {i}</a></li>'
                               for i in range(8)) + "</ul></nav>"
         "<h4>Perkhidmatan Teras Utama</h4><ul>"
         "<li>Menyelaras, memantau, menilai pelaksanaan dan outcome Program Projek Pembangunan.</li>"
         "<li>Mengurus peruntukan serta melaksana dan memantau Program Projek Khas kerajaan persekutuan.</li>"
         "</ul><p>Unit Penyelarasan Pelaksanaan ialah agensi pusat di Jabatan Perdana Menteri yang "
         "menyelaras pemantauan pembangunan negara bagi kesejahteraan rakyat seluruh Malaysia.</p></body></html>")


@pytest.fixture
def mock_http(monkeypatch):
    """Route fetch_official_page through a MockTransport and public DNS."""
    routes = {}
    real_client = httpx.Client

    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))

    def client_factory(*args, **kwargs):
        assert isinstance(kwargs.get("verify"), ssl.SSLContext)
        kwargs.pop("verify")
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    monkeypatch.setattr(public_fetch, "_resolves_publicly", lambda host: True)
    return routes


def _html(body=_PAGE, status=200, ctype="text/html; charset=utf-8", headers=None):
    return httpx.Response(status, content=body.encode("utf-8") if isinstance(body, str) else body,
                          headers={"content-type": ctype, **(headers or {})})


def test_ssl_context_never_disables_verification():
    context = public_fetch._ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_bundled_intermediates_are_present_and_not_roots():
    from cryptography import x509
    pem = public_fetch.EXTRA_INTERMEDIATES.read_bytes()
    certs = x509.load_pem_x509_certificates(pem)
    assert certs
    for cert in certs:
        assert cert.subject != cert.issuer  # intermediates only, never self-signed roots


@pytest.mark.parametrize("url", [
    "https://example.com/about",            # unclassified host
    "https://www.reddit.com/r/malaysia",    # community tier
    "http://www.icu.gov.my/pg/main.php",    # plain http
    "https://user:pw@www.icu.gov.my/",      # credentials
    "https://www.icu.gov.my/login",         # account path
    "https://127.0.0.1/",                   # literal address
])
def test_non_official_or_unsafe_urls_are_rejected_without_network(monkeypatch, url):
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: pytest.fail("network must not be used"))
    assert public_fetch.fetch_official_page(url, timeout=5) is None


def test_private_dns_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(public_fetch.socket, "getaddrinfo",
                        lambda *a, **k: [(None, None, None, None, ("10.0.0.5", 443))])
    assert public_fetch._resolves_publicly("www.icu.gov.my") is False
    monkeypatch.setattr(public_fetch.socket, "getaddrinfo",
                        lambda *a, **k: [(None, None, None, None, ("203.106.0.10", 443))])
    assert public_fetch._resolves_publicly("www.icu.gov.my") is True


def test_html_keeps_headings_and_moves_menus_after_content(mock_http):
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    mock_http[url] = _html()
    text = public_fetch.fetch_official_page(url, timeout=5)
    assert text is not None
    assert "#### Perkhidmatan Teras Utama" in text
    assert "var x" not in text
    content_at = text.index("Perkhidmatan Teras Utama")
    assert text.index("## Page links") > content_at
    assert "[Menu 3](https://www.icu.gov.my/pg/main.php?pg=info&type=corp&list=m3)" in text
    # Content sentences remain literal, contiguous source spans.
    assert ("Unit Penyelarasan Pelaksanaan ialah agensi pusat di Jabatan Perdana Menteri yang "
            "menyelaras pemantauan pembangunan negara") in text


def test_redirect_to_non_official_host_is_rejected(mock_http):
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    mock_http[url] = httpx.Response(302, headers={"location": "https://evil.example.com/x"})
    assert public_fetch.fetch_official_page(url, timeout=5) is None


def test_redirect_within_official_host_is_followed(mock_http):
    start = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    final = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp&list=profil"
    mock_http[start] = httpx.Response(301, headers={"location": final})
    mock_http[final] = _html()
    assert "Perkhidmatan Teras Utama" in public_fetch.fetch_official_page(start, timeout=5)


@pytest.mark.parametrize("response", [
    httpx.Response(202, content=b""),                                   # WAF challenge
    httpx.Response(403, content=b"blocked"),
    httpx.Response(200, content=b"<html><body>Loading...</body></html>",
                   headers={"content-type": "text/html"}),              # JS shell
    httpx.Response(200, content=b"\x00\x01", headers={"content-type": "application/zip"}),
])
def test_challenge_empty_or_binary_responses_return_none(mock_http, response):
    url = "https://www.akpk.org.my/"
    mock_http[url] = response
    assert public_fetch.fetch_official_page(url, timeout=5) is None


def test_oversized_body_is_rejected(mock_http):
    url = "https://www.icu.gov.my/big"
    mock_http[url] = _html(body="<p>" + "word " * 400_000 + "</p>")
    assert public_fetch.fetch_official_page(url, timeout=5) is None


def test_mislabeled_cp1252_page_is_decoded(mock_http):
    url = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp"
    body = _PAGE.replace("Unit Penyelarasan", "DATO\u2019 HAJI MOHD \u2013 Unit Penyelarasan"
                         ).replace("<p>", "<p>\u2019\u2019\u2019\u2019 ")
    mock_http[url] = _html(body=body.encode("cp1252"))
    text = public_fetch.fetch_official_page(url, timeout=5)
    assert "DATO\u2019 HAJI" in text and "\ufffd" not in text


class _FakeTavily:
    response = {"results": [], "failed_results": [{"url": "x"}]}

    def __init__(self, api_key):
        pass

    def extract(self, **kwargs):
        return self.response


@pytest.fixture
def tavily_fails(monkeypatch):
    import sys, types
    module = types.SimpleNamespace(TavilyClient=_FakeTavily)
    monkeypatch.setitem(sys.modules, "tavily", module)
    return _FakeTavily


def test_extract_falls_back_only_for_failed_official_urls(monkeypatch, tavily_fails):
    from app import config
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", True)
    fetched = []

    def fake_fetch(url, *, timeout):
        fetched.append(url)
        return "# Profil Jabatan\n\n" + "Unit Penyelarasan Pelaksanaan menyelaras pembangunan negara. " * 10

    monkeypatch.setattr(public_fetch, "fetch_official_page", fake_fetch)
    cache = WebResearchCache()
    official = "https://www.icu.gov.my/pg/main.php?pg=info&type=corp&list=profil"
    unknown = "https://some-blog.example.com/icu"
    passages = extract_passages([official, unknown], api_key="k", query="ICU JPM fungsi",
                                timeout=8, cache=cache, complete_context=True, subject_query="ICU JPM")
    assert fetched == [official]
    assert official in passages and unknown not in passages
    assert official in cache.full_pages and official in cache.fetched_pages  # persisted path
    assert cache.direct_fetches == 1
    assert cache.public_source_diagnostics["direct_fetch_pages"] == 1
    assert cache.last_error is None  # recovered extraction is not reported as failed


def test_extract_does_not_refetch_successful_tavily_page(monkeypatch, tavily_fails):
    from app import config
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", True)
    url = "https://www.ptptn.gov.my/en/korporat/"
    monkeypatch.setattr(tavily_fails, "response",
                        {"results": [{"url": url, "raw_content": "PTPTN corporate information. " * 40}]})
    monkeypatch.setattr(public_fetch, "fetch_official_page", lambda *a, **k: pytest.fail("not needed"))
    cache = WebResearchCache()
    extract_passages([url], api_key="k", query="PTPTN", timeout=8, cache=cache, complete_context=True)
    assert cache.direct_fetches == 0


def test_direct_fetch_cap_and_kill_switch(monkeypatch, tavily_fails):
    from app import config
    calls = []
    monkeypatch.setattr(public_fetch, "fetch_official_page", lambda url, **k: calls.append(url) or None)
    urls = [f"https://www.icu.gov.my/pg/main.php?pg=info&type=corp&list=p{i}" for i in range(6)]
    cache = WebResearchCache()
    extract_passages(urls, api_key="k", query="q", timeout=8, cache=cache, complete_context=True)
    assert calls == []  # disabled by the hermetic default
    monkeypatch.setattr(config, "COACH_DIRECT_FETCH_ENABLED", True)
    extract_passages(urls, api_key="k", query="q", timeout=8, cache=cache, complete_context=True)
    extract_passages(urls, api_key="k", query="q2", timeout=8, cache=cache, complete_context=True)
    assert len(calls) == web_research._DIRECT_FETCH_CAP
