"""Guarded direct fetch for official public pages that Tavily cannot extract.

Some official Malaysian hosts send only their leaf TLS certificate. Browsers
repair the chain through AIA fetching; Python and Tavily reject it, so the page
is never available as evidence. This module is a narrow fallback used only
after Tavily extraction failed or returned clipped text:

* tier-1/2 official hosts and the shared public-URL guard only;
* TLS verification is ALWAYS on; a bundled, publicly issued intermediate set
  only completes chains to the normal ``certifi`` roots;
* every DNS answer must be a public address (no SSRF to private networks);
* redirects are followed manually and each hop is re-validated;
* bounded body size, no cookies/credentials, HTML/PDF/plain text only.

Fetched text is evidence *candidate* text: it still goes through the same
section windowing, assessor and verifier as Tavily pages. It never approves
itself.
"""
from __future__ import annotations

import io
import re
import socket
import ssl
from html.parser import HTMLParser
from ipaddress import ip_address
from pathlib import Path
from time import monotonic
from urllib.parse import urljoin, urlparse

EXTRA_INTERMEDIATES = Path(__file__).with_name("certs") / "extra_intermediates.pem"
MAX_BODY_BYTES = 1_500_000
MAX_REDIRECTS = 3
_USER_AGENT = "Mozilla/5.0 (compatible; FinCoachPublicGuidance/1.0)"
_ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "application/pdf", "text/plain")


def _ssl_context() -> ssl.SSLContext:
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    if EXTRA_INTERMEDIATES.exists():
        context.load_verify_locations(cafile=str(EXTRA_INTERMEDIATES))
    # Defensive: never allow a caller or library default to weaken these.
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _resolves_publicly(host: str) -> bool:
    """Every resolved address must be globally routable."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    for address in addresses:
        try:
            parsed = ip_address(address.split("%", 1)[0])
        except ValueError:
            return False
        if not parsed.is_global:
            return False
    return True


def _allowed_url(url: str) -> bool:
    from app.rag.web_research import classify_tier, is_public_guidance_url
    parsed = urlparse(url)
    return (parsed.scheme == "https" and is_public_guidance_url(url)
            and classify_tier(url) in {1, 2})


class _HtmlToText(HTMLParser):
    """Readable text with Markdown-style headings, list items and links.

    Headings keep a ``#`` prefix and links keep ``[label](url)`` so the existing
    section ranking and observed-link following work exactly as on Tavily
    markdown. Scripts, styles and other non-content elements are dropped;
    menus stay (as in Tavily's raw content) because observed public links are
    how the research loop reaches a profile/functions page. Section ranking
    already prefers substantive windows over navigation.
    """

    _SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "form", "select", "button"}
    _BLOCK = {"p", "div", "section", "article", "main", "table", "tr", "ul", "ol", "br", "dd", "dt", "blockquote"}

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.skip_depth = 0
        self.href: str | None = None
        self.link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")
        elif tag in self._BLOCK:
            self.parts.append("\n\n" if tag != "br" else "\n")
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
                self.href = urljoin(self.base_url, href)
                self.link_text = []

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == "a" and self.href is not None:
            label = " ".join("".join(self.link_text).split())
            if label:
                self.parts.append(f"[{label}]({self.href})")
            self.href = None
        elif re.fullmatch(r"h[1-6]", tag) or tag in self._BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.href is not None:
            self.link_text.append(data)
        else:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _relocate_menus(text: str) -> str:
    """Move runs of link-only/bullet-only lines (menus) to a trailing section.

    Whole lines are moved, never edited, so every remaining sentence is still a
    literal source span. Links stay available for observed-link following.
    """
    lines = text.split("\n")
    is_menu = [bool(re.fullmatch(r"\s*(?:[-*]\s*)?(?:\[[^\]\n]{1,120}\]\([^)\s]+\))?\s*[-|]?\s*", line))
               and line.strip() != "" for line in lines]
    keep, menu, run = [], [], []
    def flush():
        links = [line for line in run if "](" in line]
        (menu if len(links) >= 5 else keep).extend(run if len(links) < 5 else links)
        run.clear()
    for line, menu_line in zip(lines, is_menu):
        if menu_line or (run and not line.strip()):
            run.append(line)
            continue
        flush()
        keep.append(line)
    flush()
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
    if not menu:
        return body
    return body + "\n\n## Page links\n\n" + "\n".join(dict.fromkeys(m.strip() for m in menu))


def html_to_text(html: str, base_url: str) -> str:
    parser = _HtmlToText(base_url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup: keep what was parsed
        pass
    return _relocate_menus(parser.text())


def _pdf_to_text(body: bytes, *, deadline: float | None = None) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(body))
    pages = []
    for page in reader.pages[:40]:
        # Parsing is the expensive half of a PDF fetch. Stop at the deadline
        # rather than continuing to burn request time after the caller moved on.
        if deadline is not None and monotonic() >= deadline:
            break
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(p.strip() for p in pages if p.strip())


def fetch_official_page(url: str, *, timeout: float,
                        deadline: float | None = None) -> str | None:
    """Return readable text for one official public page, or ``None``.

    Never raises. ``None`` covers guard rejection, TLS failure, bot challenge
    (202/empty), non-text content, oversize bodies and network errors.

    ``deadline`` is an absolute ``monotonic`` instant shared with the caller. It is
    checked while the body is streamed and again before PDF parsing, so a slow
    response or a slow parser stops early instead of outliving the request budget.
    The caller also runs this on daemon threads: a blocking socket read cannot be
    cancelled cooperatively, so daemon threads are the backstop that keeps a stuck
    fetch from holding the process open.
    """
    if timeout < 1:
        return None
    expired = (lambda: deadline is not None and monotonic() >= deadline)
    current = str(url or "").strip()
    if not _allowed_url(current):
        return None
    try:
        import httpx
    except ImportError:
        return None
    try:
        context = _ssl_context()
        with httpx.Client(verify=context, follow_redirects=False, trust_env=False,
                          timeout=httpx.Timeout(timeout), headers={
                              "User-Agent": _USER_AGENT,
                              "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,text/plain;q=0.8",
                              "Accept-Language": "en,ms;q=0.8",
                          }) as client:
            for _ in range(MAX_REDIRECTS + 1):
                if expired():
                    return None
                host = urlparse(current).hostname or ""
                if not _allowed_url(current) or not _resolves_publicly(host):
                    return None
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(current, location).split("#", 1)[0]
                        continue
                    if response.status_code != 200:
                        return None  # includes WAF/bot challenges (202, 403)
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type and content_type not in _ALLOWED_TYPES:
                        return None
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
                        return None
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BODY_BYTES:
                            return None
                        if expired():
                            return None
                    encoding = response.encoding or "utf-8"
                break
            else:
                return None
    except Exception:
        return None
    if expired() or not body:
        return None
    if content_type == "application/pdf" or bytes(body[:5]) == b"%PDF-":
        try:
            text = _pdf_to_text(bytes(body), deadline=deadline)
        except Exception:
            return None
    else:
        decoded = bytes(body).decode(encoding, errors="replace")
        if decoded.count("\ufffd") > 3:
            # Some official CMS pages declare UTF-8 but send Windows-1252.
            alternative = bytes(body).decode("cp1252", errors="replace")
            if alternative.count("\ufffd") < decoded.count("\ufffd"):
                decoded = alternative
        text = html_to_text(decoded, current) if "<" in decoded[:2000] else decoded.strip()
    # A near-empty shell (JS-only app, challenge page) is not usable evidence.
    return text if len(re.findall(r"[^\W\d_]{3,}", text)) >= 25 else None
