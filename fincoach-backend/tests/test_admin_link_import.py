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
        for content in ('', 'x' * 200001):
            client = MagicMock()
            client.extract.return_value = {'results': [{'url': 'https://example.org', 'raw_content': content}]}
            with patch('app.admin.link_import._resolves_publicly', return_value=True), patch('tavily.TavilyClient', return_value=client), self.assertRaises(ValueError):
                extract_link('https://example.org', 'test-key')
