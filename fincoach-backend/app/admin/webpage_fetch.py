"""Fetch a public webpage without allowing redirects into private networks."""

import ipaddress
import re
import socket
import ssl
import time
from email.message import Message
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import certifi
import urllib3.connection
import urllib3.exceptions

from app.admin.documents import MAX_CONTENT_CHARS

MAX_BODY_BYTES = 1_500_000
MAX_REDIRECTS = 3
FETCH_TIMEOUT = 20.0
_VOID = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                   'link', 'meta', 'param', 'source', 'track', 'wbr'})


def _parse_public_url(url):
    """Reject credentials and unusual ports on the original URL and every redirect."""
    try:
        parsed = urlsplit(url)
        if (len(url) > 2048 or parsed.scheme not in {'http', 'https'}
                or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 80, 443}
                or any(ord(char) < 32 or ord(char) == 127 for char in url)):
            return None
        return parsed
    except (ValueError, UnicodeError):
        return None


def _public_addresses(host, port):
    """Resolve once, rejecting the entire set if any address is not public."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError('Host did not resolve')
    for family, _, _, _, sockaddr in infos:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            raise ValueError('Unsupported address family')
        address = ipaddress.ip_address(sockaddr[0].split('%', 1)[0])
        mapped = getattr(address, 'ipv4_mapped', None)
        if (not address.is_global or address.is_multicast
                or (mapped and (not mapped.is_global or mapped.is_multicast))):
            raise ValueError('Host resolved to a non-public address')
    return infos


def _connect_pinned(infos, deadline):
    """Connect to the validated socket address, without a second DNS lookup."""
    last_error = None
    for family, socktype, proto, _, sockaddr in infos:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Fetch timed out')
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(remaining)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    raise last_error or OSError('No usable public address')


def _connection(parsed, infos, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Fetch timed out')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if parsed.scheme == 'https':
        # Verify the original hostname even though _new_conn pins the socket to
        # an address from the validated DNS result.
        conn = urllib3.connection.HTTPSConnection(parsed.hostname, port, timeout=remaining,
                                                  cert_reqs=ssl.CERT_REQUIRED,
                                                  ca_certs=certifi.where())
    else:
        conn = urllib3.connection.HTTPConnection(parsed.hostname, port, timeout=remaining)
    conn._new_conn = lambda: _connect_pinned(infos, deadline)
    return conn


class _PageText(HTMLParser):
    """Collect article/main/body text while excluding non-content elements."""

    _SKIP = frozenset({'script', 'style', 'noscript', 'template', 'svg', 'iframe',
                       'nav', 'aside', 'footer', 'form', 'button', 'select'})
    _BLOCK = frozenset({'p', 'div', 'section', 'article', 'main', 'table', 'tr',
                        'ul', 'ol', 'blockquote', 'dd', 'dt'})
    _AD = re.compile(r'(?:^|[\s_-])(?:advertisement|adslot|newsletter)(?:$|[\s_-])', re.I)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = {'body': 0, 'main': 0, 'article': 0}
        self.parts = {'body': [], 'main': [], 'article': []}
        self.skip = 0
        self.in_title = False
        self.title = []

    def _append(self, value):
        for scope, depth in self.depth.items():
            if depth:
                self.parts[scope].append(value)

    def handle_starttag(self, tag, attrs):
        if tag == 'title' and not self.skip:
            self.in_title = True
        if self.skip:
            if tag not in _VOID:
                self.skip += 1
            return
        attributes = dict(attrs)
        hidden = ('hidden' in attributes or str(attributes.get('aria-hidden') or '').lower() == 'true')
        names = (attributes.get('id') or '') + ' ' + (attributes.get('class') or '')
        if tag in self._SKIP or hidden or self._AD.search(names):
            if tag not in _VOID:
                self.skip = 1
            return
        if tag in self.depth:
            self.depth[tag] += 1
        if re.fullmatch(r'h[1-6]', tag):
            self._append('\n\n' + '#' * int(tag[1]) + ' ')
        elif tag == 'li':
            self._append('\n- ')
        elif tag in {'td', 'th'}:
            self._append(' | ')
        elif tag == 'br':
            self._append('\n')
        elif tag in self._BLOCK:
            self._append('\n\n')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1
            return
        if tag == 'title':
            self.in_title = False
        if re.fullmatch(r'h[1-6]', tag) or tag in self._BLOCK:
            self._append('\n\n')
        if tag in self.depth:
            self.depth[tag] = max(0, self.depth[tag] - 1)

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
        self._append(data)

    def result(self):
        title = ' '.join(''.join(self.title).split())[:200]
        for scope in ('article', 'main', 'body'):
            text = ''.join(self.parts[scope])
            text = re.sub(r'[ \t\r\f\v]+', ' ', text)
            text = re.sub(r' *\n *', '\n', text)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            if len(re.findall(r'[^\W\d_]{3,}', text)) >= 25:
                return title, text
        return title, ''


def fetch_public_webpage(url):
    """Return a bounded public article, or None when it cannot be safely read."""
    deadline = time.monotonic() + FETCH_TIMEOUT
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            parsed = _parse_public_url(current)
            if not parsed:
                return None
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            infos = _public_addresses(parsed.hostname, port)
            conn = _connection(parsed, infos, deadline)
            try:
                path = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
                path = quote(path, safe="/%:@?&=+$,;~!()*'-._")
                conn.request('GET', path, headers={
                    'User-Agent': 'FinCoachKnowledgeImport/1.0',
                    'Accept': '*/*',
                    'Accept-Encoding': 'identity',
                    'Connection': 'keep-alive',
                }, preload_content=False, decode_content=False)
                sock = conn.sock
                response = conn.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get('Location')
                    if not location:
                        return None
                    following = urljoin(current, location).split('#', 1)[0]
                    next_parsed = _parse_public_url(following)
                    if not next_parsed or (parsed.scheme == 'https' and next_parsed.scheme != 'https'):
                        return None
                    current = following
                    continue
                if response.status != 200 or response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    return None
                content_type = response.headers.get('Content-Type', '')
                metadata = Message()
                metadata['content-type'] = content_type
                media_type = metadata.get_content_type() if content_type else ''
                if media_type not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
                    return None
                declared = response.headers.get('Content-Length')
                if declared and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
                    return None
                body = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    if sock is not None:
                        sock.settimeout(remaining)
                    chunk = response.read1(min(65536, MAX_BODY_BYTES + 1 - len(body)), decode_content=False)
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > MAX_BODY_BYTES:
                        return None
                if not body or (declared and len(body) != int(declared)):
                    return None
                encoding = metadata.get_content_charset() or 'utf-8'
                decoded = bytes(body).decode(encoding, errors='replace')
                if '\x00' in decoded:
                    return None
                if media_type == 'text/plain':
                    title, text = '', decoded.strip()
                else:
                    parser = _PageText()
                    parser.feed(decoded)
                    parser.close()
                    title, text = parser.result()
                if (not text or len(text) > MAX_CONTENT_CHARS
                        or len(re.findall(r'[^\W\d_]{3,}', text)) < 25):
                    return None
                # Challenge pages can return HTTP 200 but contain no article.
                if re.search(r'^(just a moment|access denied|attention required)', title, re.I):
                    return None
                return {'title': title, 'content': text}
            finally:
                conn.close()
    except (OSError, ValueError, UnicodeError, LookupError, urllib3.exceptions.HTTPError):
        return None
    return None
