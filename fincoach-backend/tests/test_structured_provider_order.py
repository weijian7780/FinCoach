"""Provider order changes must preserve roles, fallback time, and writing policy."""
import os
import subprocess
import sys

import pytest
from app import llm
from app.rag import verifier


@pytest.fixture
def providers(monkeypatch):
    items = [llm._Provider("primary", "https://primary.invalid", "dummy", "nemotron"),
             llm._Provider("fallback", "https://fallback.invalid", "dummy", "gemini")]
    monkeypatch.setattr(llm, "_providers", lambda: items.copy())
    monkeypatch.setattr(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120)
    monkeypatch.setattr(llm, "LLM_PRIMARY_TIMEOUT_SECONDS", 110)
    monkeypatch.setattr(llm, "LLM_FALLBACK_TIMEOUT_SECONDS", 18)
    monkeypatch.setattr(llm, "COACH_STRUCTURED_TIMEOUT_SECONDS", 15)
    return items


@pytest.mark.parametrize("value,expected", [(None, "primary_first"), ("invalid", "primary_first"),
                                           ("fallback_first", "fallback_first")])
def test_setting_validation(value, expected):
    env = os.environ.copy()
    env.pop("COACH_STRUCTURED_PROVIDER_ORDER", None)
    if value is not None:
        env["COACH_STRUCTURED_PROVIDER_ORDER"] = value
    result = subprocess.run([sys.executable, "-c", "from app.config import COACH_STRUCTURED_PROVIDER_ORDER; print(COACH_STRUCTURED_PROVIDER_ORDER)"],
                            env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("order,roles", [("primary_first", ["primary", "fallback"]),
                                        ("fallback_first", ["fallback", "primary"])])
@pytest.mark.parametrize("validated", [False, True])
def test_order_and_failover(monkeypatch, providers, order, roles, validated):
    monkeypatch.setattr(llm, "COACH_STRUCTURED_PROVIDER_ORDER", order)
    seen = []
    def generate(_client, provider, _prompt, **kwargs):
        seen.append(provider.role)
        if len(seen) == 1:
            raise RuntimeError("synthetic transport failure")
        return llm.LLMResult("{}", provider.model)
    monkeypatch.setattr(llm, "_generate_with_provider", generate)
    if validated:
        assert llm.generate_validated_interpretation("q", response_schema={}, validate=lambda s: s,
                                                     budget=llm.CoachRequestBudget.start()) == "{}"
    else:
        assert llm.generate_structured_result("q").model == providers[0 if order == "fallback_first" else 1].model
    assert seen == roles


def test_structured_timeout_reserves_primary_share(monkeypatch, providers):
    monkeypatch.setattr(llm, "COACH_STRUCTURED_PROVIDER_ORDER", "fallback_first")
    clock = [0.0]
    monkeypatch.setattr(llm, "monotonic", lambda: clock[0])
    seen = []
    def generate(_client, provider, _prompt, **kwargs):
        seen.append((provider.role, kwargs["timeout_seconds"]))
        if len(seen) == 1:
            clock[0] += kwargs["timeout_seconds"]
            raise TimeoutError("synthetic timeout")
        return llm.LLMResult("{}", provider.model)
    monkeypatch.setattr(llm, "_generate_with_provider", generate)
    llm.generate_structured_result("q")
    assert seen == [("fallback", 12.0), ("primary", 3.0)]


def test_interpreter_schema_rejection_uses_primary_backup(monkeypatch, providers):
    monkeypatch.setattr(llm, "COACH_STRUCTURED_PROVIDER_ORDER", "fallback_first")
    seen = []
    def generate(_client, provider, prompt, **kwargs):
        seen.append((provider.role, prompt, kwargs["timeout_seconds"]))
        return llm.LLMResult(provider.role, provider.model)
    def validate(content):
        if content == "fallback":
            raise ValueError("synthetic invalid proposal")
        return "accepted"
    monkeypatch.setattr(llm, "_generate_with_provider", generate)
    assert llm.generate_validated_interpretation("q", response_schema={}, validate=validate,
                                                 budget=llm.CoachRequestBudget.start()) == "accepted"
    assert [row[0] for row in seen] == ["fallback", "primary"]
    assert "PREVIOUS PROPOSAL REJECTED" in seen[1][1]
    assert all(0 < row[2] <= 15 for row in seen)


@pytest.mark.parametrize("role_index", [0, 1])
def test_single_provider(monkeypatch, providers, role_index):
    monkeypatch.setattr(llm, "COACH_STRUCTURED_PROVIDER_ORDER", "fallback_first")
    monkeypatch.setattr(llm, "_providers", lambda: [providers[role_index]])
    monkeypatch.setattr(llm, "_generate_with_provider", lambda _c, p, _q, **kw: llm.LLMResult("{}", p.model))
    assert llm.generate_structured_result("q").model == providers[role_index].model


def test_writing_and_checker_remain_primary(monkeypatch, providers):
    monkeypatch.setattr(llm, "COACH_STRUCTURED_PROVIDER_ORDER", "fallback_first")
    monkeypatch.setattr(llm, "_generate_with_provider", lambda _c, p, _q, **kw: llm.LLMResult("answer", p.model))
    assert llm.generate_result("q").model == "nemotron"
    monkeypatch.setattr(verifier, "LLM_PRIMARY_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_API_KEY", "dummy")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_MODEL", "nemotron")
    assert verifier._verifier_settings()[2:] == ("nemotron", {"extra_body": {"reasoning": {"enabled": False}}})
