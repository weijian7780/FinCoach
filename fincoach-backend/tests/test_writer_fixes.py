"""Presentation repair and bounded checker-format recovery regressions."""
import json
from types import SimpleNamespace as NS

import pytest

from app.rag import verifier
from app.rag.grounding import DISCLAIMER, GroundingClaim
from app.rag.research_answer import normalize_research_layout


@pytest.mark.parametrize("variant", ["**{}:**", "**{}**:", "**{} :**"])
@pytest.mark.parametrize("heading", ["Insight", "Recommended action", "Educational guidance"])
def test_heading_colon_variations(variant, heading):
    original = f"**Insight**\nA supported fact [S1].\n\n**Recommended action**\nRead the guide [S1].\n\n**Educational guidance**\n{DISCLAIMER}"
    draft = original.replace(f"**{heading}**", variant.format(heading))
    assert normalize_research_layout(draft) == original


def test_heading_repair_preserves_content_and_duplicates():
    draft = f"**Insight:**\nA fact [S1].\n**Insight:**\nAnother fact [S1].\n**Educational guidance:**\n{DISCLAIMER}"
    result = normalize_research_layout(draft)
    assert result.count("**Insight**") == 2
    assert "A fact [S1]." in result and "Another fact [S1]." in result
    inline = f"**Insight:** A fact [S1].\n**Educational guidance**\n{DISCLAIMER}"
    assert "**Insight:** A fact [S1]." in normalize_research_layout(inline)


def response(payload, finish="stop"):
    return NS(choices=[NS(message=NS(content=payload if isinstance(payload, str) else json.dumps(payload)),
                          finish_reason=finish)], usage=NS(prompt_tokens=10, completion_tokens=5))


def verdict(value="supported"):
    return {"claims": [{"id": 1, "verdict": value, "source_index": 1 if value == "supported" else None}]}


def setup(monkeypatch, responses, *, elapsed=0, fallback=True):
    for key, value in {"LLM_PRIMARY_BASE_URL": "https://openrouter.ai/api/v1",
                       "LLM_PRIMARY_API_KEY": "test-only", "LLM_PRIMARY_MODEL": "nemotron-test",
                       "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/" if fallback else "",
                       "LLM_API_KEY": "test-only" if fallback else "", "LLM_MODEL": "gemini-test" if fallback else ""}.items():
        monkeypatch.setattr(verifier, key, value)
    clock, calls, timeouts = [0.0], [], []
    replies = iter(responses)
    def create(**kwargs):
        calls.append(kwargs)
        clock[0] += elapsed
        return next(replies)
    def factory(**kwargs):
        timeouts.append(kwargs["timeout_seconds"])
        return NS(chat=NS(completions=NS(create=create)))
    monkeypatch.setattr(verifier, "monotonic", lambda: clock[0])
    monkeypatch.setattr(verifier, "_create_verifier_client", factory)
    return calls, timeouts


def check(timeout=10, context=None):
    return verifier.verify_grounding_claims([GroundingClaim(1, "A fact.", (1,))], ["A fact."],
                                            timeout_seconds=timeout, research_context=context)


@pytest.mark.parametrize("broken", [response("{"), response({}), response(verdict(), "length")])
def test_broken_reply_retries_same_provider_once(monkeypatch, broken):
    calls, timeouts = setup(monkeypatch, [broken, response(verdict())], elapsed=2)
    result = check()
    assert result.all_supported
    assert [c["model"] for c in calls] == ["nemotron-test", "nemotron-test"]
    assert timeouts == [10, 8]
    assert result.prompt_tokens == 20 and result.completion_tokens == 10
    assert all(c["extra_body"] == {"reasoning": {"enabled": False}} for c in calls)


def test_two_broken_replies_then_gemini(monkeypatch, caplog):
    calls, timeouts = setup(monkeypatch, [response("{"), response({}), response(verdict())], elapsed=2)
    with caplog.at_level("INFO", logger="uvicorn.error"):
        result = check()
    assert result.all_supported and result.model == "gemini-test"
    assert [c["model"] for c in calls] == ["nemotron-test", "nemotron-test", "gemini-test"]
    assert "extra_body" not in calls[-1]
    assert timeouts == [10, 8, 6]
    assert result.prompt_tokens == 30 and result.completion_tokens == 15
    assert '"attempt": 3' in caplog.text


@pytest.mark.parametrize("value", ["unsupported", "contradicted", "misapplied"])
def test_valid_rejection_is_final(monkeypatch, value):
    payload = verdict(value)
    payload["quality_errors"] = []
    calls, _ = setup(monkeypatch, [response(payload)])
    result = check(context=verifier.ResearchVerificationContext("q", "d", ()))
    assert result.verdicts == {1: value} and not result.error_code
    assert len(calls) == 1


def test_deadline_exhausted_after_first_broken_reply(monkeypatch):
    calls, _ = setup(monkeypatch, [response("{")], elapsed=10)
    result = check()
    assert result.error_code == "verifier_invalid_json" and len(calls) == 1


def test_expired_deadline_makes_no_call(monkeypatch):
    calls, _ = setup(monkeypatch, [])
    result = check(timeout=0)
    assert result.error_code == "verifier_timeout" and not calls


def test_no_fallback_stops_after_two_broken_replies(monkeypatch):
    calls, _ = setup(monkeypatch, [response("{"), response("{")], fallback=False)
    assert check().error_code == "verifier_invalid_json"
    assert len(calls) == 2


def test_fallback_is_not_retried(monkeypatch):
    calls, _ = setup(monkeypatch, [response("{"), response("{"), response("{")])
    assert check().error_code == "verifier_invalid_json"
    assert len(calls) == 3


def test_no_gemini_when_retry_uses_remaining_deadline(monkeypatch):
    calls, timeouts = setup(monkeypatch, [response("{"), response("{")], elapsed=5)
    assert check().error_code == "verifier_invalid_json"
    assert len(calls) == 2 and timeouts == [10, 5]


def test_valid_rejection_after_retry_does_not_fall_back(monkeypatch):
    calls, _ = setup(monkeypatch, [response("{"), response(verdict("unsupported"))])
    assert check().verdicts == {1: "unsupported"}
    assert len(calls) == 2


def test_transport_error_is_not_a_format_retry(monkeypatch):
    calls, _ = setup(monkeypatch, [])
    def unavailable(**kwargs):
        raise TimeoutError
    monkeypatch.setattr(verifier, "_create_verifier_client", unavailable)
    assert check().error_code == "verifier_timeout"
    assert not calls
