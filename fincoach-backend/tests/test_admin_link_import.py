import unittest
from unittest.mock import MagicMock, patch

from app.admin.link_import import extract_link


class LinkImportTests(unittest.TestCase):
    def test_reject_private_targets_before_provider_call(self):
        with patch('app.admin.link_import._resolves_publicly', return_value=False), patch('tavily.TavilyClient') as client:
            for url in ('http://127.0.0.1', 'http://localhost', 'file:///secret', 'https://user:pass@example.org'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    extract_link(url, 'test-key')
            client.assert_not_called()

    def test_full_page_is_not_research_snippet(self):
        text = '# Financial guide\n' + 'Budget safely. ' * 1000
        client = MagicMock()
        client.extract.return_value = {'results': [{'url': 'https://example.org/guide', 'raw_content': text}]}
        with patch('app.admin.link_import._resolves_publicly', return_value=True), patch('tavily.TavilyClient', return_value=client):
            result = extract_link('https://example.org/guide', 'test-key')
        self.assertEqual(result['content'], text.strip())
        self.assertEqual(result['title'], 'Financial guide')
        self.assertNotIn('query', client.extract.call_args.kwargs)

    def test_empty_failed_or_oversized_extraction_is_rejected(self):
        for content in ('x' * 200001, 'unsafe\x00content'):
            client = MagicMock()
            client.extract.return_value = {'results': [{'url': 'https://example.org', 'raw_content': content}]}
            with patch('app.admin.link_import._resolves_publicly', return_value=True), patch('tavily.TavilyClient', return_value=client), self.assertRaises(ValueError):
                extract_link('https://example.org', 'test-key')

    def test_provider_failure_uses_public_page_fallback(self):
        url = 'https://www.investopedia.com/terms/f/finance.asp'
        client = MagicMock()
        client.extract.side_effect = RuntimeError('provider error')
        page = {'title': 'Finance', 'content': 'A complete financial article.'}
        with patch('app.admin.link_import._resolves_publicly', return_value=True), \
             patch('tavily.TavilyClient', return_value=client), \
             patch('app.admin.link_import.fetch_public_webpage', return_value=page) as fallback:
            result = extract_link(url, 'test-key')
        self.assertEqual(result, {**page, 'source_urls': [url]})
        fallback.assert_called_once_with(url)

    def test_failed_results_and_missing_key_use_fallback(self):
        page = {'title': 'Guide', 'content': 'Readable page content.'}
        client = MagicMock()
        client.extract.return_value = {'results': [], 'failed_results': [{'error': 'blocked'}]}
        with patch('app.admin.link_import._resolves_publicly', return_value=True), \
             patch('tavily.TavilyClient', return_value=client), \
             patch('app.admin.link_import.fetch_public_webpage', return_value=page) as fallback:
            self.assertEqual(extract_link('https://example.org/guide', 'test-key')['content'], page['content'])
            self.assertEqual(extract_link('https://example.org/guide', '')['content'], page['content'])
        self.assertEqual(fallback.call_count, 2)

    def test_fallback_failure_is_actionable_without_exposing_provider_error(self):
        client = MagicMock()
        client.extract.side_effect = RuntimeError('secret provider detail')
        with patch('app.admin.link_import._resolves_publicly', return_value=True), \
             patch('tavily.TavilyClient', return_value=client), \
             patch('app.admin.link_import.fetch_public_webpage', return_value=None):
            with self.assertRaises(RuntimeError) as caught:
                extract_link('https://example.org/guide', 'test-key')
        self.assertNotIn('secret provider detail', str(caught.exception))
        self.assertIn('Upload', str(caught.exception))
