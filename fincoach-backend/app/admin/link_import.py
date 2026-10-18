"""Import a complete public page, without research query/snippet truncation."""
import re
from urllib.parse import urlparse, unquote

from app.admin.documents import MAX_CONTENT_CHARS
from app.rag.public_fetch import _resolves_publicly


def extract_link(url: str, api_key: str) -> dict:
    parsed = urlparse(url)
    # Extraction goes through the provider, never an unrestricted local fetch.
    # Reject local targets and credentials before sending URLs to that provider.
    if (len(url) > 2048 or parsed.scheme not in {"https", "http"}
            or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 80, 443}
            or not _resolves_publicly(parsed.hostname)):
        raise ValueError("Enter a public HTTP or HTTPS webpage link without login details.")
    if not api_key:
        raise RuntimeError("Link import is unavailable. Upload a file instead.")
    from tavily import TavilyClient
    try:
        response = TavilyClient(api_key=api_key).extract(
            urls=[url], extract_depth="advanced", format="markdown", timeout=30)
    except Exception as exc:
        raise RuntimeError("The webpage could not be imported. Retry or upload its document instead.") from exc
    items = response.get("results") or []
    item = next((row for row in items if row.get("url") == url), None)
    content = str((item or {}).get("raw_content") or "").strip()
    # Never quietly index a clipped prefix: reject oversized/empty extraction.
    if not content or "\x00" in content or len(content) > MAX_CONTENT_CHARS:
        raise ValueError("The page has no readable content or exceeds 200,000 characters. Upload a smaller document instead.")
    heading = re.search(r"^#\s+(.+)$", content, re.M)
    title = str((item or {}).get("title") or (heading.group(1) if heading else
                unquote(parsed.path.rstrip('/').split('/')[-1]).replace('-', ' ') or parsed.hostname))[:200]
    return dict(title=title, content=content, source_urls=[url])
