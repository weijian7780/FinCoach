"""Provider adapters for public search and page reading."""
import httpx


class ProviderError(Exception):
    def __init__(self, code, status_code=None):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def country_code(value):
    from app.config import WEB_SEARCH_DEFAULT_COUNTRY, WEB_SEARCH_DEFAULT_COUNTRY_CODE
    value = str(value or '').strip()
    if len(value) == 2 and value.isascii() and value.isalpha():
        return value.upper()
    if value and value.casefold() == WEB_SEARCH_DEFAULT_COUNTRY.casefold():
        code = WEB_SEARCH_DEFAULT_COUNTRY_CODE.strip()
        if len(code) == 2 and code.isascii() and code.isalpha():
            return code.upper()
    return None


class TavilyProvider:
    def __init__(self, api_key):
        from tavily import TavilyClient
        self.client = TavilyClient(api_key=api_key)

    def search(self, **kwargs):
        kwargs.pop('fresh_required', None)
        return self.client.search(**kwargs)

    def extract(self, **kwargs):
        kwargs.pop('fresh_required', None)
        return self.client.extract(**kwargs)


class ExaProvider:
    def __init__(self, api_key):
        self._key = api_key

    def _post(self, endpoint, body, timeout):
        try:
            response = httpx.post('https://api.exa.ai/' + endpoint,
                                  headers={'x-api-key': self._key}, json=body,
                                  timeout=timeout, follow_redirects=False)
        except httpx.TimeoutException:
            raise ProviderError('timeout') from None
        except httpx.RequestError:
            raise ProviderError('network_error') from None
        if not response.is_success:
            code = {401: 'auth_error', 403: 'auth_error', 402: 'quota',
                    429: 'rate_limited'}.get(response.status_code, 'search_failed')
            raise ProviderError(code, response.status_code) from None
        try:
            data = response.json()
        except ValueError:
            raise ProviderError('invalid_response') from None
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            raise ProviderError('invalid_response')
        return data

    def search(self, *, query, max_results=4, timeout=8, country=None,
               include_domains=(), include_domains_mode=None, exclude_domains=(), fresh_required=False, **_):
        from app.rag.web_research import build_research_query
        # Search only discovers URLs. Asking it to fetch page text made Exa
        # slower in the paired measurement; page reading applies freshness.
        body = {'query': build_research_query(query), 'numResults': max_results,
                'type': 'auto', 'contents': {'text': {'maxCharacters': 2000}}}
        if not body['query']:
            raise ProviderError('invalid_query')
        # Preference is broad discovery followed by existing local tier ranking.
        if include_domains and include_domains_mode == 'restrict':
            body['includeDomains'] = list(include_domains)
        elif exclude_domains:
            body['excludeDomains'] = list(exclude_domains)
        if code := country_code(country):
            body['userLocation'] = code
        data = self._post('search', body, timeout)
        return {'results': [dict(title=row.get('title'), url=row.get('url'),
                                content=row.get('text') or '\n'.join(row.get('highlights') or []),
                                score=row.get('score'), published_date=row.get('publishedDate'))
                            for row in data['results'] if isinstance(row, dict)],
                'costDollars': data.get('costDollars')}

    def extract(self, *, urls, timeout=8, fresh_required=False, **_):
        from app.rag.web_research import is_public_guidance_url
        if not urls or any(not is_public_guidance_url(url) for url in urls):
            raise ProviderError('invalid_url')
        data = self._post('contents', {'urls': list(urls),
                          'text': {'verbosity': 'full', 'maxCharacters': 200001},
                          'maxAgeHours': 0 if fresh_required else 24,
                          'livecrawlTimeout': max(1, min(90000, int(timeout * 1000)))}, timeout)
        statuses = {row.get('id'): row for row in data.get('statuses', []) if isinstance(row, dict)}
        rows = {row.get('url'): row for row in data['results'] if isinstance(row, dict)}
        results, failures = [], []
        for url in urls:
            status, row = statuses.get(url, {}), rows.get(url, {})
            if status.get('status') == 'success' and row.get('text'):
                results.append({'url': url, 'title': row.get('title'), 'raw_content': row['text']})
            else:
                failures.append({'url': url, 'error': 'extraction_failed'})
        return {'results': results, 'failed_results': failures, 'costDollars': data.get('costDollars')}


def provider(api_key):
    from app.config import WEB_SEARCH_PROVIDER
    if WEB_SEARCH_PROVIDER == 'exa':
        return ExaProvider(api_key)
    if WEB_SEARCH_PROVIDER == 'tavily':
        return TavilyProvider(api_key)
    raise ProviderError('invalid_provider')


def configured_key(tavily_key=None):
    from app import config
    if config.WEB_SEARCH_PROVIDER == 'exa':
        return config.EXA_API_KEY
    return config.TAVILY_API_KEY if tavily_key is None else tavily_key
