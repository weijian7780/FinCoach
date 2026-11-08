"""Luna-everywhere stage: capability-based requests, precise rejections, null lists,
short follow-up searches, checker roles. Network-free; all data synthetic."""
import json
from datetime import date
from types import SimpleNamespace

import pytest

from app import llm, model_capabilities as caps
from app.rag import request_interpretation as intent
from app.rag import search_privacy, verifier

OPENROUTER = "https://openrouter.ai/api/v1"


@pytest.fixture
def listing(monkeypatch):
    """A published capability list, as OpenRouter's /models would return it."""
    caps.clear_cache()
    table = {"openai/gpt-6-luna": frozenset({"max_tokens", "response_format", "structured_outputs",
                                             "reasoning", "seed"}),
             "plain/model": frozenset({"max_tokens", "temperature"})}
    monkeypatch.setattr(caps, "_fetch", lambda url: table)
    yield table
    caps.clear_cache()


# ---- Parameters follow the model's published list -------------------------------------

def test_unlisted_parameters_are_dropped_and_call_keys_kept(listing):
    request = {"model": "openai/gpt-6-luna", "messages": [], "stream": False, "extra_body": {"x": 1},
               "max_tokens": 10, "temperature": 0, "top_p": 1}
    fitted = caps.fit_request(OPENROUTER, request)
    assert fitted == {"model": "openai/gpt-6-luna", "messages": [], "stream": False,
                      "extra_body": {"x": 1}, "max_tokens": 10}


def test_request_is_unchanged_without_a_listing(monkeypatch):
    caps.clear_cache()
    monkeypatch.setattr(caps, "_fetch", lambda url: (_ for _ in ()).throw(ConnectionError("offline")))
    request = {"model": "openai/gpt-6-luna", "messages": [], "temperature": 0}
    assert caps.fit_request(OPENROUTER, request) is request
    assert caps.fit_request("https://generativelanguage.googleapis.com/v1beta/openai/", request) is request
    caps.clear_cache()


def test_unknown_model_keeps_its_request(listing):
    request = {"model": "not/listed", "messages": [], "temperature": 0}
    assert caps.fit_request(OPENROUTER, request) is request


def test_structured_output_form_follows_capabilities(listing):
    schema = {"type": "object"}
    assert caps.structured_response_format(OPENROUTER, "openai/gpt-6-luna", schema, "x") == {
        "type": "json_schema", "json_schema": {"name": "x", "schema": schema}}
    assert caps.structured_response_format(OPENROUTER, "plain/model", schema, "x") is None


def test_structured_call_sends_the_schema_and_omits_temperature(monkeypatch, listing):
    sent = {}

    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"),
                                                            finish_reason="stop")], usage=None)
    provider = llm._Provider("writer_fallback", OPENROUTER, "k", "openai/gpt-6-luna")
    llm._generate_with_provider(Client, provider, "q", reasoning_effort="low", timeout_seconds=5,
                                structured=True, response_schema={"type": "object"})
    assert sent["response_format"]["type"] == "json_schema"
    assert "temperature" not in sent
    assert sent["extra_body"]["provider"]["data_collection"] == "deny"


# ---- Precise rejections let the model correct itself --------------------------------

def _spending(**read):
    return intent.IntentProposal.model_validate({
        "route": "personal_finance", "response_language": "en",
        "read": {"operation": "get_spending_summary", "period": {"kind": "this_month"},
                 "category": {"decision": "named", "name": "food", "built_in": "Food"}, **read}})


def test_rejection_names_the_field_that_broke_the_rule():
    with pytest.raises(intent.ProposalRejected) as error:
        intent.compile_read(_spending(transaction_type="expense", result_mode="expense_total"), date(2026, 11, 8))
    message = str(error.value)
    assert message.startswith("Transaction filters require search_transactions")
    assert "read.transaction_type" in message and "read.result_mode" not in message


@pytest.mark.parametrize("read", [{}, {"result_mode": "expense_total"}])
def test_the_rule_accepts_exactly_what_it_accepted_before(read):
    assert intent.compile_read(_spending(**read), date(2026, 11, 8)).tool_name == "get_spending_summary"


@pytest.mark.parametrize("read", [{"transaction_type": "income"}, {"merchant": "Shop"}, {"limit": 5},
                                  {"result_mode": "count"}])
def test_the_rule_still_rejects_what_it_rejected_before(read):
    with pytest.raises(intent.ProposalRejected) as error:
        intent.compile_read(_spending(**read), date(2026, 11, 8))
    assert f"read.{next(iter(read))}" in str(error.value)


def test_clarification_rejection_names_positions_not_wording():
    with pytest.raises(ValueError) as error:
        intent.IntentProposal.model_validate({
            "route": "financial_education", "response_language": "en",
            "public": {"topic": "loans", "required_facts": ["loan rate"],
                       "clarification_facts": ["my secret loan"], "subject_domain": "finance"}})
    assert "public.clarification_facts[0]" in str(error.value)
    assert "my secret loan" not in str(error.value).split("Input should")[0].split("[type=")[0]


def test_null_lists_become_empty_lists_through_nested_models():
    raw = json.dumps({"route": "financial_education", "response_language": "en", "actions": None,
                      "public": {"topic": "loans", "required_facts": None, "entities": None,
                                 "subject_domain": "finance"}})
    proposal = intent.IntentProposal.model_validate_json(intent._null_lists_as_empty(raw))
    assert proposal.actions == [] and proposal.public.entities == [] and proposal.public.required_facts == []
    with pytest.raises(Exception):
        intent.IntentProposal.model_validate_json(raw)
    assert intent._null_lists_as_empty("{not json") == "{not json"


# ---- Short follow-up searches ---------------------------------------------------------

def _guard(monkeypatch, reply, *, names=(), jurisdiction="Malaysia"):
    monkeypatch.setattr(search_privacy, "owned_names", lambda client, user_id: tuple(names))
    calls = []

    def generate(prompt, **kwargs):
        calls.append(prompt)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=json.dumps(reply))
    guard = search_privacy.make_search_guard(None, "u", generate=generate, budget=llm.CoachRequestBudget.start(),
                                             jurisdiction=jurisdiction)
    return guard, calls


GOOD = {"search_query": "share trading account documents", "general_public": True,
        "same_financial_subject": True, "contains_personal_context": False}
LONG = ("General step-by-step process to open a share trading account in Malaysia Required documents "
        "for a general share trading account application")


def test_long_follow_up_search_is_shortened(monkeypatch):
    guard, calls = _guard(monkeypatch, GOOD)
    assert guard(LONG, "legacy", timeout=10, shorten=True) == "share trading account documents Malaysia"
    assert len(calls) == 1 and "in Malaysia" in calls[0]


def test_failed_shortening_sends_the_clean_text_as_before(monkeypatch):
    guard, _ = _guard(monkeypatch, RuntimeError("down"))
    assert guard(LONG, "legacy", timeout=10, shorten=True) == LONG


def test_clean_first_search_is_not_rewritten(monkeypatch):
    guard, calls = _guard(monkeypatch, GOOD)
    assert guard("how to buy shares Malaysia", "legacy", timeout=10) == "how to buy shares Malaysia"
    assert calls == []


def test_jurisdiction_comes_from_the_question_not_a_fixed_word(monkeypatch):
    guard, calls = _guard(monkeypatch, GOOD, jurisdiction="Singapore")
    assert guard(LONG, "legacy", timeout=10, shorten=True).endswith("Singapore")
    assert "in Singapore" in calls[0] and "Malaysia" not in calls[0].split("data:")[0]


def test_owned_name_still_blocks_or_generalises(monkeypatch):
    guard, _ = _guard(monkeypatch, GOOD, names=("Laptop",))
    assert guard("my Laptop goal saving habits", "legacy", timeout=10, shorten=True) == \
        "share trading account documents Malaysia"
    guard, _ = _guard(monkeypatch, {**GOOD, "search_query": "Laptop saving"}, names=("Laptop",))
    assert guard("my Laptop goal", "legacy", timeout=10) is search_privacy.SKIP_UNSAFE_SEARCH


# ---- Checker roles --------------------------------------------------------------------

def test_luna_checker_uses_the_writer_privacy_rules_and_nemotron_backs_it_up(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    for module in (verifier, llm):
        monkeypatch.setattr(module, "COACH_WRITER_FALLBACK_BASE_URL", OPENROUTER, raising=False)
        monkeypatch.setattr(module, "COACH_WRITER_FALLBACK_MODEL", "openai/gpt-6-luna", raising=False)
    monkeypatch.setattr(llm, "COACH_WRITER_FALLBACK_API_KEY_ENV", "OPENROUTER_API_KEY")
    monkeypatch.setattr(verifier, "COACH_VERIFIER_BASE_URL", OPENROUTER)
    monkeypatch.setattr(verifier, "COACH_VERIFIER_API_KEY_ENV", "OPENROUTER_API_KEY")
    monkeypatch.setattr(verifier, "COACH_VERIFIER_MODEL", "openai/gpt-6-luna")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_BASE_URL", OPENROUTER)
    monkeypatch.setattr(verifier, "LLM_PRIMARY_API_KEY", "dummy")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_MODEL", "nvidia/nemotron")
    first = verifier._verifier_settings()
    backup = verifier._verifier_settings(fallback=True)
    assert first[2] == "openai/gpt-6-luna"
    assert first[3]["extra_body"]["provider"]["data_collection"] == "deny"
    assert backup[2] == "nvidia/nemotron"


def test_literal_rejection_names_the_allowed_values_not_the_input():
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as caught:
        intent.IntentProposal.model_validate({"route": "casual", "response_language": "en",
                                              "requested_output": "SECRET-USER-TEXT"})
    error = caught.value
    fields = [llm._rejected_field(e) for e in error.errors()]
    item = next(f for f in fields if f["field"] == "requested_output")
    assert item["rule"].startswith("must be one of ") and "SECRET-USER-TEXT" not in item["rule"]
    feedback = llm._interpretation_feedback(error, fields)
    assert "requested_output: must be one of" in feedback
