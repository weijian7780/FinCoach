"""Unit tests for the web-research fallback ranking and adapters.

Networking (Tavily) is not exercised here; only the pure classification and
adapter functions, plus the no-key degradation path.
"""

import pytest

from unittest import mock

from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import (
    ResearchOutcome,
    WebResult,
    build_research_query,
    classify_tier,
    extract_passages,
    is_named_product_allowed,
    merge_evidence,
    research,
    research_evidence,
    search_web,
    tier_to_confidence,
    to_retrieved_chunks,
)


@pytest.mark.parametrize(
    "url, expected_tier",
    [
        ("https://www.bnm.gov.my/rates", 1),
        ("https://lhdn.gov.my/tax", 1),
        ("https://kwsp.gov.my/dividend", 1),
        ("https://example.gov/policy", 1),
        ("https://www.maybank2u.com.my/fd", 2),
        ("https://cimb.com.my/savings", 2),
        ("https://www.thestar.com.my/business/x", 3),
        ("https://www.reuters.com/markets", 3),
        ("https://econ.mit.edu/paper", 4),
        ("https://doi.org/10.1000/xyz", 4),
        # AKPK (BNM subsidiary) is tier 1 despite the .org.my suffix.
        ("https://www.akpk.org.my/debt", 1),
        # Licensed commercial entities are tier 2 (their own official domains).
        ("https://www.stashaway.my/fees", 2),
        ("https://gxbank.my/savings", 2),
        ("https://www.aeonbank.com.my/deposit", 2),
        ("https://kenanga.com.my/kdi", 2),
        ("https://versa.com.my/rates", 2),
        ("https://www.wahed.com/my/faq", 2),
        ("https://wahedinvest.com/portfolios", 2),
        ("https://digitalinvesting.com.my/kdi-save", 2),
        ("https://www.reddit.com/r/MalaysianPF", 5),
        ("https://lowyat.net/thread/123", 5),
        # Unknown/unclassifiable hosts are NOT dressed as tier 5 — they are None.
        ("https://some-random-blog.xyz/opinion", None),
        ("not a url", None),
        ("", None),
    ],
)
def test_classify_tier(url, expected_tier):
    assert classify_tier(url) == expected_tier


def test_unknown_domain_maps_to_insufficient_not_anecdotal():
    # An unclassifiable host is "insufficient" (establishes nothing), NEVER tier 5
    # anecdotal — tier 5 is reserved for hosts known to be community/forum.
    assert classify_tier("https://randomforum.example/post") is None
    assert tier_to_confidence(classify_tier("https://randomforum.example/post")) == "insufficient"


def test_known_community_host_stays_tier_5_anecdotal():
    assert classify_tier("https://www.reddit.com/r/x") == 5
    assert tier_to_confidence(5) == "anecdotal"


@pytest.mark.parametrize(
    "tier, expected",
    [
        (1, "established"), (2, "established"), (3, "reported"),
        (4, "reported"), (5, "anecdotal"), (None, "insufficient"),
    ],
)
def test_tier_to_confidence(tier, expected):
    assert tier_to_confidence(tier) == expected


def test_named_product_allowed_only_for_top_two_tiers():
    assert is_named_product_allowed(1) is True
    assert is_named_product_allowed(2) is True
    assert is_named_product_allowed(3) is False
    assert is_named_product_allowed(5) is False
    assert is_named_product_allowed(None) is False


def test_to_retrieved_chunks_ranks_by_tier_then_score_and_tags_provenance():
    results = [
        WebResult("Forum post", "https://www.reddit.com/r/x", "anecdote text", 0.99),
        WebResult("BNM rate", "https://www.bnm.gov.my/rate", "official rate text", 0.40),
        WebResult("Star article", "https://www.thestar.com.my/a", "news text", 0.80),
    ]
    chunks = to_retrieved_chunks(results)

    # Government source ranks first despite the lowest raw score.
    assert [c.source for c in chunks] == ["bnm.gov.my", "thestar.com.my", "reddit.com"]
    assert [c.tier for c in chunks] == [1, 3, 5]
    assert [c.confidence for c in chunks] == ["established", "reported", "anecdotal"]
    assert all(c.source_type == "web" for c in chunks)
    assert chunks[0].url == "https://www.bnm.gov.my/rate"
    # Synthetic ids are negative so they never collide with real doc ids.
    assert all(c.id < 0 for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_search_web_returns_empty_without_api_key():
    # No key configured -> no network call, no results, graceful degradation.
    assert search_web("epf dividend 2025", api_key="") == []
    assert research("epf dividend 2025", api_key="") == []


def test_search_web_returns_empty_for_blank_query():
    assert search_web("   ", api_key="fake-key") == []


# ---- Two-pass search: caged pass 1, regional fallback pass 2 -----------------

def _fake_tavily(pass1_hosts, pass2_hosts):
    """Build a fake TavilyClient whose .search returns different hits per pass.

    A caged call (topic='finance' + include_domains) yields pass1_hosts; an
    un-caged call (topic='general' + country) yields pass2_hosts.
    """
    def search(**kwargs):
        hosts = pass1_hosts if "include_domains" in kwargs else pass2_hosts
        return {
            "results": [
                {"url": f"https://{h}/x", "content": f"text from {h}", "score": 0.5, "title": h}
                for h in hosts
            ]
        }
    client = mock.MagicMock()
    client.search.side_effect = search
    return mock.MagicMock(TavilyClient=mock.MagicMock(return_value=client)), client


def test_search_web_uses_only_pass1_when_caged_results_are_enough():
    fake_module, client = _fake_tavily(
        pass1_hosts=["bnm.gov.my", "kwsp.gov.my"], pass2_hosts=["reddit.com"]
    )
    with mock.patch.dict("sys.modules", {"tavily": fake_module}):
        results = search_web("epf dividend", api_key="k", max_results=4)
    # Pass 1 met the floor -> pass 2 never runs (single API call).
    assert client.search.call_count == 1
    assert {r.url for r in results} == {"https://bnm.gov.my/x", "https://kwsp.gov.my/x"}


def test_search_web_falls_back_to_pass2_when_caged_is_thin():
    # Pass 1 returns only 1 trusted hit (< floor) -> pass 2 fills the rest.
    fake_module, client = _fake_tavily(
        pass1_hosts=["bnm.gov.my"], pass2_hosts=["ringgitplus.com", "thestar.com.my"]
    )
    with mock.patch.dict("sys.modules", {"tavily": fake_module}):
        results = search_web("brand new bank promo", api_key="k", max_results=4)
    assert client.search.call_count == 2  # caged + regional fallback
    hosts = {r.url for r in results}
    assert "https://bnm.gov.my/x" in hosts  # pass-1 trusted hit kept
    assert "https://ringgitplus.com/x" in hosts  # pass-2 fill (edge coverage)


def test_search_web_dedupes_across_passes():
    fake_module, client = _fake_tavily(
        pass1_hosts=["bnm.gov.my"], pass2_hosts=["bnm.gov.my", "thestar.com.my"]
    )
    with mock.patch.dict("sys.modules", {"tavily": fake_module}):
        results = search_web("q", api_key="k", max_results=4)
    urls = [r.url for r in results]
    assert urls.count("https://bnm.gov.my/x") == 1  # no duplicate across passes


def test_source_rows_carries_web_provenance():
    from app.rag.retrieval import RetrievedChunk
    from app.rag.service import source_rows

    web = to_retrieved_chunks(
        [WebResult("BNM", "https://www.bnm.gov.my/rate", "official text", 0.5)]
    )
    corpus = RetrievedChunk(
        id=9, title="Guide", source="student_finance.md", page_number=None,
        chunk_index=0, content="corpus text", similarity=0.82,
    )

    rows = source_rows(web + [corpus])
    assert rows[0]["source_type"] == "web"
    assert rows[0]["url"] == "https://www.bnm.gov.my/rate"
    assert rows[0]["tier"] == 1
    assert rows[0]["confidence"] == "established"
    # Corpus source keeps the backward-compatible defaults.
    assert rows[1]["source_type"] == "corpus"
    assert rows[1]["url"] is None
    assert rows[1]["tier"] is None


def test_build_coach_prompt_labels_web_reference_and_rules():
    from app.rag.prompts import build_coach_prompt

    web = to_retrieved_chunks(
        [WebResult("BNM rate", "https://www.bnm.gov.my/rate", "the OPR is set here", 0.5)]
    )
    prompt = build_coach_prompt("What is the OPR?", web, "", [], 6)

    assert "web; tier=1 (government / regulatory)" in prompt
    assert "confidence=established" in prompt
    assert "https://www.bnm.gov.my/rate" in prompt
    # The disagreement and insufficient-evidence guidance is present.
    assert "state the disagreement" in prompt
    assert "evidence is insufficient" in prompt


def test_prompt_scopes_tier2_commercial_to_factual_product_details():
    from app.rag.prompts import build_coach_prompt

    prompt = build_coach_prompt("What are the fees?", [], "", [], 6)
    # Tier-2 commercial pages are trusted for product facts only, never for
    # promotional claims, and never to override a tier-1 statutory figure.
    assert "own factual product details" in prompt
    assert "never override a statutory rate" in prompt
    assert "source wins" in prompt  # tier-1 wins a statutory-figure conflict


# ---- Task 3: de-identified query (invariant #7) ------------------------------

def test_build_research_query_strips_name_ref_and_signoff():
    query = build_research_query(
        "Explain compound interest. Regards, Ahmad, ref 5234."
    )
    assert "Ahmad" not in query
    assert "5234" not in query
    assert "Regards" not in query
    # The actual finance topic survives.
    assert "compound interest" in query.lower()


def test_build_research_query_strips_email_phone_and_amount():
    query = build_research_query(
        "Is my RM12,500 safe? mail me ahmad@example.com or 012-345 6789"
    )
    for leaked in ("RM12,500", "12,500", "ahmad@example.com", "012-345 6789", "6789"):
        assert leaked not in query
    assert "safe" in query.lower()


def test_build_research_query_keeps_in_topic_year():
    # A plain year is topic, not PII — it must survive so the query stays useful.
    query = build_research_query("What was the EPF dividend in 2024?")
    assert "2024" in query
    assert "EPF" in query


def test_build_research_query_empty_when_only_pii():
    assert build_research_query("Regards, Ahmad") == ""


# ---- Task 3: extract endpoint -> passage mapping -----------------------------

def test_extract_passages_maps_raw_content_and_skips_failures():
    fake_client = mock.MagicMock()
    fake_client.extract.return_value = {
        "results": [
            {"url": "https://www.bnm.gov.my/a", "raw_content": "full official passage"},
        ],
        "failed_results": [
            {"url": "https://blocked.example/x", "error": "403"},
        ],
    }
    fake_module = mock.MagicMock(TavilyClient=mock.MagicMock(return_value=fake_client))
    with mock.patch.dict("sys.modules", {"tavily": fake_module}):
        passages = extract_passages(
            ["https://www.bnm.gov.my/a", "https://blocked.example/x"],
            api_key="test-key",
            query="opr rate",
        )
    assert passages == {"https://www.bnm.gov.my/a": "full official passage"}
    # The de-identified query is forwarded to the extract call for reranking.
    assert fake_client.extract.call_args.kwargs["query"] == "opr rate"


def test_extract_passages_returns_empty_without_key():
    assert extract_passages(["https://x.example"], api_key="") == {}


def test_research_evidence_prefers_extracted_passage_over_snippet():
    def fake_search(query, *, api_key, max_results, timeout, errors=None):
        return [WebResult("BNM", "https://www.bnm.gov.my/a", "short snippet", 0.5)]

    with (
        mock.patch("app.rag.web_research.search_web", side_effect=fake_search),
        mock.patch(
            "app.rag.web_research.extract_passages",
            return_value={"https://www.bnm.gov.my/a": "the full extracted passage text"},
        ),
    ):
        outcome = research_evidence("opr rate", api_key="test-key")

    assert isinstance(outcome, ResearchOutcome)
    assert outcome.web_ran is True
    assert outcome.reason == "ok"
    assert outcome.chunks[0].content == "the full extracted passage text"


def test_research_evidence_reasons_when_degraded():
    assert research_evidence("x", api_key="").reason == "no_api_key"
    assert research_evidence("", api_key="k").reason == "no_query"
    with mock.patch("app.rag.web_research.search_web", return_value=[]):
        assert research_evidence("x", api_key="k").reason == "no_results"


# ---- Task 3: merge keeps corpus primary (invariant #1) -----------------------

def _corpus(cid: int, content: str, sim: float = 0.4) -> RetrievedChunk:
    return RetrievedChunk(
        id=cid, title="Guide", source="corpus.md", page_number=None,
        chunk_index=0, content=content, similarity=sim,
    )


def test_merge_evidence_keeps_corpus_and_appends_web():
    corpus = [_corpus(1, "corpus fact")]
    web = to_retrieved_chunks(
        [WebResult("BNM", "https://www.bnm.gov.my/a", "web fact", 0.5)]
    )
    merged = merge_evidence(corpus, web)
    assert [c.id for c in merged] == [1, -1]
    assert merged[0].source_type == "corpus"
    assert merged[1].source_type == "web"


def test_merge_evidence_never_drops_corpus_even_over_budget():
    # Corpus alone exceeds the cap: it is still kept whole; web is what gets cut.
    big = "x" * 50
    corpus = [_corpus(1, big), _corpus(2, big)]
    web = to_retrieved_chunks(
        [WebResult("BNM", "https://www.bnm.gov.my/a", "y" * 50, 0.5)]
    )
    merged = merge_evidence(corpus, web, max_chars=60)
    corpus_ids = [c.id for c in merged if c.source_type == "corpus"]
    assert corpus_ids == [1, 2]  # both corpus chunks survive
    assert not [c for c in merged if c.source_type == "web"]  # web dropped, not corpus
