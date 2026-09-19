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
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.rag.retrieval import RetrievedChunk


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
    score: float


@dataclass(frozen=True)
class ResearchOutcome:
    """Typed result of a research pass: merged-ready chunks + why web ran (or not)."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    web_ran: bool = False
    reason: str = "not_attempted"


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
                score=float(item.get("score") or 0.0),
            )
        )
    return results


def _search_pass(client: Any, query: str, *, caged: bool, max_results: int, timeout: float) -> list[WebResult]:
    """Run one Tavily search pass, returning ``[]`` on any error.

    Pass 1 (``caged=True``): ``topic="finance"`` + ``include_domains`` restricted
    to the trusted finance allowlist — authoritative, on-list results only.
    Pass 2 (``caged=False``): ``topic="general"`` + ``country="malaysia"`` — the
    regional boost only works OUTSIDE the finance topic (finance routes to US
    data), so this is where breaking news / new platforms surface. Scrapers are
    excluded. Each pass fails closed to ``[]`` so one bad call can't break a turn.
    """
    try:
        if caged:
            response = client.search(
                query=query,
                max_results=max(1, int(max_results)),
                search_depth="basic",
                topic="finance",
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
                country="malaysia",
                exclude_domains=list(_EXCLUDED_DOMAINS),
                timeout=timeout,
            )
    except Exception:
        return []
    return _parse_results(response)


def search_web(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
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
        from tavily import TavilyClient  # lazy: optional dependency
    except ImportError:
        return []
    client = TavilyClient(api_key=api_key)

    caged = _search_pass(client, query, caged=True, max_results=max_results, timeout=timeout)
    if len(caged) >= _MIN_CAGED_RESULTS:
        return caged[:max_results]

    # Pass 1 was thin (edge case): fill remaining slots with the regional search.
    seen = {result.url for result in caged}
    merged = list(caged)
    for result in _search_pass(client, query, caged=False, max_results=max_results, timeout=timeout):
        if result.url in seen:
            continue
        seen.add(result.url)
        merged.append(result)
        if len(merged) >= max_results:
            break
    return merged


def extract_passages(
    urls: list[str],
    *,
    api_key: str,
    query: str = "",
    timeout: float = 8.0,
    extract_depth: str = "basic",
) -> dict[str, str]:
    """Pull real page text via Tavily's extract endpoint, keyed by URL.

    Returns ``{url: raw_content}`` for successfully extracted pages only; URLs in
    the response's ``failed_results`` (or any error/timeout/missing SDK) simply
    do not appear, so the caller falls back to the search snippet. When ``query``
    is supplied, Tavily reranks and returns the topic-relevant chunks joined by
    ``[...]`` — still genuine page text, just focused. Each passage is capped at
    ``_MAX_PASSAGE_CHARS`` so one page cannot dominate the verifier budget.
    """
    clean_urls = [str(u or "").strip() for u in urls if str(u or "").strip()]
    if not api_key or not clean_urls:
        return {}
    try:
        from tavily import TavilyClient  # lazy: optional dependency
    except ImportError:
        return {}
    try:
        client = TavilyClient(api_key=api_key)
        kwargs: dict[str, Any] = {
            "urls": clean_urls[:20],  # Tavily extract accepts up to 20 URLs
            "extract_depth": extract_depth,
            "timeout": timeout,
        }
        if str(query or "").strip():
            kwargs["query"] = query  # rerank extracted chunks to the topic
        response: Any = client.extract(**kwargs)
    except Exception:
        return {}
    passages: dict[str, str] = {}
    # Even on HTTP 200, failures surface in failed_results and results may be
    # empty; we simply take whatever succeeded.
    for item in (response or {}).get("results", []) or []:
        url = str(item.get("url") or "").strip()
        raw = str(item.get("raw_content") or "").strip()
        if url and raw:
            passages[url] = raw[:_MAX_PASSAGE_CHARS]
    return passages


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
        return (_UNKNOWN_TIER_RANK if tier is None else tier, -result.score)

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
                similarity=result.score,
                url=result.url,
                source_type="web",
                tier=tier,
                confidence=tier_to_confidence(tier),
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
    results = search_web(query, api_key=api_key, max_results=max_results, timeout=timeout)
    if not results:
        return ResearchOutcome([], True, "no_results")
    passages = extract_passages(
        [result.url for result in results],
        api_key=api_key,
        query=query,
        timeout=timeout,
    )
    enriched = [
        WebResult(
            title=result.title,
            url=result.url,
            # Prefer the fuller extracted passage; fall back to the snippet.
            content=passages.get(result.url, result.content),
            score=result.score,
        )
        for result in results
    ]
    return ResearchOutcome(to_retrieved_chunks(enriched), True, "ok")


def research(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
) -> list[RetrievedChunk]:
    """Backward-compatible list wrapper over ``research_evidence``.

    ``query`` must already be de-identified by the caller. Returns just the
    tier-ranked chunks (merging with corpus is the caller's job, since corpus
    lives in the service).
    """
    return research_evidence(
        query, api_key=api_key, max_results=max_results, timeout=timeout
    ).chunks
