"""Import a complete public page, without research query/snippet truncation."""
import re
from urllib.parse import urlparse, unquote

from app.admin.documents import MAX_CONTENT_CHARS
from app.admin.webpage_fetch import fetch_public_webpage
from app.rag.public_fetch import _resolves_publicly


def extract_link(url: str, api_key: str) -> dict:
    try:
        parsed = urlparse(url)
        valid = (len(url) <= 2048 and parsed.scheme in {"https", "http"}
                 and parsed.hostname and parsed.username is None and parsed.password is None
                 and parsed.port in {None, 80, 443} and _resolves_publicly(parsed.hostname))
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise ValueError("Enter a public HTTP or HTTPS webpage link without login details.")

    item = None
    if api_key:
        try:
            from tavily import TavilyClient
            response = TavilyClient(api_key=api_key).extract(
                urls=[url], extract_depth="advanced", format="markdown", timeout=30)
            item = next((row for row in (response.get("results") or []) if row.get("url") == url), None)
        except Exception:
            # A provider failure does not prevent an independently guarded fetch.
            item = None
    content = str((item or {}).get("raw_content") or "").strip()
    # Never quietly index a clipped prefix or accept malformed provider text.
    if "\x00" in content or len(content) > MAX_CONTENT_CHARS:
        raise ValueError("The page has no readable content or exceeds 200,000 characters. Upload a smaller document instead.")
    if not content:
        page = fetch_public_webpage(url)
        if page is None:
            raise RuntimeError("The webpage could not be imported. The site may block access or have no readable text. Upload a text-based document instead.")
        content = page["content"]
        item = page
    heading = re.search(r"^#\s+(.+)$", content, re.M)
    title = str((item or {}).get("title") or (heading.group(1) if heading else
                unquote(parsed.path.rstrip('/').split('/')[-1]).replace('-', ' ') or parsed.hostname))[:200]
    return dict(title=title, content=content, source_urls=[url])
