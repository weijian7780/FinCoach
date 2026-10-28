"""The answer checker runs on the primary provider (Gemini) when configured."""
from types import SimpleNamespace

from app.rag import verifier
from app.rag.grounding import GroundingClaim


def _configure(monkeypatch, *, primary):
    monkeypatch.setattr(verifier, "LLM_PRIMARY_BASE_URL", "https://gemini.example/" if primary else "")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_API_KEY", "primary-key" if primary else "")
    monkeypatch.setattr(verifier, "LLM_PRIMARY_MODEL", "gemini-test" if primary else "")
    monkeypatch.setattr(verifier, "LLM_BASE_URL", "https://deepseek.example/")
    monkeypatch.setattr(verifier, "LLM_API_KEY", "fallback-key")
    monkeypatch.setattr(verifier, "LLM_MODEL", "deepseek-test")


def test_primary_provider_is_the_checker_without_the_deepseek_switch(monkeypatch):
    _configure(monkeypatch, primary=True)
    assert verifier._verifier_settings() == ("https://gemini.example/", "primary-key", "gemini-test", {})


def test_without_a_primary_the_existing_provider_keeps_its_options(monkeypatch):
    _configure(monkeypatch, primary=False)
    base_url, _, model, extra = verifier._verifier_settings()
    assert (base_url, model) == ("https://deepseek.example/", "deepseek-test")
    assert extra == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_checker_request_goes_to_the_primary_model(monkeypatch):
    _configure(monkeypatch, primary=True)
    sent = {}

    class Completions:
        def create(self, **kwargs):
            sent.update(kwargs)
            message = SimpleNamespace(content='{"claims": []}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                                   usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    def client(*, timeout_seconds):
        return SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(verifier, "_create_verifier_client", client)
    verifier.verify_grounding_claims([GroundingClaim(1, "PTPTN provides education loans.", (1,))],
                                     ["PTPTN provides education loans."], timeout_seconds=5)
    assert sent["model"] == "gemini-test" and "extra_body" not in sent
