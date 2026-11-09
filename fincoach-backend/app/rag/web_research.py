"""Web-research fallback: search the open web when the corpus cannot answer.

This is a *fallback*, invoked only when internal RAG retrieval is inadequate for
a knowledge-route question (see the trigger in ``CoachingService.send_message``).
Corpus is always tried first and is never discarded — web evidence *augments* it
(see ``merge_evidence``), it does not replace it.

Results are ranked into trust tiers by domain and adapted into ``RetrievedChunk``
objects so they flow through the SAME citation + grounding + verifier machinery as
corpus chunks — the web path gets no private exemption from the guards. A claim
with no supporting fetched text fails closed exactly like an unsupported corpus
claim.

Trust tiers (highest -> lowest):
  1 government / regulatory     -> confidence "established"
  2 official institution        -> confidence "established"
  3 reputable publication       -> confidence "reported"
  4 academic                    -> confidence "reported"
  5 community / forum            -> confidence "anecdotal"  (only KNOWN hosts)
  None unclassified/unknown      -> confidence "insufficient"

An unknown domain is NOT dressed up as tier 5. Tier 5 is reserved for hosts we
positively recognise as community/forum (Reddit, Lowyat, ...); anything we cannot
classify maps to ``tier=None`` / ``confidence="insufficient"`` so it can never be
presented as established, reported, OR anecdotal fact.

Privacy (invariant #7): only a de-identified *topic* query
(``build_research_query``) is ever sent to Tavily. Raw conversation history,
names, amounts, account/reference numbers, emails, and phone numbers are stripped
before any network call.
"""

from __future__ import annotations

import re
from hashlib import sha256
from time import monotonic
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal, TYPE_CHECKING

from app.config import WEB_SEARCH_DEFAULT_COUNTRY
from urllib.parse import urlparse, urljoin, parse_qsl, unquote
from ipaddress import ip_address
from math import isfinite

from app.rag.retrieval import RetrievedChunk

if TYPE_CHECKING:
    from app.rag.public_source_store import PublicSourcePage


# ---- Domain -> tier tables ---------------------------------------------------
# Matched most-trusted first. Suffix rules (``.gov.my``, ``.edu``) cover whole
# families; explicit sets cover well-known named domains. An unmatched host is
# UNKNOWN (tier None), not tier 5.

_GOV_SUFFIXES = (".gov.my", ".gov", ".mil")
_GOV_HOSTS = frozenset({
    "bnm.gov.my",        # Bank Negara Malaysia
    "lhdn.gov.my",       # Inland Revenue (LHDN)
    "hasil.gov.my",      # LHDN e-filing
    "kwsp.gov.my",       # EPF
    "perkeso.gov.my",    # SOCSO
    "pidm.gov.my",       # Deposit insurance
    "mof.gov.my",        # Ministry of Finance
    "sc.com.my",         # Securities Commission Malaysia
    "bursamalaysia.com", # Exchange (regulated market operator)
    "akpk.org.my",       # AKPK — credit counselling agency, a BNM subsidiary
})

# Tier 2 = licensed commercial financial entities' OWN official domains (banks,
# licensed digital banks, SC-licensed investment managers). Trusted for factual
# product attributes (fees, minimums, eligibility, mechanics, licensing/Shariah
# status) — NOT for promotional or performance claims, and never to override a
# statutory rate from a tier-1 source. The prompt enforces that scope.
#
# Inclusion criterion: verifiable on the SC Malaysia register of licence holders
# OR the BNM financial-participants directory; NOT on the SC Investor Alert / BNM
# Consumer Alert list; canonical apex domain only. Verify before adding.
_OFFICIAL_INSTITUTIONS = frozenset({
    "maybank2u.com.my", "maybank.com", "cimb.com.my", "cimbbank.com.my",
    "publicbank.com.my", "pbebank.com", "rhbgroup.com", "hongleongbank.com.my",
    "ambank.com.my", "bankislam.com", "bankrakyat.com.my", "affinbank.com.my",
    "alliancebank.com.my", "hsbc.com.my", "ocbc.com.my", "uob.com.my",
    "standardchartered.com.my", "tnbc.com.my", "touchngo.com.my", "boost.my",
    "grab.com", "bigpay.com.my", "principal.com.my", "publicmutual.com.my",
    # Verified 2026-09-19 against each entity's own official site:
    "stashaway.my",      # StashAway Malaysia Sdn Bhd — SC DIM (eCMSL/A0352/2018)
    "gxbank.my",         # GX Bank Berhad — BNM digital bank, PIDM member
    "aeonbank.com.my",   # AEON Bank — BNM Islamic digital bank, PIDM member
    "kenanga.com.my",    # Kenanga Investment Bank — SC-licensed investment bank
    # Verified against SC register + Investor Alert clearance (2026-09-19):
    "versa.com.my",      # Versa Asia Sdn Bhd — SC RMO e-Services Platform
    "wahed.com",         # Wahed Technologies Sdn Bhd — SC DIM (primary apex)
    "wahedinvest.com",   # Wahed — legacy/redirect apex, same entity
    "digitalinvesting.com.my",  # Kenanga Digital Investing (KDI) product portal
})

_REPUTABLE_PUBLICATIONS = frozenset({
    "thestar.com.my", "nst.com.my", "theedgemarkets.com", "theedgemalaysia.com",
    "freemalaysiatoday.com", "malaymail.com", "bernama.com", "reuters.com",
    "bloomberg.com", "bbc.com", "cnbc.com", "ft.com", "channelnewsasia.com",
    "thestar.com", "businesstoday.com.my", "focusmalaysia.my",
})

_ACADEMIC_SUFFIXES = (".edu", ".edu.my", ".ac.uk", ".ac.my")
_ACADEMIC_HOSTS = frozenset({
    "doi.org", "arxiv.org", "ssrn.com", "jstor.org", "springer.com",
    "sciencedirect.com", "tandfonline.com", "scholar.google.com",
})

# Hosts positively known to be community/forum. Only these map to tier 5.
_COMMUNITY_HOSTS = frozenset({
    "reddit.com", "lowyat.net", "quora.com", "medium.com", "blogspot.com",
    "wordpress.com", "facebook.com", "twitter.com", "x.com", "youtube.com",
    "tiktok.com", "cari.com.my", "mycen.com.my",
})

_TIER_CONFIDENCE = {
    1: "established",
    2: "established",
    3: "reported",
    4: "reported",
    5: "anecdotal",
}

_TIER_LABEL = {
    1: "government / regulatory",
    2: "official institution",
    3: "reputable publication",
    4: "academic",
    5: "community / forum",
}

# Domains the search is biased toward (Tavily `include_domains` + `prefer` mode):
# every known-trustworthy finance host (tier 1-3). "prefer" favours these without
# excluding others, so a legitimate site not yet on the list still surfaces — it
# just ranks below a trusted one. Paired with `topic="finance"` this steers the
# open-web search toward financial sources instead of arbitrary pages, without
# caging it to the allowlist.
_PREFERRED_DOMAINS = tuple(
    sorted(_GOV_HOSTS | _OFFICIAL_INSTITUTIONS | _REPUTABLE_PUBLICATIONS)
)

# Data brokers / scrapers that soak up result slots with no finance value. Kept
# out of pass 2 (the un-caged fallback), where they otherwise surface.
_EXCLUDED_DOMAINS = (
    "rocketreach.co", "zoominfo.com", "crunchbase.com", "pitchbook.com",
    "leadiq.com", "signalhire.com", "apollo.io",
)

# Two-pass search tuning. Pass 1 is caged to trusted finance domains; pass 2 (the
# un-caged regional fallback) fires ONLY when pass 1 is this thin, so the second
# API call is spent only on genuine edge cases (breaking news, a brand-new
# platform not yet on the allowlist).
_MIN_CAGED_RESULTS = 2

# The lowest tier that may back a factual provider/product name. Retained for the
# deterministic guard's history; the *prompt* rule is widened to any cited source
# in Task 6, which owns this constant's fate.
NAMED_PRODUCT_MAX_TIER = 2

# Sort sentinel so an unknown (None) tier ranks below every classified tier.
_UNKNOWN_TIER_RANK = 99

# Per-passage cap on extracted page text so one long page cannot dominate the
# verifier's single-batch context budget. merge_evidence caps the total.
_MAX_PASSAGE_CHARS = 2000
# Total merged evidence budget (corpus + web). Corpus is primary and kept whole;
# web is added in tier order until this ceiling would be exceeded.
_MAX_MERGED_CHARS = 12000
# Cap on the de-identified query length sent to Tavily.
_MAX_QUERY_CHARS = 300


def _host(url: str) -> str:
    """Return the bare lower-case host of a URL, without ``www.`` or port."""
    netloc = urlparse(str(url or "")).netloc.lower()
    if "@" in netloc:  # strip any userinfo
        netloc = netloc.rsplit("@", 1)[1]
    host = netloc.split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def is_public_guidance_url(url: str) -> bool:
    """Shared eligibility for public guidance URLs; no credentials/identifiers."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return False
        if host == "localhost" or "." not in host or host.endswith((".local", ".internal", ".localhost")):
            return False
        if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", unquote(host), re.I):
            return False
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            return False
        items = parse_qsl(parsed.query, keep_blank_values=True)
        if parsed.query and not _public_query_allowed(parsed, items):
            return False
        return not bool(re.search(r"(?:login|signin|logout|submit|callback|oauth)", parsed.path, re.I))
    except (ValueError, TypeError):
        return False


def _public_query_allowed(parsed: Any, items: list[tuple[str, str]]) -> bool:
    """Allow public CMS selectors without opening arbitrary identifier URLs.

    Official portals commonly use PHP navigation/document selectors. Only
    bounded observed public routes qualify; account IDs, credentials and
    unknown parameters remain excluded, including on official domains.
    """
    ordinary = {"lang", "language", "page", "year"}
    if items and all(k.casefold() in ordinary and re.fullmatch(r'[a-zA-Z0-9-]{1,12}', v)
                     for k, v in items):
        return True
    # Tier 2 includes commercial banks: reputation is not permission to send
    # account/document identifiers. This exception is for government CMS only.
    government_host = (parsed.hostname or '').casefold().endswith('.gov.my')
    if not items or not government_host:
        return False
    values = {k.casefold(): v for k, v in items}
    if len(values) != len(items):
        return False
    if parsed.path.casefold().endswith(('/get_dl.php', '/get_url.php')):
        # Public government CMS document/link selectors are numeric only;
        # arbitrary URLs, credentials and additional parameters stay forbidden.
        return set(values) == {'id'} and bool(re.fullmatch(r'[0-9]{1,8}', values['id']))
    public_navigation = (parsed.path in {'', '/'} or parsed.path.casefold().endswith('/main.php'))
    public_sections = {'profil', 'profile', 'info', 'fungsi', 'function', 'functions',
                       'cawang', 'bahagian', 'division', 'perkhidmatan', 'services',
                       'dokumen', 'documents', 'faq', 'soalan', 'berita', 'news', 'galeri'}
    return bool(public_navigation and values.get('pg', '').casefold() in public_sections
        and set(values) <= ordinary | {'pg', 'list', 'type', 'id'}
        and all(re.fullmatch(r'[0-9]{1,8}' if k == 'id' else r'[a-zA-Z0-9_-]{1,32}', v)
                for k, v in values.items()))


def linked_guidance_urls(page_url: str, markdown: str, *, subject_query: str,
                         part_label: str, visited: frozenset[str]) -> tuple[str, ...]:
    """Rank only observed public links; links never inherit a parent's trust."""
    stop = {"the", "and", "for", "how", "what", "required", "malaysia", "application", "programme"}
    words = lambda text: set(re.findall(r"[^\W_]+", text.casefold())) - stop
    subject, gap = words(subject_query), words(part_label)
    if gap & {"documents", "document"}:
        gap.update({"dokumen", "sokongan"})
    if gap & {"eligibility", "qualifies", "eligible"}:
        gap.update({"syarat", "kelayakan"})
    candidates = {}
    for label, target in re.findall(r"\[([^\]\n]{1,250})\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", markdown[:100_000]):
        url = urljoin(page_url, target).split("#", 1)[0]
        if not is_public_guidance_url(url):
            continue
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            continue
        if host == "localhost" or "." not in host or host.endswith((".local", ".internal", ".localhost")):
            continue
        if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", unquote(host), re.I):
            continue  # Shortened/octal/hex numeric addresses are not DNS hosts.
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            continue  # No literal addresses, including numeric public targets.
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        if parsed.query and not _public_query_allowed(parsed, query_items):
            continue
        if re.search(r"(?:login|signin|logout|submit|callback|oauth)", parsed.path, re.I) or url in visited:
            continue
        terms = words(label + " " + unquote(parsed.path))
        gap_score, subject_score = len(gap & terms), len(subject & terms)
        same_host = host == (urlparse(page_url).hostname or "")
        # A same-institution document can inherit subject relevance, never its
        # factual authority. Cross-host links must name the actual subject.
        if gap_score and (subject_score or same_host):
            candidates[url] = (gap_score, subject_score)
    return tuple(sorted(candidates, key=lambda url: candidates[url], reverse=True)[:4])


def _host_or_suffix_in(host: str, hosts: frozenset[str]) -> bool:
    """Match an exact host or any of its parent domains against ``hosts``."""
    parts = host.split(".")
    return any(".".join(parts[i:]) in hosts for i in range(len(parts)))


def classify_tier(url: str) -> int | None:
    """Map a URL to a trust tier 1..5, or ``None`` when unclassifiable.

    Unknown domains return ``None`` (confidence "insufficient"), NOT tier 5.
    Tier 5 is reserved for hosts positively known to be community/forum.
    """
    host = _host(url)
    if not host:
        return None
    if host.endswith(_GOV_SUFFIXES) or _host_or_suffix_in(host, _GOV_HOSTS):
        return 1
    if _host_or_suffix_in(host, _OFFICIAL_INSTITUTIONS):
        return 2
    if _host_or_suffix_in(host, _REPUTABLE_PUBLICATIONS):
        return 3
    if host.endswith(_ACADEMIC_SUFFIXES) or _host_or_suffix_in(host, _ACADEMIC_HOSTS):
        return 4
    if _host_or_suffix_in(host, _COMMUNITY_HOSTS):
        return 5
    return None  # unknown/unclassified -> insufficient, never dressed as fact


def tier_to_confidence(tier: int | None) -> str:
    """Map a trust tier to one of the four confidence classes.

    An unknown tier (``None``) is "insufficient" — it establishes nothing.
    """
    if tier is None:
        return "insufficient"
    return _TIER_CONFIDENCE.get(tier, "insufficient")


def tier_label(tier: int | None) -> str:
    if tier is None:
        return "unclassified source"
    return _TIER_LABEL.get(tier, "unclassified source")


def is_named_product_allowed(tier: int | None) -> bool:
    """A provider/product may be named only when a tier-1/2 source backs it.

    NOTE: superseded at the prompt layer by Task 6 (factual naming from any cited
    source). Retained for the deterministic-guard history; not used to gate the
    prompt rule any more.
    """
    return tier is not None and tier <= NAMED_PRODUCT_MAX_TIER


# ---- De-identified query builder (invariant #7) ------------------------------

# A sign-off cue and everything after it is dropped (that is where names/refs
# tend to live: "Regards, Ahmad, ref 5234").
_SIGNOFF = re.compile(
    r"\b(?:regards|kind\s+regards|warm\s+regards|best\s+regards|best\s+wishes|"
    r"best|thanks|thank\s+you|sincerely|cheers|"
    r"yours(?:\s+truly|\s+sincerely|\s+faithfully)?|salam|terima\s+kasih)\b.*",
    re.IGNORECASE | re.DOTALL,
)
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_PHONE = re.compile(r"\+?\d[\d\s\-]{6,}\d")
_REF_NUMBER = re.compile(
    r"\b(?:ref|reference|acct|account|acc|no|id|nric|ic|member(?:ship)?)\b"
    r"\.?\s*[:#]?\s*[\w-]*\d[\w-]*",
    re.IGNORECASE,
)
_RM_AMOUNT = re.compile(r"\bRM\s?\d[\d,]*(?:\.\d{1,2})?", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\b\d{5,}\b")  # phone/account/ref runs
_WS = re.compile(r"\s+")


def build_research_query(question: str) -> str:
    """Produce a de-identified topic query safe to send to a web search API.

    Strips sign-off blocks (and the names/refs that trail them), emails, phone
    numbers, reference/account numbers, RM amounts, and long digit runs, then
    collapses whitespace and caps length. Only the current question is used —
    never conversation history — so no prior turns leave the server.

    This is a conservative topic extractor, not a certified PII scrubber: plain
    years and small in-topic numbers (e.g. "EPF dividend 2024") are preserved so
    the query stays useful. Returns ``""`` when nothing usable survives.
    """
    text = str(question or "")
    text = _SIGNOFF.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _REF_NUMBER.sub(" ", text)
    text = _RM_AMOUNT.sub(" ", text)
    text = _PHONE.sub(" ", text)
    text = _LONG_DIGITS.sub(" ", text)
    text = _WS.sub(" ", text).strip(" ,.;:-")
    return text[:_MAX_QUERY_CHARS].strip()


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    content: str
    score: float | None
    published_date: str | None = None


@dataclass(frozen=True)
class ResearchOutcome:
    """Typed result of a research pass: merged-ready chunks + why web ran (or not)."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    web_ran: bool = False
    reason: str = "not_attempted"
    extraction_reason: str | None = None


@dataclass
class WebResearchCache:
    """Request-local public evidence only; bounded by the policy's three rounds."""

    searches: dict[tuple, tuple[WebResult, ...]] = field(default_factory=dict)
    passages: dict[tuple[str, str, str, bool, str], str] = field(default_factory=dict)
    full_pages: dict[str, str] = field(default_factory=dict)
    fetched_pages: dict[str, PublicSourcePage] = field(default_factory=dict)
    public_source_diagnostics: dict[str, Any] = field(default_factory=dict)
    search_calls: int = 0
    extract_calls: int = 0
    # One bounded batch can use one independently billed Tavily request per URL.
    tavily_extract_requests: int = 0
    # Guarded official-page fetches after a failed/clipped Tavily extraction.
    # Free of Tavily credit, so counted separately but capped per request.
    direct_fetches: int = 0
    cache_hits: int = 0
    credits: float | None = None
    last_error: str | None = None
    # Bounded operational metadata only: never page text or provider messages.
    extraction_events: list[dict[str, Any]] = field(default_factory=list)
    # Request-local normalized search identities; diagnostic events hold hashes,
    # not proposed or owner-derived search text.
    sent_searches: set[str] = field(default_factory=set)
    skipped_searches: list[dict[str, str]] = field(default_factory=list)
    privacy_skips: list[dict[str, bool]] = field(default_factory=list)
    exa_cost_dollars: float | None = None
    fresh_required: bool = False

    def note_usage(self, response: Any) -> None:
        usage = response.get("usage") if isinstance(response, dict) else None
        credits = usage.get("credits") if isinstance(usage, dict) else None
        if type(credits) in (int, float) and isfinite(credits) and credits >= 0:
            self.credits = (self.credits or 0) + credits
        cost = response.get('costDollars') if isinstance(response, dict) else None
        dollars = cost.get('total') if isinstance(cost, dict) else None
        if type(dollars) in (int, float) and isfinite(dollars) and dollars >= 0:
            self.exa_cost_dollars = (self.exa_cost_dollars or 0) + dollars


def _extraction_url(url: str) -> str:
    """Retain the public page address without credentials or arbitrary query data."""
    try:
        parsed = urlparse(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "[invalid URL]"
        host = parsed.hostname
        if parsed.port:
            host += f":{parsed.port}"
        # The existing public-URL guard admits only bounded public selectors.
        query = f"?{parsed.query}" if parsed.query and is_public_guidance_url(url) else ""
        return f"{parsed.scheme}://{host}{parsed.path}{query}"
    except (ValueError, TypeError):
        return "[invalid URL]"


def _extraction_method() -> str:
    from app.config import WEB_SEARCH_PROVIDER
    return WEB_SEARCH_PROVIDER if WEB_SEARCH_PROVIDER in {'exa', 'tavily'} else 'unknown'


def _extraction_event(cache: WebResearchCache | None, url: str, method: str,
                      success: bool, error_type: str | None = None, *, attempted: bool = True,
                      elapsed_seconds: float = 0.0) -> None:
    if cache is not None:
        cache.extraction_events.append({"url": _extraction_url(url), "method": method,
            "attempted": attempted, "success": success, "error_type": error_type,
            "elapsed_ms": round(max(0.0, elapsed_seconds) * 1000, 1)})


def _provider_extract_error(value: Any) -> str:
    """Classify a provider failure without recording the untrusted message."""
    if isinstance(value, dict):
        value = value.get("type") or value.get("code") or value.get("message")
    if isinstance(value, str):
        if value in {'auth_error', 'quota', 'rate_limited', 'timeout', 'network_error', 'extraction_failed'}:
            return value
        if re.search(r"\b(?:timeout|timed out)\b", value, re.I):
            return "timeout"
        status = re.search(r"\b(?:HTTP\s*)?([45]\d\d)\b", value, re.I)
        if status:
            return f"http_{status.group(1)}"
    return "provider_reported_failure"


def _safe_error(error: Exception) -> str:
    """Classify failures without retaining credentials or provider response text."""
    from app.search_provider import ProviderError
    if isinstance(error, ProviderError):
        return error.code
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return "auth_error"
    if status in (402, 432, 433):
        return "quota"
    if status == 429:
        return "rate_limited"
    name = type(error).__name__.lower()
    # The Tavily SDK raises typed errors without a status code; its class names
    # are the provider's own evidence of a rejected key or exhausted plan.
    if name in ("forbiddenerror", "invalidapikeyerror", "missingapikeyerror"):
        return "auth_error"
    if name in ("usagelimitexceedederror", "tavilykeylesslimiterror"):
        return "quota"
    if "timeout" in name:
        return "timeout"
    if "connection" in name or "network" in name:
        return "network_error"
    return "search_failed"


def _parse_results(response: Any) -> list[WebResult]:
    """Adapt a raw Tavily search response into WebResult objects."""
    results: list[WebResult] = []
    for item in (response or {}).get("results", []) or []:
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        if not url or not content:
            continue
        results.append(
            WebResult(
                title=str(item.get("title") or "").strip() or _host(url),
                url=url,
                content=content,
                score=float(item['score']) if item.get('score') is not None else None,
                published_date=str(item.get("published_date") or "")[:10] or None,
            )
        )
    return results


def _search_pass(client: Any, query: str, *, caged: bool, max_results: int, timeout: float,
                 errors: list[str] | None = None, public_policy: bool = False,
                 official_domains: tuple[str, ...] = (),
                 cache: WebResearchCache | None = None,
                 discovery_mode: Literal["institution", "broader"] = "institution",
                 country: str | None = None) -> list[WebResult]:
    """Run one Tavily search pass, returning ``[]`` on any error.

    Pass 1 (``caged=True``): ``topic="finance"`` + ``include_domains`` restricted
    to the trusted finance allowlist — authoritative, on-list results only.
    Pass 2 (``caged=False``): ``topic="general"`` + ``country="malaysia"`` — the
    regional boost only works OUTSIDE the finance topic (finance routes to US
    data), so this is where breaking news / new platforms surface. Scrapers are
    excluded. Each pass fails closed to ``[]`` so one bad call can't break a turn.
    """
    started = monotonic()
    normalized = " ".join(str(query or "").split()).casefold()
    key = (query, caged, max_results, public_policy, official_domains, discovery_mode)
    if cache is not None and normalized in cache.sent_searches:
        cache.skipped_searches.append({"reason": "duplicate_search",
            "query_hash": sha256(normalized.encode("utf-8")).hexdigest()})
        if key in cache.searches:
            cache.cache_hits += 1
            return list(cache.searches[key])
        if errors is not None:
            errors.append("duplicate_search")
        return []
    if cache is not None and key in cache.searches:
        cache.cache_hits += 1
        return list(cache.searches[key])
    if cache is not None and cache.search_calls >= 3:
        cache.last_error = "search_call_limit"
        if errors is not None:
            errors.append(cache.last_error)
        return []
    try:
        if cache is not None:
            cache.search_calls += 1
            if normalized:
                cache.sent_searches.add(normalized)
        if public_policy:
            # Broad Malaysian official guidance, rather than a finance/news bias.
            # Domain preference is discovery, not proof of authority. Restrict
            # only to hosts already classified as an official institution.
            domains = [host for host in official_domains if discovery_mode == "institution"
                       if classify_tier("https://" + host) in {1, 2}]
            response = client.search(
                query=query, max_results=min(4, max(1, int(max_results))),
                **({'fresh_required': True} if cache is not None and cache.fresh_required else {}),
                search_depth="basic", topic="general",
                # Without an identified institution host, discover broadly.
                # A long finance-domain preference displaces unrelated public
                # agencies. Trust is still checked on every returned URL.
                # Country reranking can displace the institution's substantive
                # pages with short regional/news snippets. Identified official
                # domains already establish the search boundary; keep the
                # Malaysian boost only for open discovery.
                **({"include_domains": domains, "include_domains_mode": "restrict"}
                   if domains else {"country": country or WEB_SEARCH_DEFAULT_COUNTRY}),
                # Public factual policy rejects anecdotal/community evidence.
                # Do not spend its bounded discovery slots on social snippets
                # that cannot authorize the requested facts in the first place.
                exclude_domains=[*_EXCLUDED_DOMAINS, 'facebook.com', 'instagram.com', 'tiktok.com'],
                include_published_date=True, include_usage=True, timeout=timeout,
            )
        elif caged:
            response = client.search(
                query=query,
                max_results=max(1, int(max_results)),
                search_depth="basic",
                topic="finance",
                **({'fresh_required': True} if cache is not None and cache.fresh_required else {}),
                include_domains=list(_PREFERRED_DOMAINS),
                include_domains_mode="prefer",
                timeout=timeout,
            )
        else:
            response = client.search(
                query=query,
                max_results=max(1, int(max_results)),
                search_depth="basic",
                topic="general",
                country=country or WEB_SEARCH_DEFAULT_COUNTRY,
                **({'fresh_required': True} if cache is not None and cache.fresh_required else {}),
                exclude_domains=list(_EXCLUDED_DOMAINS),
                timeout=timeout,
            )
    except Exception as error:
        reason = _safe_error(error)
        if errors is not None:
            errors.append(reason)
        if cache is not None:
            cache.last_error = reason
        return []
    results = _parse_results(response)
    from app.rag.search_similarity import score_unscored
    results = score_unscored(query, results, timeout - (monotonic() - started))
    if cache is not None:
        cache.note_usage(response)
        cache.searches[key] = tuple(results)
    return results


def search_web(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
    errors: list[str] | None = None,
    single_search: bool = False,
    unrestricted: bool = False,
    public_policy: bool = False,
    official_domains: tuple[str, ...] = (),
    cache: WebResearchCache | None = None,
    discovery_mode: Literal["institution", "broader"] = "institution",
    country: str | None = None,
) -> list[WebResult]:
    """Two-pass Tavily search. Degrades to ``[]`` on any failure.

    Pass 1 is caged to trusted finance domains (authoritative). Only when pass 1
    is thinner than ``_MIN_CAGED_RESULTS`` does pass 2 fire — an un-caged,
    Malaysia-boosted general search that reaches breaking news and brand-new
    platforms the allowlist can't cover — and its results FILL the remaining
    slots (deduped by URL) rather than replacing pass 1. The tier classifier in
    ``to_retrieved_chunks`` then re-ranks the merged set so trusted domains lead
    regardless of which pass found them; un-trusted pass-2 hits classify as
    ``insufficient`` and cannot ground a claim.

    With no API key / SDK / query, or on error, returns ``[]`` so the answer
    degrades to "insufficient evidence" rather than raising.
    """
    if not api_key or not str(query or "").strip():
        return []
    try:
        from app.search_provider import provider
        client = provider(api_key)
    except ImportError:
        if errors is not None:
            errors.append("sdk_unavailable")
        return []
    except Exception as error:
        reason = _safe_error(error)
        if errors is not None:
            errors.append(reason)
        if cache is not None:
            cache.last_error = reason
        return []

    caged = _search_pass(client, query, caged=not unrestricted, max_results=max_results,
                         timeout=timeout, errors=errors, public_policy=public_policy,
                         official_domains=official_domains, cache=cache, discovery_mode=discovery_mode,
                         country=country)
    if single_search or public_policy or len(caged) >= _MIN_CAGED_RESULTS:
        return caged[:max_results]

    # Pass 1 was thin (edge case): fill remaining slots with the regional search.
    seen = {result.url for result in caged}
    merged = list(caged)
    for result in _search_pass(client, query, caged=False, max_results=max_results,
                               timeout=timeout, errors=errors, cache=cache, country=country):
        if result.url in seen:
            continue
        seen.add(result.url)
        merged.append(result)
        if len(merged) >= max_results:
            break
    return merged


def _complete_page_window(raw: str, query: str, *, subject_query: str = "") -> str:
    """Choose a bounded, contiguous section from a full page, locally.

    Tavily's query mode returns <=500-character snippets. Recovery instead
    fetches page context and ranks paragraph windows here, preserving list items
    after their heading. No new search call or source text is manufactured.
    """
    from collections import Counter
    words = lambda text: re.findall(r"\b[^\W\d_]{3,}\b", text.casefold())
    terms = set(words(query)) - {"the", "and", "for", "from", "with", "what", "how", "are"}
    # These are retrieval vocabulary, never policy facts. Malaysian official
    # pages often use Malay headings while the user asks in English. Rank the
    # requested section without translating or modifying its source text.
    equivalents = {
        "documents": {"dokumen", "sokongan"}, "document": {"dokumen"},
        "eligibility": {"eligible", "kelayakan", "syarat"}, "eligible": {"eligibility", "kelayakan", "syarat"},
        "qualifies": {"eligibility", "eligible", "kelayakan", "syarat"}, "application": {"apply", "permohonan", "memohon"},
        "apply": {"application", "permohonan", "memohon"}, "deadline": {"tarikh", "tempoh"},
        "process": {"kaedah", "langkah"}, "steps": {"langkah", "kaedah"},
        "exemption": {"pengecualian"}, "waiver": {"pengecualian"},
        "married": {"berkahwin", "perkahwinan"}, "role": {"peranan", "fungsi"},
        "functions": {"fungsi", "tugas"},
        "fungsi": {"functions", "role", "tugas", "peranan"},
        "duties": {"fungsi", "tugas", "peranan", "responsibilities"},
    }
    for term in tuple(terms):
        terms.update(equivalents.get(term, ()))
    # The programme/withdrawal subject must outrank a generic introduction that
    # happens to mention every procedural query word and the institution's name.
    subject_terms = set(words(subject_query)) - {
        "the", "and", "for", "from", "with", "what", "how", "are", "current", "latest",
        "application", "apply", "applying", "process", "procedure", "procedures", "steps",
        "eligibility", "eligible", "criteria", "qualifies", "qualifications", "required",
        "supporting", "document", "documents", "details", "information", "official",
    }
    subject_is_explicit = bool(subject_terms) and subject_terms <= terms
    for term in tuple(subject_terms):
        subject_terms.update(equivalents.get(term, ()))
    def subject_window(window: str) -> str:
        # A candidate can start at the last paragraph of another programme. If
        # the requested subject heading is present, drop that unrelated prefix;
        # never splice its conditions into the requested section.
        for heading in re.finditer(r"(?m)^#{1,6}\s+([^\n]+)", window):
            if subject_terms and subject_terms <= set(words(heading.group(1))):
                return window[heading.start():]
        return window
    # The assessor receives at most 1800 characters. Select within that bound
    # here instead of finding a useful section then cutting off its last items.
    window_limit = min(_MAX_PASSAGE_CHARS, 1800)
    if len(raw) <= window_limit:
        return subject_window(raw)
    frequencies = Counter(words(raw))
    starts = [0, *(match.end() for match in re.finditer(r"\n\s*\n", raw))]
    # PDF extraction can flatten an entire document into one paragraph. Add
    # literal sentence/question boundaries within those long spans; return a
    # contiguous source slice so quotation validation remains unchanged.
    flat_spans = [(start, end) for start, end in zip(starts, [*starts[1:], len(raw)])
                  if end - start > window_limit]
    document_is_flat = len(starts) <= 2 and not re.search(r"(?m)^#{1,6}\s", raw)
    for start, end in flat_spans:
        starts.extend(start + match.end() for match in re.finditer(r"[.!?]\s+", raw[start:end]))
        starts.extend(start + match.start() for match in re.finditer(
            r"(?<!\w)(?:\d{1,3}\.\s*[SQ]\s*:|[IVX]{1,6}\.\s+[A-Z])", raw[start:end]))
        # Some PDF lists contain no punctuation. Bounded overlapping windows
        # still make their later sections reachable, without changing text.
        for position in range(start + window_limit // 2, end, window_limit // 2):
            boundary = raw.find(" ", position, min(end, position + 100))
            if boundary >= 0:
                starts.append(boundary + 1)
    starts = sorted(set(starts))
    focus_terms = terms - subject_terms
    if terms & {"document", "documents", "documentation", "dokumen"}:
        focus_terms = terms & {"document", "documents", "documentation", "dokumen", "sokongan",
                               "married", "berkahwin", "perkahwinan"}
    windows = []
    for start in starts:
        end = min(len(raw), start + window_limit)
        if end < len(raw):
            # Prefer a paragraph boundary to cutting off the next instruction.
            boundaries = list(re.finditer(r"\n\s*\n", raw[start:end]))
            if boundaries:
                end = start + boundaries[-1].start()
        window = subject_window(raw[start:end].strip())
        if not window:
            continue
        tokens = set(words(window))
        # Rare requested words carry more weight than repeated menu labels.
        # Window boundaries can expose a partial token absent from the full
        # page. It must neither crash ranking nor count as a requested match.
        score = sum(1 / frequencies[term] ** .5 for term in terms & tokens if frequencies[term])
        subject_score = sum(1 / frequencies[term] ** .5 for term in subject_terms & tokens if frequencies[term])
        focus_score = sum(1 / frequencies[term] ** .5 for term in focus_terms & tokens if frequencies[term])
        focus_distance = next((match.start() for match in re.finditer(r"\b[^\W\d_]{3,}\b", window.casefold())
                               if match.group() in focus_terms), len(window))
        # General FAQ questions/section titles describe the requested list;
        # an exception answer can repeat more query words but omits its scope.
        heading = re.match(r"(?:(?:\d{1,3}\.\s*)?[SQ]\s*:\s*(?:which|what|who|how|apakah|bagaimanakah|adakah|siapakah)\b"
                           r"([^?]{0,180})\?|[IVX]{1,6}\.\s*([^()]{1,80})\s+[a-z]\))", window, re.I)
        heading_focus = bool(heading and focus_terms & set(words(next(
            value for value in heading.groups() if value is not None))))
        # HTML often exposes short unmarked section labels rather than Markdown
        # headings. A requested procedural section must beat menus/footers that
        # repeat the programme name. Its statements still require assessment.
        first_line = window.splitlines()[0].strip("#* ")
        section_terms = set(words(first_line))
        # Rank the question/section's purpose, not repeated words in its answer.
        # Checking an existing application's status and purchasing goods are
        # different workflows from applying or determining who qualifies.
        label = heading.group() if heading else first_line if len(first_line) <= 100 else ""
        status_heading = bool(re.search(r"\b(?:check|status|semak|semakan)\b", label, re.I))
        intent_rank = 0
        if terms & {"documents", "document", "documentation", "dokumen"}:
            intent_rank = int(bool(re.search(r"\b(?:what you need|documents?|dokumen)\b", label, re.I)))
        elif terms & {"eligibility", "eligible", "qualifies", "kelayakan", "syarat"}:
            intent_rank = int(not status_heading and bool(re.search(
                r"\b(?:who can apply|who is eligible|eligibility|eligible|criteria|qualif\w*|siapakah|layak|syarat)\b", label, re.I)))
        elif terms & {"application", "apply", "permohonan", "memohon"}:
            intent_rank = int(not status_heading and bool(re.search(
                r"\b(?:applications?|apply|applying|permohonan|memohon)\b", label, re.I)))
        # Standalone labels retain the section title above the relevant facts.
        # A sentence mentioning documents is evidence, not a competing heading.
        if not heading and (len(section_terms) > 8 or re.search(r"[.!?:]", label)):
            intent_rank = 0
        section_focus = bool(not document_is_flat and len(first_line) <= 100
            and len(section_terms) <= 8 and focus_terms & section_terms
            and (not subject_terms or subject_terms & tokens))
        # An agency-role heading identifies the actual section. Its body must
        # outrank a footer that repeats the agency and every intent word.
        role_terms = {'role', 'roles', 'duties', 'functions', 'fungsi', 'tugas', 'peranan', 'responsibilities'}
        preceding_headings = list(re.finditer(r'(?m)^#{1,6}\s+([^\n]+)', raw[:start]))
        owner_terms = set(words(preceding_headings[-1].group(1))) if preceding_headings else set()
        role_section = bool(terms & role_terms and (
            bool(re.match(r'^#{1,6}\s', window)) and section_terms & role_terms
            or owner_terms & role_terms)
            and (not subject_terms or subject_terms & tokens))
        # A programme heading alone cannot outrank the explicitly requested
        # document/eligibility section elsewhere on the same page. Subject
        # terms still contribute, and the assessor checks actual applicability.
        # On flattened documents, the programme name often occurs only on the
        # cover page. It must not defeat the actual requested document section.
        windows.append((int(role_section), intent_rank,
                        int(heading_focus) if document_is_flat else int(section_focus),
                        focus_score if document_is_flat else subject_score if subject_is_explicit else subject_score + score,
                        score, -focus_distance if document_is_flat else 0, -len(window), window))
    return max(windows, key=lambda item: item[:-1])[-1] if windows else raw[:window_limit]


def extract_passages(
    urls: list[str],
    *,
    api_key: str,
    query: str = "",
    timeout: float = 8.0,
    extract_depth: str = "basic",
    cache: WebResearchCache | None = None,
    complete_context: bool = False,
    subject_query: str = "",
) -> dict[str, str]:
    """Pull real page text via Tavily's extract endpoint, keyed by URL.

    Returns ``{url: raw_content}`` for successfully extracted pages only; URLs in
    the response's ``failed_results`` (or any error/timeout/missing SDK) simply
    do not appear, so the caller falls back to the search snippet. When ``query``
    is supplied, Tavily reranks and returns the topic-relevant chunks joined by
    ``[...]`` — still genuine page text, just focused. Each passage is capped at
    ``_MAX_PASSAGE_CHARS`` so one page cannot dominate the verifier budget.
    ``complete_context`` omits Tavily's query parameter to avoid its short snippet
    cutoffs, then selects one bounded section from full page text locally.
    """
    clean_urls = list(dict.fromkeys(str(u or "").strip() for u in urls if str(u or "").strip()))
    if not api_key or not clean_urls or timeout < 1:
        reason = "no_api_key" if not api_key else "deadline"
        for url in clean_urls:
            _extraction_event(cache, url, _extraction_method(), False, reason, attempted=False)
        return {}
    # A different public gap can need a different passage from the same URL.
    cached = {url: cache.passages[(url, query, extract_depth, complete_context, subject_query)] for url in clean_urls
              if cache is not None and (url, query, extract_depth, complete_context, subject_query) in cache.passages}
    if cache is not None and complete_context:
        for url in clean_urls:
            if url not in cached and url in cache.full_pages:
                cached[url] = _complete_page_window(cache.full_pages[url], query, subject_query=subject_query)
                cache.passages[(url, query, extract_depth, complete_context, subject_query)] = cached[url]
    clean_urls = [url for url in clean_urls if url not in cached]
    if cache is not None:
        cache.cache_hits += len(cached)
    if not clean_urls:
        return cached
    started = monotonic()
    raw_pages: dict[str, tuple[str, str]] = {}  # url -> (title, raw page text)
    if cache is not None and cache.extract_calls >= 4:
        cache.last_error = "extract_call_limit"
        for url in clean_urls[:20]:
            _extraction_event(cache, url, _extraction_method(), False, "extract_call_limit", attempted=False)
    else:
        try:
            from app.search_provider import provider as TavilyClient
            from app.search_provider import ProviderError
        except ImportError:
            TavilyClient = None
            for url in clean_urls[:20]:
                _extraction_event(cache, url, _extraction_method(), False, "sdk_unavailable", attempted=False)
        if TavilyClient is not None:
            from app.rag.research_checker_deadline import extract_with_deadline
            def extract_one(url, remaining):
                kwargs: dict[str, Any] = {
                    "urls": [url],
                    "extract_depth": extract_depth,
                    "timeout": remaining,
                }
                if str(query or "").strip() and not complete_context:
                    kwargs["query"] = query  # rerank extracted chunks to the topic
                    kwargs["chunks_per_source"] = 3
                if cache is not None:
                    kwargs["include_usage"] = True
                    if cache.fresh_required:
                        kwargs['fresh_required'] = True
                try:
                    client = TavilyClient(api_key)
                    return client.extract(**kwargs)
                except ProviderError as error:
                    return {'results': [], 'failed_results': [{'url': url, 'error': error.code}]}
            if cache is not None:
                cache.extract_calls += 1
            bounded = extract_with_deadline(clean_urls[:20], extract_one, max(0, timeout - (monotonic() - started)))
            if cache is not None:
                cache.tavily_extract_requests += sum(attempted for _, _, _, _, attempted in bounded)
            for url, (ok, response, error, elapsed, attempted) in zip(clean_urls[:20], bounded):
                if not ok:
                    if cache is not None:
                        cache.last_error = "timeout" if error in {"deadline", "TimeoutError"} else "extraction_failed"
                    _extraction_event(cache, url, _extraction_method(), False, error, attempted=attempted,
                                      elapsed_seconds=elapsed)
                    continue
                if cache is not None:
                    cache.note_usage(response)
                if not isinstance(response, dict):
                    _extraction_event(cache, url, _extraction_method(), False, "invalid_response", elapsed_seconds=elapsed)
                    continue
                found = next((item for item in response.get("results", []) or []
                              if str(item.get("url") or "").strip() == url
                              and str(item.get("raw_content") or "").strip()), None)
                if found:
                    raw = str(found.get("raw_content") or "").strip()
                    raw_pages[url] = (str(found.get("title") or raw[:180]), raw)
                    _extraction_event(cache, url, _extraction_method(), True, elapsed_seconds=elapsed)
                else:
                    failed = next((item for item in response.get("failed_results", []) or []
                                   if str(item.get("url") or "").strip() == url), None)
                    error_type = (_provider_extract_error(failed.get("error")) if failed else "missing_result")
                    if cache is not None and failed:
                        cache.last_error = error_type if error_type in {'auth_error', 'quota', 'rate_limited', 'timeout', 'network_error'} else "extraction_failed"
                    _extraction_event(cache, url, _extraction_method(), False, error_type, elapsed_seconds=elapsed)
    if cache is not None and complete_context:
        _direct_fetch_fallback(clean_urls, raw_pages, cache=cache,
                               remaining=timeout - (monotonic() - started))
    passages: dict[str, str] = dict(cached)
    for url, (title, raw) in raw_pages.items():
        passages[url] = (_complete_page_window(raw, query, subject_query=subject_query) if complete_context
                         else raw[:_MAX_PASSAGE_CHARS])
        if cache is not None:
            if complete_context and len(raw) <= 100_000 and len(cache.full_pages) < 6:
                cache.full_pages[url] = raw
                if is_public_guidance_url(url) and classify_tier(url) in {1, 2, 3, 4}:
                    from datetime import datetime, timezone
                    from hashlib import sha256
                    from app.rag.public_source_store import PublicSourcePage
                    cache.fetched_pages[url] = PublicSourcePage(url,
                        title[:500], raw,
                        datetime.now(timezone.utc), sha256(raw.encode()).hexdigest())
            cache.passages[(url, query, extract_depth, complete_context, subject_query)] = passages[url]
    return passages


# Tavily text shorter than this for an official page is treated as clipped.
_CLIPPED_RAW_CHARS = 400
_DIRECT_FETCH_CAP = 3
_DIRECT_FETCH_TIMEOUT = 6.0


def _direct_fetch_fallback(urls: list[str], raw_pages: dict[str, tuple[str, str]], *,
                           cache: WebResearchCache, remaining: float) -> None:
    """Retry failed/clipped official URLs with the guarded direct fetcher.

    Only tier-1/2 hosts qualify (``fetch_official_page`` re-checks every guard).
    Fetches run in parallel within the caller's remaining operation time, so
    this never extends the shared request deadline. Fetched text is an
    evidence candidate only; the assessor and verifier still decide.
    """
    from app import config
    if not getattr(config, "COACH_DIRECT_FETCH_ENABLED", False):
        return
    retry = [url for url in urls
             if classify_tier(url) in {1, 2}
             and len(raw_pages.get(url, ("", ""))[1]) < _CLIPPED_RAW_CHARS]
    retry = retry[:max(0, _DIRECT_FETCH_CAP - cache.direct_fetches)]
    if not retry or remaining < 1.5:
        return
    from app.rag.research_checker_deadline import extract_with_deadline
    from app.rag.public_fetch import fetch_official_page
    cache.direct_fetches += len(retry)
    allowance = min(_DIRECT_FETCH_TIMEOUT, remaining)
    bounded = extract_with_deadline(retry, lambda url, left: fetch_official_page(url, timeout=left), allowance)
    recovered = 0
    for url, (ok, raw, error, elapsed, attempted) in zip(retry, bounded):
        if not ok:
            _extraction_event(cache, url, "direct", False, error, attempted=attempted, elapsed_seconds=elapsed)
            continue
        _extraction_event(cache, url, "direct", bool(raw), None if raw else "unavailable_or_rejected",
                          elapsed_seconds=elapsed)
        if raw and len(raw) > len(raw_pages.get(url, ("", ""))[1]):
            heading = re.search(r"(?m)^#{1,6}\s+(.{3,180})$", raw)
            raw_pages[url] = (heading.group(1) if heading else raw[:180], raw)
            recovered += 1
    diagnostics = cache.public_source_diagnostics
    diagnostics["direct_fetch_attempts"] = diagnostics.get("direct_fetch_attempts", 0) + len(retry)
    diagnostics["direct_fetch_pages"] = diagnostics.get("direct_fetch_pages", 0) + recovered
    if recovered and cache.last_error == "extraction_failed":
        cache.last_error = None


def to_retrieved_chunks(
    results: list[WebResult],
    *,
    start_id: int = -1,
) -> list[RetrievedChunk]:
    """Adapt web results into RetrievedChunk objects, ranked by tier then score.

    Web chunks get negative synthetic ids so they never collide with real
    knowledge-document ids during persistence and de-duplication. An unknown-tier
    result sorts last (least trusted) and carries confidence "insufficient".
    """
    def _rank(result: WebResult) -> tuple[int, float]:
        tier = classify_tier(result.url)
        return (_UNKNOWN_TIER_RANK if tier is None else tier, -(result.score if result.score is not None else 0.0))

    ranked = sorted(results, key=_rank)
    chunks: list[RetrievedChunk] = []
    for offset, result in enumerate(ranked):
        tier = classify_tier(result.url)
        chunks.append(
            RetrievedChunk(
                id=start_id - offset,
                title=result.title or None,
                source=_host(result.url) or result.title or None,
                page_number=None,
                chunk_index=None,
                content=result.content,
                similarity=result.score if result.score is not None else 0.0,
                url=result.url,
                source_type="web",
                tier=tier,
                confidence=tier_to_confidence(tier),
                published_date=result.published_date,
                checked_at=datetime.now(timezone.utc).date().isoformat(),
            )
        )
    return chunks


def merge_evidence(
    corpus_chunks: list[RetrievedChunk],
    web_chunks: list[RetrievedChunk],
    *,
    max_chars: int = _MAX_MERGED_CHARS,
) -> list[RetrievedChunk]:
    """Merge corpus + web evidence with corpus PRIMARY (invariant #1).

    Corpus chunks are kept whole and first — they are never dropped to make room
    for web. Web chunks (already tier-ranked) are appended until adding one would
    exceed ``max_chars`` of total evidence text, so the merged block stays within
    the verifier's single-batch context budget. Fixes the earlier wholesale
    ``chunks = web_chunks`` replace.
    """
    merged: list[RetrievedChunk] = list(corpus_chunks)
    used = sum(len(chunk.content or "") for chunk in merged)
    for chunk in web_chunks:
        size = len(chunk.content or "")
        if merged and used + size > max_chars:
            continue  # prefer corpus + already-added higher-tier web passages
        merged.append(chunk)
        used += size
    return merged


def research_evidence(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
    single_search: bool = False,
    unrestricted: bool = False,
    public_policy: bool = False,
    official_domains: tuple[str, ...] = (),
    cache: WebResearchCache | None = None,
    subject_query: str = "",
    discovery_mode: Literal["institution", "broader"] = "institution",
    web_query: str | None = None,
    web_query_guard: Any = None,
    web_query_shorten: bool = False,
    country: str | None = None,
) -> ResearchOutcome:
    """Search then extract: tier-ranked web chunks with real passage text.

    ``query`` must already be de-identified (see ``build_research_query``). The
    search finds candidate pages; the extract endpoint pulls full passage text
    for those pages so the entailment verifier has genuine source text to check
    against (not just a snippet). Degrades to an empty outcome — with a reason
    code — on no key / no query / no results / SDK missing / error.
    """
    if not api_key:
        return ResearchOutcome([], False, "no_api_key")
    if not str(query or "").strip():
        return ResearchOutcome([], False, "no_query")
    errors: list[str] = []
    if cache is not None:
        cache.last_error = None
    # Search can make two calls and extraction one; divide the caller's shared
    # research allowance so those calls do not each consume the full cap.
    started = monotonic()
    operation_timeout = max(0.1, timeout / (2 if single_search else 3))
    search_options = ({"single_search": True, "unrestricted": unrestricted}
                      if single_search else {})
    if cache is not None:
        search_options["cache"] = cache
    if public_policy:
        search_options.update(public_policy=True, official_domains=official_domains, cache=cache,
                              discovery_mode=discovery_mode)
    if country:
        search_options["country"] = country
    # The optional interpreter phrase affects web discovery only; extraction,
    # evidence windows, and knowledge-base retrieval keep the existing query.
    # A new phrase is usable only after the owner-scoped comparison immediately
    # before the search. A failing guard cannot authorize the old query.
    search_query = query
    if web_query_guard is not None:
        try:
            guard_options = ({"timeout": max(0, timeout - (monotonic() - started))}
                             if getattr(web_query_guard, "accepts_timeout", False) else {})
            if web_query_shorten and getattr(web_query_guard, "accepts_shorten", False):
                guard_options["shorten"] = True
            guarded_query = web_query_guard(web_query or "", query, **guard_options)
        except Exception:
            if cache is not None:
                cache.privacy_skips.append({"privacy_guard_unavailable": True})
            return ResearchOutcome([], False, "privacy_skip_owned_name")
        else:
            from app.rag.search_privacy import SKIP_UNSAFE_SEARCH
            if guarded_query is SKIP_UNSAFE_SEARCH:
                if cache is not None:
                    cache.privacy_skips.append({"privacy_guard_skip": True})
                return ResearchOutcome([], False, "privacy_skip_owned_name")
            if not isinstance(guarded_query, str) or not guarded_query.strip():
                if cache is not None:
                    cache.privacy_skips.append({"privacy_guard_unavailable": True})
                return ResearchOutcome([], False, "privacy_skip_owned_name")
            search_query = guarded_query
    remaining = timeout - (monotonic() - started)
    if remaining <= 0:
        return ResearchOutcome([], False, "search_deadline")
    operation_timeout = min(operation_timeout, remaining)
    before = cache.search_calls if cache is not None else 0
    skips_before = len(cache.skipped_searches) if cache is not None else 0
    results = search_web(search_query, api_key=api_key, max_results=max_results,
                         timeout=operation_timeout, errors=errors, **search_options)
    if not results:
        duplicate_only = (cache is not None and cache.search_calls == before
                          and len(cache.skipped_searches) > skips_before)
        reason = "duplicate_search" if duplicate_only else (errors[0] if errors else "no_results")
        # Preserve the previous attempted-web semantics for all other failures.
        return ResearchOutcome([], not duplicate_only, reason)
    extract_options = {"cache": cache} if cache is not None else {}
    if public_policy:
        # Application rules and document lists need their surrounding section.
        # Fetch page context on the same extraction call, rather than waiting
        # for a later round to discover that reranked short snippets were cut off.
        extract_options["complete_context"] = True
        extract_options["subject_query"] = subject_query
    passages = extract_passages(
        [result.url for result in results],
        api_key=api_key,
        query=query if public_policy else search_query,
        timeout=timeout - (monotonic() - started),
        **extract_options,
    ) if timeout - (monotonic() - started) >= 1 else {}
    def evidence_text(result: WebResult) -> str:
        extracted = passages.get(result.url)
        if not extracted:
            return result.content
        if not public_policy or result.content in extracted:
            return extracted
        # A nominally successful extraction may contain just navigation/footer.
        # Retain independently retrieved public text from the SAME URL, selecting
        # a bounded literal window. The explicit gap forbids joining snippets
        # into a fabricated sentence; the assessor still checks applicability.
        search_text = _complete_page_window(result.content, query, subject_query=subject_query)
        return search_text + '\n\n[...]\n\n' + extracted

    enriched = [
        WebResult(
            title=result.title,
            url=result.url,
            # Prefer the fuller extracted passage; fall back to the snippet.
            content=evidence_text(result),
            score=result.score,
            published_date=result.published_date,
        )
        for result in results
    ]
    chunks = to_retrieved_chunks(enriched)
    # A search snippet is not evidence that the page was fetched now. Only a
    # successful extraction earns today's checked_at; fallback text keeps an
    # unknown check date so it cannot count as fresh.
    chunks = [replace(chunk, checked_at=None)
              if chunk.url and chunk.url not in passages else chunk
              for chunk in chunks]
    return ResearchOutcome(chunks, True, "ok",
                           cache.last_error if cache is not None else None)


def research(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
    web_query_guard: Any = None,
) -> list[RetrievedChunk]:
    """Backward-compatible list wrapper over ``research_evidence``.

    ``query`` must already be de-identified by the caller. Returns just the
    tier-ranked chunks (merging with corpus is the caller's job, since corpus
    lives in the service).
    """
    return research_evidence(
        query, api_key=api_key, max_results=max_results, timeout=timeout,
        web_query_guard=web_query_guard,
    ).chunks
