"""Search-only interpreter wording and literal, formatting-tolerant evidence."""
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.rag import request_interpretation as interpreter
from app.rag import research_policy as policy
from app.rag import service
from app.rag import web_research
from app.rag.evidence_text import match_evidence_quote
from app.rag.research_coverage import RequestedPart
from app.rag.research_fact_bindings import _literal
from app.rag.research_scope import normalized_anchor
from app.rag.search_privacy import SKIP_UNSAFE_SEARCH, contains_owned_phrase, make_search_guard, owned_names
from app.rag.retrieval import RetrievedChunk
from tests.test_category_interpretation_contract import StoredClient, USER_ID, stored_rows


# The quote is the literal q3-r3 assessment; the retained trial did not save
# the fetched passage, so this passage recreates its reported list formatting.
Q3_QUOTE = ("You can buy and sell stocks through: * A direct stock plan "
            "* A dividend reinvestment plan * A discount or full-service broker * A stock fund")
Q3_SOURCE = ("Earlier text.\nYou can buy and sell stocks through:\n"
             "* A direct stock plan\n* A dividend reinvestment plan\n"
             "* A discount or full-service broker\n* A stock fund\nLater text.")


def test_q3_quote_ignores_bullets_line_breaks_and_returns_original_span():
    matched = match_evidence_quote(Q3_QUOTE, Q3_SOURCE)
    assert matched == Q3_SOURCE[Q3_SOURCE.index("You can"):Q3_SOURCE.index("\nLater")]
    assert matched in Q3_SOURCE
    # Downstream ownership gets the recovered exact span, not model wording.
    assert _literal(matched, Q3_SOURCE)
    assert normalized_anchor(matched) in normalized_anchor(Q3_SOURCE)


@pytest.mark.parametrize("quote", [
    Q3_QUOTE.replace("direct", "indirect"),
    Q3_QUOTE.replace("* A direct stock plan * A dividend reinvestment plan",
                     "* A dividend reinvestment plan * A direct stock plan"),
    Q3_QUOTE.replace(" * A discount or full-service broker", ""),
    Q3_QUOTE.replace("* A direct stock plan * A dividend reinvestment plan",
                     "A direct stock plan, A dividend reinvestment plan"),
])
def test_rewritten_reordered_omitted_or_comma_replaced_items_fail(quote):
    assert match_evidence_quote(quote, Q3_SOURCE) is None


def test_numbered_lists_emphasis_and_whitespace_preserve_numbers_and_conditions():
    source = ("Before\n**Options:**\n1. Save 20 percent if eligible\n"
              "2. Pay the remainder\nAfter")
    quote = "Options: 1. Save 20 percent if eligible 2. Pay the remainder"
    assert match_evidence_quote(quote, source) == source[source.index("Options:"):source.index("\nAfter")]
    assert match_evidence_quote(quote.replace("20", "30"), source) is None
    assert match_evidence_quote(quote.replace(" if eligible", ""), source) is None
    assert match_evidence_quote(quote.replace("20 percent", "20, percent"), source) is None


def test_punctuation_and_arithmetic_are_not_fuzzy_matched():
    source = "Rules:\n* The formula is 5 * 3\n* The fee is 2 percent."
    assert match_evidence_quote("The formula is 5 3", source) is None
    assert match_evidence_quote("The fee is 3 percent.", source) is None
    assert match_evidence_quote("The fee, is 2 percent.", source) is None


@pytest.mark.parametrize("quote,source", [
    ("1. Pay at least / 2. Then wait 3 days", "Pay at least 5. Then wait 3 days"),
    ("- Repay in 1 2 years", "Repay in 1 - 2 years"),
    ("1. Pay at least 2. Then wait 3 days", "Pay at least 5. Then wait 3 days"),
])
def test_source_inline_numbers_and_operators_are_never_list_markers(quote, source):
    assert match_evidence_quote(quote, source) is None


def test_assessment_matches_quote_but_rejects_foreign_jurisdiction():
    chunk = RetrievedChunk(-1, "Stocks", "investor.gov", None, 0, Q3_SOURCE, 0.8,
        url="https://www.investor.gov/example", source_type="web", tier=1, confidence="established")
    plan = policy.QuestionPlan("buy stocks", False, True, "stable", required_facts=("how to buy stocks",),
                               search_query="shares investing Malaysia")
    result = {"status": "partial", "missing": ["Malaysian procedure"], "conflicting": False,
              "jurisdiction_matches": False, "period_matches": True,
              "support": [{"source_id": 1, "quote": Q3_QUOTE}]}
    generate = Mock(return_value=SimpleNamespace(content=json.dumps(result)))
    diagnostics = {}
    assessment = policy.assess_evidence(plan, [chunk], generate=generate, diagnostics=diagnostics)
    assert diagnostics["unmatched_quotes"] == 0
    assert assessment.supported_sources == ()
    assert assessment.applicability_rejected
    assert assessment.status == "partial"
    assert "evidence applicable to Malaysia" in assessment.missing
    assert '"search_query"' not in generate.call_args.args[0]
    assert "shares investing Malaysia" not in generate.call_args.args[0]
    result["jurisdiction_matches"] = True
    generate.return_value.content = json.dumps(result)
    assessment = policy.assess_evidence(plan, [chunk], generate=generate)
    assert assessment.supported_sources == (1,)
    assert assessment.supported_quotes[0][1] in Q3_SOURCE


def make_proposal(search_query=None):
    public = {
        "topic": "rutin menabung", "required_facts": ["rutin menabung"],
        "subject_domain": "finance", "search_query": search_query,
    }
    return interpreter.IntentProposal.model_validate({
        "route": "combined", "response_language": "ms",
        "read": {"operation": "get_savings_goals", "category": {"decision": "none"},
                 "goal_name": "Private Laptop"},
        "public": public,
    })


def test_malay_question_uses_english_phrase_and_not_personal_context():
    proposal = make_proposal("savings habits and financial goals")
    plan = interpreter._public_plan(proposal, "Simpanan saya untuk Private Laptop RM3000?")
    query = policy._web_search_query(plan, RequestedPart("p1", "rutin menabung Private Laptop RM3000"))
    assert query == "savings habits and financial goals Malaysia"
    assert all(value not in query for value in ("Private", "Laptop", "3000", "rutin"))
    assert plan.response_language == "ms"
    assert plan.required_facts == ("rutin menabung",)


def test_interpreter_echo_of_private_goal_must_not_reach_web_search():
    proposal = make_proposal("Private Laptop savings habits")
    plan = interpreter._public_plan(proposal, "Simpanan saya untuk Private Laptop?")
    rows = stored_rows(["Food"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Private Laptop"}]
    client = StoredClient(rows)
    guard = make_search_guard(client, USER_ID)
    outgoing = guard(policy._web_search_query(plan), "saving routines Malaysia")
    assert outgoing is SKIP_UNSAFE_SEARCH  # No rewrite model was provided.
    assert {q.table_name for q in client.executed} >= {"savings_goals", "categories", "transactions"}
    assert all(("eq", "user_id", USER_ID) in q.filters for q in client.executed
               if q.table_name in {"savings_goals", "categories", "transactions"})


@pytest.mark.parametrize("phrase", ["new PRIVATE LAPTOP plan", "new secret custom plan", "saving at Secret Shop"])
def test_owned_goal_category_and_merchant_are_checked_before_each_search(phrase):
    rows = stored_rows(["Food"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Private Laptop"},
                             {"id": "g2", "user_id": "other-owner", "name": "Other Goal"}]
    rows["categories"].append({"id": 1001, "user_id": USER_ID, "name": "Secret Custom"})
    rows["transactions"].append({"id": "t1", "user_id": USER_ID, "source": "Secret Shop"})
    client = StoredClient(rows)
    guard = make_search_guard(client, USER_ID)
    assert guard(phrase, "old query Malaysia") is SKIP_UNSAFE_SEARCH
    assert len([q for q in client.executed if q.table_name == "transactions"]) == 1
    assert guard("Other Goal plans", "old query Malaysia") == "Other Goal plans"


def test_case_insensitive_whole_phrase_matching_skips_unsafe_legacy_query():
    assert contains_owned_phrase("Savings PRIVATE   Laptop plan", ("Private Laptop",))
    assert not contains_owned_phrase("Savings Private Laptopcase plan", ("Private Laptop",))
    rows = stored_rows(["Food"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Laptop"}]
    guard = make_search_guard(StoredClient(rows), USER_ID)
    assert guard("Private Laptop saving habits", "Laptop saving Malaysia") is SKIP_UNSAFE_SEARCH


def test_privacy_diagnostics_do_not_log_owned_names(caplog):
    rows = stored_rows(["Food"])
    rows['savings_goals'] = [{'id': 'g1', 'user_id': USER_ID, 'name': 'Private Laptop'}]
    with caplog.at_level('INFO', logger='app.rag.search_privacy'):
        result = make_search_guard(StoredClient(rows), USER_ID)(
            'Private Laptop saving ideas', 'legacy private laptop Malaysia')
    assert result is SKIP_UNSAFE_SEARCH
    assert 'Private Laptop' not in caplog.text and 'private laptop' not in caplog.text
    assert 'owned_name_detected' in caplog.text


def test_privacy_read_failure_or_denied_consent_skips_unverified_search():
    assert make_search_guard(StoredClient(stored_rows(["Food"], consent="denied")), USER_ID)(
        "saving habits Malaysia", "legacy Malaysia") is SKIP_UNSAFE_SEARCH
    assert make_search_guard(object(), USER_ID)("saving habits Malaysia", "legacy Malaysia") is SKIP_UNSAFE_SEARCH


def test_privacy_reads_all_owner_pages_not_only_first_page():
    rows = stored_rows(["Food"])
    rows['savings_goals'] = [
        {'id': f'g{i:04d}', 'user_id': USER_ID, 'name': f'Goal {i}'} for i in range(501)
    ]
    client = StoredClient(rows)
    assert 'Goal 500' in owned_names(client, USER_ID)
    pages = [q.bounds for q in client.executed if q.table_name == 'savings_goals']
    assert pages == [(0, 499), (500, 999)]


def test_actual_search_does_not_send_unsafe_legacy(monkeypatch):
    rows = stored_rows(["Food"])
    rows["savings_goals"] = [{"id": "g1", "user_id": USER_ID, "name": "Private Laptop"}]
    guard = make_search_guard(StoredClient(rows), USER_ID)
    sent = []
    monkeypatch.setattr(web_research, "search_web", lambda query, **kwargs: sent.append(query) or [])
    result = web_research.research_evidence("Private Laptop legacy Malaysia",
        web_query="PRIVATE LAPTOP savings Malaysia", web_query_guard=guard,
        api_key="test-only", timeout=10)
    assert not sent and result.reason == "privacy_skip_owned_name"


def test_new_wording_without_an_owner_guard_never_reaches_the_search(monkeypatch):
    sent = []
    monkeypatch.setattr(web_research, "search_web", lambda query, **kwargs: sent.append(query) or [])
    web_research.research_evidence("legacy Malaysia", web_query="unverified proposed phrase",
                                   api_key="test-only", timeout=10)
    assert sent == ["legacy Malaysia"]


@pytest.mark.parametrize("bad", ["", "  ", "word " * 13, "x" * 161, "RM3000 advice", "中文", 12])
def test_empty_or_invalid_search_phrase_falls_back_without_rejecting_proposal(bad):
    plan = interpreter._public_plan(make_proposal(bad), "Simpanan saya?")
    assert plan.search_query == ""
    assert policy._web_search_query(plan) == ""
    assert policy.research_query(plan) == policy.research_query(replace(plan, search_query=""))


def test_old_stored_proposal_and_kb_query_are_unchanged():
    data = make_proposal("savings habits").model_dump()
    del data["public"]["search_query"]
    old = interpreter.load_proposal(data)
    old_plan = interpreter._public_plan(old, "Simpanan saya?")
    new_plan = interpreter._public_plan(make_proposal("savings habits"), "Simpanan saya?")
    assert old.public.search_query is None
    assert policy._web_search_query(old_plan) == ""
    assert policy.research_query(old_plan) == policy.research_query(new_plan)
    assert replace(new_plan, search_query="") == old_plan
    assert service._subject_subqueries(old_plan) == service._subject_subqueries(new_plan)
    assert service._part_subqueries(old_plan) == service._part_subqueries(new_plan)


def test_part_phrase_is_selected_without_overlap_reordering():
    plan = policy.QuestionPlan("topic", False, True, "stable",
                               required_facts=("payment rules PRIVATE 999",), part_ids=("p1",),
                               search_query="general credit cards",
                               part_search_queries=("credit card payment rules",))
    first = policy._web_search_query(plan, RequestedPart("p1", "payment rules PRIVATE 999"))
    assert first == "credit card payment rules Malaysia"
    assert "PRIVATE" not in first and "999" not in first


def test_web_search_phrase_does_not_reach_extraction_or_window_selection(monkeypatch):
    seen = {}
    result = web_research.WebResult("Example", "https://example.com/page", "Short snippet.", 0.7)
    def search(query, **kwargs):
        seen["search"] = query
        return [result]
    def extract(urls, **kwargs):
        seen["extraction"] = kwargs["query"]
        return {result.url: "Full source passage."}
    monkeypatch.setattr(web_research, "search_web", search)
    monkeypatch.setattr(web_research, "extract_passages", extract)
    web_research.research_evidence("rutin menabung Malaysia", web_query="saving habits Malaysia",
                                   web_query_guard=lambda new, old: new,
                                   api_key="test-only", timeout=10)
    assert seen == {"search": "saving habits Malaysia", "extraction": "saving habits Malaysia"}


def test_mixed_domain_financial_search_keeps_existing_guard():
    plan = policy.QuestionPlan("topic", False, True, "stable", required_facts=("finance", "science"),
        part_domains=("finance", "non_finance"), part_entities=((), ()),
        search_query="finance and science")
    assert policy.financial_search_plan(plan).search_query == ""


def test_malay_mixed_question_gets_different_part_queries_without_searching_nonfinance():
    proposal = interpreter.IntentProposal.model_validate({
        "route": "financial_education", "response_language": "ms",
        "public": {"topic": "faedah dan bajet", "subject_domain": "mixed",
                   "parts": [
                       {"fact": "faedah berganda", "domain": "finance", "search_query": "compound interest savings"},
                       {"fact": "belanjawan bulanan", "domain": "finance", "search_query": "monthly budget planning"},
                       {"fact": "cahaya", "domain": "non_finance", "search_query": "light physics"},
                   ]}})
    plan = interpreter._public_plan(proposal, "Terangkan faedah berganda dan bajet serta cahaya")
    search = policy.financial_search_plan(plan)
    parts = policy.requested_parts(search)
    assert [p.id for p in parts] == ["p1", "p2"]
    assert policy._web_search_query(search, parts[0]) == "compound interest savings Malaysia"
    assert policy._web_search_query(search, parts[1]) == "monthly budget planning Malaysia"
    assert search.part_search_queries == ("compound interest savings", "monthly budget planning")


def test_part_search_phrase_validation_and_part_id_survival():
    part = interpreter.PublicPart(fact="example", domain="finance", search_query="word " * 13)
    assert part.search_query is None
    plan = policy.QuestionPlan("topic", False, True, "stable", required_facts=("one", "two"),
        part_ids=("p1", "p2"), part_domains=("finance", "finance"), part_entities=((), ()),
        part_search_queries=("first concept", "second concept"))
    from app.rag.research_coverage import plan_without_parts
    remaining = plan_without_parts(plan, ("p1",))
    assert remaining.part_ids == ("p2",)
    assert policy._web_search_query(remaining, policy.requested_parts(remaining)[0]) == "second concept Malaysia"
