"""Writer backup isolation, privacy and checker outage recovery."""
import pytest
from app import llm
from app.rag import verifier
from app.rag.grounding import GroundingClaim


@pytest.fixture
def slot(monkeypatch):
    monkeypatch.setattr(llm, "COACH_WRITER_FALLBACK_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(llm, "COACH_WRITER_FALLBACK_API_KEY_ENV", "TEST_BACKUP_CREDENTIAL")
    monkeypatch.setattr(llm, "COACH_WRITER_FALLBACK_MODEL", "deepseek/deepseek-v4.1-flash-1017")
    monkeypatch.setenv("TEST_BACKUP_CREDENTIAL", "synthetic-test-value")
    providers = [llm._Provider("primary", "https://openrouter.ai/api/v1", "dummy", "nemotron"),
                 llm._Provider("fallback", "https://gemini.invalid", "dummy", "gemini")]
    monkeypatch.setattr(llm, "_providers", lambda: providers.copy())
    return providers


def test_writing_and_structured_chains(slot, monkeypatch):
    monkeypatch.setattr(llm, "COACH_STRUCTURED_PROVIDER_ORDER", "fallback_first")
    assert [p.role for p in llm._writing_providers()] == ["primary", "writer_fallback"]
    assert [p.model for p in llm._structured_providers()] == ["gemini", "nemotron"]


@pytest.mark.parametrize("tools", [False, True])
def test_privacy_policy(slot, tools):
    policy = llm._provider_request_policy(llm._writer_fallback_provider(), tool_request=tools)
    assert policy.extra_body == {"reasoning": {"enabled": False},
        "provider": {"data_collection": "deny", "require_parameters": True}}
    assert policy.reasoning_mode == "disabled"
    assert not policy.replays_reasoning_content


def test_writer_outage_uses_backup_without_secret_log(slot, monkeypatch, caplog):
    seen = []
    def generate(factory, provider, prompt, **kwargs):
        seen.append(provider.role)
        if provider.role == "primary":
            raise RuntimeError("synthetic outage")
        return llm.LLMResult("answer", provider.model)
    monkeypatch.setattr(llm, "_generate_with_provider", generate)
    assert llm.generate_result("question").content == "answer"
    assert seen == ["primary", "writer_fallback"]
    assert "synthetic-test-value" not in caplog.text


def test_missing_credential_fails_closed(slot, monkeypatch):
    monkeypatch.delenv("TEST_BACKUP_CREDENTIAL")
    with pytest.raises(RuntimeError, match="not configured"):
        llm._writing_providers()


def test_unset_preserves_original_chain(monkeypatch):
    for name in ("BASE_URL", "API_KEY_ENV", "MODEL"):
        monkeypatch.setattr(llm, "COACH_WRITER_FALLBACK_" + name, "")
    assert llm._writing_providers() == llm._providers()


def test_checker_last_resort_after_transport_outage(slot, monkeypatch):
    monkeypatch.setattr(verifier, "LLM_PRIMARY_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_API_KEY", "dummy")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_MODEL", "nemotron")
    seen = []
    def check(*args, _fallback=False, **kwargs):
        seen.append(_fallback)
        return verifier.GroundingVerification({1: "supported"} if _fallback else {},
            error_code=None if _fallback else "verifier_http_error")
    monkeypatch.setattr(verifier, "_verify_grounding_claims_once", check)
    context = verifier.ResearchVerificationContext("question", "draft", ())
    result = verifier.verify_grounding_claims([GroundingClaim(1, "claim", (1,))],
        ["source"], timeout_seconds=15, research_context=context)
    assert seen == [False, True]
    assert result.all_supported
    assert verifier._verifier_settings(fallback=True)[2].startswith("deepseek/")
    assert verifier._verifier_settings(fallback=True)[3]["extra_body"]["provider"]["data_collection"] == "deny"


def test_agent_and_correction_use_backup(slot, monkeypatch):
    seen = []
    def agent(factory, provider, prompt, **kwargs):
        seen.append(provider.role)
        if provider.role == "primary":
            raise RuntimeError("outage")
        return llm.AgentLLMResult("answer", provider.model)
    monkeypatch.setattr(llm, "_generate_agent_with_provider", agent)
    assert llm.generate_agent_result("q", tool_definitions=[], tool_executor=lambda *a: {}).content == "answer"
    assert seen == ["primary", "writer_fallback"]
    monkeypatch.setattr(llm, "_generate_with_provider", agent)
    seen.clear()
    assert llm.generate_fallback_result("repair").content == "answer"
    assert seen == ["writer_fallback"]


def test_backup_uses_fallback_time_window(slot, monkeypatch):
    monkeypatch.setattr(llm, "LLM_FALLBACK_TIMEOUT_SECONDS", 7)
    monkeypatch.setattr(llm, "COACH_REQUEST_DEADLINE_SECONDS", 120)
    assert llm.CoachRequestBudget.start().timeout_for("writer_fallback") == 7


def test_wire_payload_does_not_relax_privacy_on_error(slot):
    from types import SimpleNamespace
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        raise RuntimeError("No provider qualifies")
    factory = lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(RuntimeError, match="No provider qualifies"):
        llm._generate_with_provider(factory, llm._writer_fallback_provider(), "q",
            reasoning_effort="high", timeout_seconds=5)
    assert len(requests) == 1
    assert requests[0]["extra_body"]["reasoning"] == {"enabled": False}
    assert requests[0]["extra_body"]["provider"]["data_collection"] == "deny"
