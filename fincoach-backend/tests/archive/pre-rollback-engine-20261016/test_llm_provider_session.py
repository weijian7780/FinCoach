from types import SimpleNamespace
import pytest


def provider(role="primary", endpoint="https://user:secret@example.org/v1?key=secret", model="model"):
    return SimpleNamespace(role=role, base_url=endpoint, model=model)


def test_successful_fallback_is_sticky_for_the_request():
    from app.llm_provider_session import ProviderSession, ProviderCooldown
    session = ProviderSession(cooldown=ProviderCooldown())
    primary, fallback = provider(), provider("fallback", "https://fallback.org/v1")
    session.note_failure(primary, SimpleNamespace(status_code=429))
    session.note_success(fallback)
    assert session.eligible_roles([primary, fallback]) == [fallback]


def test_cooldown_has_one_probe_and_ignores_credentials():
    from app.llm_provider_session import ProviderCooldown, provider_identity
    clock = [0.0]
    health = ProviderCooldown(clock=lambda: clock[0])
    first = provider_identity(provider())
    assert first == provider_identity(provider(endpoint="https://other:changed@example.org/v1?key=changed#fragment"))
    health.fail(first)
    assert not health.admit(first)
    clock[0] = 31
    assert health.admit(first)
    assert not health.admit(first)
    health.success(first)
    assert health.admit(first)


@pytest.mark.parametrize("error", [ValueError("bad JSON"), TimeoutError(), SimpleNamespace(status_code=400)])
def test_request_errors_do_not_poison_another_request(error):
    from app.llm_provider_session import ProviderSession, ProviderCooldown
    health = ProviderCooldown()
    primary = provider()
    ProviderSession(cooldown=health).note_failure(primary, error)
    assert ProviderSession(cooldown=health).eligible_roles([primary]) == [primary]


def test_attempt_and_transient_limits_are_shared_by_children():
    from app.llm_provider_session import ProviderSession
    from app.llm import CoachRequestBudget
    session = ProviderSession()
    budget = CoachRequestBudget.start(provider_session=session)
    child = budget.for_stage(max_seconds=10)
    assert child.provider_session is session
    for _ in range(15):
        session.begin_attempt()
    with pytest.raises(RuntimeError, match="provider_attempt_limit"):
        child.provider_session.begin_attempt()
    error = SimpleNamespace(status_code=429, response=SimpleNamespace(headers={"retry-after": "1"}))
    assert session.retry_delay(error) == 1
    assert session.retry_delay(error) is None


def test_sdk_boundary_enforces_attempt_ceiling():
    from app import llm
    from app.llm_provider_session import ProviderSession, ProviderCooldown
    count = []
    def create(**request):
        count.append(request["model"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="done"), finish_reason="stop")])
    factory = lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    session = ProviderSession(cooldown=ProviderCooldown())
    p = llm._Provider("primary", "https://example.org/v1", "unused", "model")
    for _ in range(15):
        llm._generate_with_provider(factory, p, "public", reasoning_effort="high",
            timeout_seconds=1, provider_session=session)
    with pytest.raises(RuntimeError, match="provider_attempt_limit"):
        llm._generate_with_provider(factory, p, "public", reasoning_effort="high",
            timeout_seconds=1, provider_session=session)
    assert len(count) == 15


def test_structured_failover_keeps_next_writer_on_working_fallback():
    from unittest.mock import patch
    from app import llm
    from app.llm_provider_session import ProviderSession, ProviderCooldown
    calls = []
    class Limited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "30"})
    def factory(**kw):
        def create(**request):
            calls.append(request["model"])
            if request["model"] == "primary":
                raise Limited()
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    session = ProviderSession(cooldown=ProviderCooldown())
    providers = [llm._Provider("primary", "https://example.org", "unused", "primary"),
                 llm._Provider("fallback", "https://other.org", "unused", "fallback")]
    with patch("openai.OpenAI", side_effect=factory), patch.object(llm, "_providers", return_value=providers):
        budget = llm.CoachRequestBudget.start(provider_session=session)
        llm.generate_structured_result("public", budget=budget, reserve_after_seconds=0)
        llm.generate_result("public", budget=budget, allow_failover=False)
    assert calls == ["primary", "fallback", "fallback"]
    assert session.logical_calls == 2 and session.attempts == 3


def test_research_token_budget_reaches_sdk_without_changing_default():
    from unittest.mock import patch
    from app import llm
    from app.llm_provider_session import ProviderSession, ProviderCooldown
    requests = []
    def factory(**kw):
        def create(**request):
            requests.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Complete answer.'), finish_reason='stop')])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    providers = [llm._Provider('primary', 'https://example.org', 'unused', 'primary')]
    with patch('openai.OpenAI', side_effect=factory), patch.object(llm, '_providers', return_value=providers), \
         patch.object(llm, '_configured', return_value=True), patch.object(llm, 'LLM_PRIMARY_MAX_TOKENS', 4096):
        budget = llm.CoachRequestBudget.start(provider_session=ProviderSession(cooldown=ProviderCooldown()))
        llm.generate_result('Public research', budget=budget, max_tokens=8192)
        llm.generate_result('Ordinary coaching', budget=budget)
    assert [r['max_tokens'] for r in requests] == [8192,4096]
    assert budget.provider_session.logical_calls == 2


def test_provider_selection_does_not_lease_an_unused_half_open_fallback():
    from app.llm_provider_session import ProviderSession, ProviderCooldown, provider_identity
    clock = [0.0]
    health = ProviderCooldown(clock=lambda: clock[0])
    primary, fallback = provider(), provider('fallback', 'https://fallback.org/v1')
    health.fail(provider_identity(fallback))
    clock[0] = 31
    selected = ProviderSession(cooldown=health).eligible_roles([primary, fallback])
    assert selected == [primary, fallback]
    # Merely considering the fallback must not acquire its one probe lease.
    assert health.admit(provider_identity(fallback))


def test_mixed_failures_and_children_cannot_exceed_nine_logical_tasks():
    from unittest.mock import patch
    from app import llm
    from app.llm_provider_session import ProviderSession, ProviderCooldown
    calls = []
    class Limited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={'retry-after': '0'})
    def factory(**kwargs):
        def create(**request):
            calls.append(request['model'])
            if request['model'] == 'primary':
                raise Limited()
            # Format/length errors do not reset the shared HTTP/task ledger.
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content='{invalid'), finish_reason='length')])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    providers = [llm._Provider('primary', 'https://primary.test', 'unused', 'primary'),
                 llm._Provider('fallback', 'https://fallback.test', 'unused', 'fallback')]
    session = ProviderSession(cooldown=ProviderCooldown())
    root = llm.CoachRequestBudget.start(provider_session=session)
    with patch('openai.OpenAI', side_effect=factory), patch.object(llm, '_providers', return_value=providers):
        for _ in range(9):
            with pytest.raises(RuntimeError, match='structured_output_truncated'):
                llm.generate_structured_result('public', budget=root.for_stage(max_seconds=15), reserve_after_seconds=0)
        with pytest.raises(RuntimeError, match='provider_logical_call_limit'):
            llm.generate_result('public', budget=root)
    assert session.logical_calls == 9 and session.attempts == len(calls) == 11
    assert session.transient_retries == 1
