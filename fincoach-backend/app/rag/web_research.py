"""Web-research fallback: search the open web when the corpus cannot answer.

This is a *fallback*, invoked only when internal RAG retrieval is inadequate for
a knowledge-route question (see the trigger in ``CoachingService.send_message``).
Corpus is always tried first.

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
  5 community / forum           -> confidence "anecdotal"

An unknown domain defaults to tier 5 (anecdotal) and is NEVER upgraded — this is
what stops community/blog content being dressed up as established fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.rag.retrieval import RetrievedChunk


# ---- Domain -> tier tables ---------------------------------------------------
# Matched most-trusted first. Suffix rules (``.gov.my``, ``.edu``) cover whole
# families; explicit sets cover well-known named domains. Anything unmatched is
# tier 5 and cannot be promoted.

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
})

# Institutions' own official domains. Naming a provider is only ever allowed when
# cited to a tier-1 or tier-2 source (see the loosened product guard).
_OFFICIAL_INSTITUTIONS = frozenset({
    "maybank2u.com.my", "maybank.com", "cimb.com.my", "cimbbank.com.my",
    "publicbank.com.my", "pbebank.com", "rhbgroup.com", "hongleongbank.com.my",
    "ambank.com.my", "bankislam.com", "bankrakyat.com.my", "affinbank.com.my",
    "alliancebank.com.my", "hsbc.com.my", "ocbc.com.my", "uob.com.my",
    "standardchartered.com.my", "tnbc.com.my", "touchngo.com.my", "boost.my",
    "grab.com", "bigpay.com.my", "principal.com.my", "publicmutual.com.my",
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

# The lowest tier that may back a factual provider/product name.
NAMED_PRODUCT_MAX_TIER = 2


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


def classify_tier(url: str) -> int:
    """Map a URL to a trust tier 1..5. Unknown domains are tier 5, never higher."""
    host = _host(url)
    if not host:
        return 5
    if host.endswith(_GOV_SUFFIXES) or _host_or_suffix_in(host, _GOV_HOSTS):
        return 1
    if _host_or_suffix_in(host, _OFFICIAL_INSTITUTIONS):
        return 2
    if _host_or_suffix_in(host, _REPUTABLE_PUBLICATIONS):
        return 3
    if host.endswith(_ACADEMIC_SUFFIXES) or _host_or_suffix_in(host, _ACADEMIC_HOSTS):
        return 4
    return 5  # community/forum and every unknown domain


def tier_to_confidence(tier: int) -> str:
    """Map a trust tier to one of the four confidence classes."""
    return _TIER_CONFIDENCE.get(tier, "anecdotal")


def tier_label(tier: int) -> str:
    return _TIER_LABEL.get(tier, "community / forum")


def is_named_product_allowed(tier: int | None) -> bool:
    """A provider/product may be named only when a tier-1/2 source backs it."""
    return tier is not None and tier <= NAMED_PRODUCT_MAX_TIER


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    content: str
    score: float


def search_web(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
) -> list[WebResult]:
    """Query Tavily for web evidence. Degrades to ``[]`` on any failure.

    With no API key configured — or if the Tavily SDK is not installed, or the
    call errors/times out — this returns no results so the coach answer degrades
    to "insufficient evidence" rather than raising. Networking is isolated here;
    the ranking/adapter functions above stay pure and unit-testable.
    """
    if not api_key or not str(query or "").strip():
        return []
    try:
        from tavily import TavilyClient  # lazy: optional dependency
    except ImportError:
        return []
    try:
        client = TavilyClient(api_key=api_key)
        response: Any = client.search(
            query=query,
            max_results=max(1, int(max_results)),
            search_depth="basic",
            timeout=timeout,
        )
    except Exception:
        # A dead key, rate limit, or timeout must not break the coach turn.
        return []
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


def to_retrieved_chunks(
    results: list[WebResult],
    *,
    start_id: int = -1,
) -> list[RetrievedChunk]:
    """Adapt web results into RetrievedChunk objects, ranked by tier then score.

    Web chunks get negative synthetic ids so they never collide with real
    knowledge-document ids during persistence and de-duplication.
    """
    ranked = sorted(
        results,
        key=lambda result: (classify_tier(result.url), -result.score),
    )
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


def research(
    query: str,
    *,
    api_key: str,
    max_results: int = 4,
    timeout: float = 8.0,
) -> list[RetrievedChunk]:
    """Full fallback: search the web and return tier-ranked RetrievedChunks."""
    return to_retrieved_chunks(
        search_web(query, api_key=api_key, max_results=max_results, timeout=timeout)
    )
