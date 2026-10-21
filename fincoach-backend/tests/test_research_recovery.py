"""Recovery must improve coverage without relaxing trust or spending blindly."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.llm import CoachRequestBudget
from app.rag.research_policy import (
    EvidenceAssessment, QuestionPlan, assess_evidence, run_research_policy,
)
from app.rag.retrieval import RetrievedChunk
from app.rag.web_research import ResearchOutcome


def test_stage_budget_preserves_request_start():
    from app import llm
    with (patch.object(llm, "monotonic", return_value=30),
          patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "LLM_PRIMARY_TIMEOUT_SECONDS", 50)):
        stage = CoachRequestBudget(0).for_stage(max_seconds=15)
        assert stage.started_at == 0
        assert stage.remaining_seconds() == 15
        with patch.object(llm, "monotonic", return_value=42):
            assert stage.timeout_for("fallback") == 3
        with patch.object(llm, "monotonic", return_value=45):
            with pytest.raises(TimeoutError):
                stage.timeout_for("primary")


def test_research_checker_cannot_spend_explanation_reserve():
    from app import llm
    with (patch.object(llm, "monotonic", return_value=25),
          patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "LLM_PRIMARY_TIMEOUT_SECONDS", 50),
          patch.object(llm, "_providers", return_value=[SimpleNamespace(role="primary")]),
          patch.object(llm, "_generate_with_provider", return_value=SimpleNamespace(content="{}")) as call):
        llm.generate_structured_result("public", budget=CoachRequestBudget(0),
                                       reserve_after_seconds=30)
        assert call.call_args.kwargs["timeout_seconds"] <= 5


def test_primary_retry_wait_respects_stage_deadline():
    from app import llm
    with (patch.object(llm, "monotonic", return_value=10),
          patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "LLM_PRIMARY_TIMEOUT_SECONDS", 50),
          patch.object(llm, "sleep") as wait):
        stage = CoachRequestBudget(0).for_stage(max_seconds=2)
        assert not stage.wait_for_rate_limit(3)
        wait.assert_not_called()


def test_initial_generation_failover_shares_its_cap():
    from app import llm
    now = [30.0]
    def provider_call(*args, **kwargs):
        if args[1].role == "primary":
            assert kwargs["timeout_seconds"] == 12
            now[0] += 12
            raise TimeoutError()
        assert kwargs["timeout_seconds"] == 3
        return SimpleNamespace(content="done")
    with (patch.object(llm, "monotonic", side_effect=lambda: now[0]),
          patch.object(llm, "COACH_REQUEST_DEADLINE_SECONDS", 60),
          patch.object(llm, "LLM_PRIMARY_TIMEOUT_SECONDS", 50),
          patch.object(llm, "_configured", return_value=True),
          patch.object(llm, "_providers", return_value=[
              SimpleNamespace(role="primary", model="primary", base_url="https://example.org"),
              SimpleNamespace(role="fallback", model="fallback")]),
          patch.object(llm, "_generate_with_provider", side_effect=provider_call)):
        result = llm.generate_result("public", budget=CoachRequestBudget(0).for_stage(max_seconds=15))
        assert result.content == "done"


def chunk(text="Apply through the institution's official application portal.",
          url="https://www.ptptn.gov.my/application", title="PTPTN application"):
    return RetrievedChunk(
        id=-1, title=title, source="official", page_number=None, chunk_index=None,
        content=text, similarity=0.8, source_type="web", url=url, tier=1,
        confidence="established", checked_at="2026-10-03",
    )


def proposal(source, **changes):
    data = dict(status="partial", missing=["application documents"],
                conflicting=False, jurisdiction_matches=True, period_matches=True,
                support=[dict(source_id=1, quote=source.content)])
    data.update(changes)
    return SimpleNamespace(content=json.dumps(data))


def plan():
    return QuestionPlan("loan waiver application", False, True, "current",
                        entities=("PTPTN",), required_facts=("eligibility", "application"))


def test_assessment_repairs_missing_string_without_changing_support():
    source = chunk()
    model = MagicMock(return_value=proposal(source, missing="application documents"))
    result = assess_evidence(plan(), [source], generate=model)
    assert result.failure is None
    assert result.missing == ("application documents",)
    assert result.supported_quotes == ((1, source.content),)
    assert model.call_count == 1


def test_official_page_relevance_recognizes_parenthesized_institution_alias():
    from dataclasses import replace
    from app.rag.research_policy import _official_domains
    institution = replace(plan(), entities=("Employees Provident Fund (EPF)",))
    source = chunk("EPF members can apply for education withdrawal.",
                   url="https://www.kwsp.gov.my/en/member/education", title="Education withdrawal")
    assert _official_domains(institution, [source]) == ("www.kwsp.gov.my",)


@pytest.mark.parametrize("name,abbreviation,url", [
    ("Employees Provident Fund", "EPF", "https://www.kwsp.gov.my/en/member/education"),
    ("Kumpulan Wang Simpanan Pekerja", "KWSP", "https://www.kwsp.gov.my/ms/pendidikan"),
    ("Bank Negara Malaysia", "BNM", "https://www.bnm.gov.my/policy"),
])
def test_known_official_page_relevance_recognizes_initials_of_full_institution_name(name, abbreviation, url):
    from app.rag.research_policy import _official_domains
    institution = replace(plan(), entities=(name,))
    source = chunk(f"{abbreviation} members can apply through this portal.",
                   url=url, title="Application guidance")
    assert _official_domains(institution, [source]) == (url.split("/")[2],)


def test_public_policy_search_extracts_complete_context_on_first_pass():
    from app.rag import web_research as web
    found = web.WebResult("Application", chunk().url, "For employed:", .9)
    with (patch.object(web, "search_web", return_value=[found]),
          patch.object(web, "extract_passages", return_value={
              found.url: "For employed:\n* Identity document\n* Latest salary slip",
          }) as extract):
        result = web.research_evidence("application documents", api_key="test",
                                       public_policy=True, single_search=True)
    assert extract.call_args.kwargs["complete_context"] is True
    assert "Latest salary slip" in result.chunks[0].content


@pytest.mark.parametrize("subject", ["education withdrawal", "training assistance"])
def test_complete_page_selection_prioritizes_requested_subject_over_generic_introduction(subject):
    from app.rag.web_research import _complete_page_window
    introduction = (
        "The Public Benefits Institution publishes eligibility criteria, application process, "
        "required documents, Malaysia guidance and official instructions for every programme.\n\n"
        "## Programme overview\n\n" + "General overview. " * 140 + "\n\n"
    )
    section = f"## {subject.title()}\n\nWho qualifies:\n* Eligible students only\n\nDocuments:\n* Enrolment proof\n* Identification"
    query = f"{subject} eligibility criteria application process required documents Public Benefits Institution Malaysia"
    result = _complete_page_window(introduction + section, query, subject_query=subject)
    assert "Enrolment proof" in result
    assert "Eligible students only" in result
    assert len(result) <= 2000


def test_requested_section_does_not_inherit_preceding_programme_conditions():
    from app.rag.web_research import _complete_page_window
    preceding = "## Other withdrawals\n\nNo supporting documents are required.\n\n"
    requested = "## Education withdrawal\n\nEligibility:\n* Students only\n\nDocuments:\n* Enrolment proof"
    raw = "Navigation. " * 180 + "\n\n" + preceding + requested
    selected = _complete_page_window(raw, "education withdrawal eligibility required documents",
                                     subject_query="education withdrawal")
    assert "Enrolment proof" in selected
    assert "No supporting documents" not in selected


def test_long_exact_quote_keeps_qualifications_without_checker_retry():
    source = chunk("Applicants may apply. " * 45 + "Only if every eligibility condition is met.")
    assert 500 < len(source.content) < 1800
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(source)))
    assert result.failure is None
    assert result.supported_quotes == ((1, source.content),)


def test_quote_cannot_exceed_supplied_excerpt_bound():
    source = chunk("a" * 1801)
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(source)))
    assert result.failure == "assessment_invalid_schema"


def test_retry_receives_safe_error_codes_without_untrusted_field_names(caplog):
    source = chunk()
    first = proposal(source)
    invalid = json.loads(first.content)
    invalid["untrusted-private-field-name"] = "private value"
    prompts = []
    outputs = [SimpleNamespace(content=json.dumps(invalid)), proposal(source, status="sufficient", missing=[])]
    def model(prompt, **kwargs):
        prompts.append(prompt)
        return outputs.pop(0)
    from dataclasses import replace
    result = run_research_policy(replace(plan(), time_scope="stable"), [source], generate=model,
        budget=CoachRequestBudget.start(), api_key="test", web_enabled=True,
        max_results=4, timeout=4)
    assert "unknown:extra_forbidden" in prompts[1]
    assert "untrusted-private-field-name" not in prompts[1] + caplog.text
    assert "private value" not in caplog.text
    assert result.assessment.status == "sufficient"
    assert "_assessment_error_codes" not in result.diagnostics


@pytest.mark.parametrize("changes", [
    {"support": [{"source_id": "1", "quote": "An invented supporting quote."}]},
    {"conflicting": "false"}, {"missing": None}, {"unexpected": True},
    {"missing": [42]},
])
def test_assessment_error_does_not_claim_required_facts_are_missing(changes):
    source = chunk()
    result = assess_evidence(plan(), [source],
                             generate=MagicMock(return_value=proposal(source, **changes)))
    assert result.failure == "assessment_invalid_schema"
    assert result.missing == ()
    assert result.supported_sources == ()


def test_repair_never_authorizes_an_invented_quote():
    source = chunk()
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, missing="documents", support=[dict(source_id=1, quote="Everyone receives a waiver.")],
    )))
    assert not result.supported_sources


def test_all_six_missing_facts_survive():
    source = chunk()
    facts = [f"public fact {i}" for i in range(6)]
    result = assess_evidence(plan(), [source],
                             generate=MagicMock(return_value=proposal(source, missing=facts)))
    assert result.missing == tuple(facts)


def test_two_supported_quotes_from_same_source_survive():
    text = "Apply through the official portal. Provide a certified transcript."
    source = chunk(text)
    support = [dict(source_id=1, quote=q) for q in
               ("Apply through the official portal.", "Provide a certified transcript.")]
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, support=support, status="sufficient", missing=[],
    )))
    assert result.supported_quotes == tuple((1, item["quote"]) for item in support)


def test_checker_accepts_visible_markdown_quote_and_recovers_original_source_span():
    source = chunk(
        "**Eligibility Criteria**\n\n* Below 55 years of age\n* Savings in Account 2\n\n"
        "**Documents Required**\n\n* [Application form](https://agency.gov.my/form.pdf)\n"
        "* Identity document (non-MyKad holders only)"
    )
    support = [dict(source_id=1, quote=text) for text in (
        "Eligibility Criteria\n\n* Below 55 years of age\n* Savings in Account 2",
        "Documents Required\n\n* Application form\n* Identity document (non-MyKad holders only)",
    )]
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, status="sufficient", missing=[], support=support,
    )))
    assert result.status == "sufficient"
    assert len(result.supported_quotes) == 2
    for _, quote in result.supported_quotes:
        assert quote in source.content  # Authoritative quotes are recovered from the page.
    assert "https://agency.gov.my/form.pdf" in result.supported_quotes[1][1]
    assert "non-MyKad holders only" in result.supported_quotes[1][1]


@pytest.mark.parametrize("quote", [
    "Below 60 years of age",
    "Identity document (all holders)",
    "Documents Required\n\n* Application form\n* Proof of income",
    "Savings in Account 2 and all applicants qualify.",
])
def test_markdown_quote_matching_never_repairs_changed_facts(quote):
    source = chunk(
        "**Below 55 years of age**\n\nSavings in Account 2.\n\n"
        "**Documents Required**\n\n* [Application form](https://agency.gov.my/form.pdf)\n"
        "* Identity document (non-MyKad holders only)"
    )
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, support=[dict(source_id=1, quote=quote)],
    )))
    assert result.supported_quotes == ()
    assert result.supported_sources == ()


def test_quote_matching_cannot_delete_intervening_conditions_or_match_link_destination():
    from app.rag.evidence_text import match_evidence_quote
    source = (
        "**Apply only if eligible**; provide identification and enrolment proof.\n\n"
        "* [Application form](https://agency.gov.my/everyone-qualifies)\n"
        "* Proof of enrolment\n* Identification"
    )
    for quote in ("Apply; provide identification and enrolment proof.",
                  "Application form * Identification", "everyone-qualifies"):
        assert match_evidence_quote(quote, source) is None


def test_one_unmatched_quote_cannot_claim_complete_coverage():
    source = chunk("Apply through the official portal.")
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, status="sufficient", missing=[], support=[
            dict(source_id=1, quote=source.content),
            dict(source_id=1, quote="Every applicant is eligible."),
        ],
    )))
    assert result.status == "partial"
    assert result.supported_quotes == ((1, source.content),)
    assert result.missing == plan().required_facts


@pytest.mark.parametrize("host,expected", [
    ("https://generativelanguage.googleapis.com/v1beta/openai/", True),
    ("https://api.deepseek.com", False),
    ("https://generativelanguage.googleapis.com.fake.example/v1", False),
])
def test_schema_is_sent_only_to_documented_gemini_endpoint(host, expected):
    from app import llm
    provider = SimpleNamespace(base_url=host, api_key="test", model="gemini-3.8-flash",
                               role="primary")
    completion = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='{"status":"sufficient"}'))], usage=None)
    factory = MagicMock()
    factory.return_value.chat.completions.create.return_value = completion
    schema = {"type": "object", "properties": {"status": {"type": "string"}}}
    llm._generate_with_provider(factory, provider, "public prompt", reasoning_effort="low",
                                timeout_seconds=4, structured=True, response_schema=schema)
    sent = factory.return_value.chat.completions.create.call_args.kwargs
    assert ("response_format" in sent) is expected
    if expected:
        assert sent["response_format"]["json_schema"]["schema"] == schema
    assert factory.call_args.kwargs["max_retries"] == 0


def test_structured_failover_shares_one_call_timeout():
    from app import llm
    budget = MagicMock(provider_session=None)
    budget.remaining_seconds.return_value = 30
    budget.timeout_for.return_value = 30
    providers = [SimpleNamespace(role="primary"), SimpleNamespace(role="fallback")]
    with (patch.object(llm, "_providers", return_value=providers),
          patch.object(llm, "COACH_STRUCTURED_TIMEOUT_SECONDS", 8, create=True),
          patch.object(llm, "monotonic", side_effect=[0, 0, 3]),
          patch.object(llm, "_generate_with_provider", side_effect=[
              TimeoutError(), SimpleNamespace(content="{}"),
          ]) as generate):
        llm.generate_structured_result("public prompt", budget=budget)
    assert [call.kwargs["timeout_seconds"] for call in generate.call_args_list] == [5, 5]


def test_recovery_preserves_final_answer_reserve():
    from app import llm
    budget = MagicMock(provider_session=None)
    budget.remaining_seconds.return_value = 10
    with (patch.object(llm, "_providers", return_value=[SimpleNamespace(role="primary")]),
          patch.object(llm, "_generate_with_provider") as generate):
        with pytest.raises(TimeoutError):
            llm.generate_structured_result("public prompt", budget=budget)
    generate.assert_not_called()


def test_primary_timeout_leaves_fallback_three_seconds():
    from app import llm
    budget = MagicMock(provider_session=None)
    budget.remaining_seconds.return_value = 60
    budget.timeout_for.return_value = 60
    with (patch.object(llm, "_providers", return_value=[
              SimpleNamespace(role="primary"), SimpleNamespace(role="fallback")]),
          patch.object(llm, "COACH_STRUCTURED_TIMEOUT_SECONDS", 8),
          patch.object(llm, "monotonic", side_effect=[0, 0, 5]),
          patch.object(llm, "_generate_with_provider", side_effect=[
              TimeoutError(), SimpleNamespace(content="{}")]) as generate):
        llm.generate_structured_result("public prompt", budget=budget)
    assert [c.kwargs["timeout_seconds"] for c in generate.call_args_list] == [5, 3]


def test_checker_timeout_retries_once_before_searching_real_gap():
    source = chunk()
    good = EvidenceAssessment("sufficient", supported_sources=(1,),
                              supported_quotes=((1, source.content),))
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[
              EvidenceAssessment("insufficient", failure="assessment_timeout"), good, good]) as checker,
          patch("app.rag.research_policy.research_evidence",
                return_value=ResearchOutcome([source], True, "ok")) as search):
        result = run_research_policy(plan(), [source], generate=MagicMock(),
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True,
            max_results=4, timeout=4)
    assert checker.call_count == 3 and search.call_count == 1
    assert result.diagnostics["checker_retries"] == 1
    assert result.assessment.status == "sufficient"


def test_changed_gap_does_not_reextract_same_pages_repeatedly():
    source = chunk()
    def partial(gap):
        return EvidenceAssessment("partial", (gap,), supported_sources=(1,),
                                  supported_quotes=((1, source.content),))
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[
              EvidenceAssessment("insufficient", ("eligibility",)),
              partial("application documents"), partial("application deadline"),
              partial("income limits")]),
          patch("app.rag.research_policy.research_evidence",
                return_value=ResearchOutcome([source], True, "ok")) as search,
          patch("app.rag.research_policy.extract_passages", return_value={
              source.url: source.content + " Provide a transcript."}) as extract):
        result = run_research_policy(plan(), [], generate=MagicMock(),
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True,
            max_results=4, timeout=4)
    assert extract.call_count == 1 and search.call_count == 2
    assert "application deadline" in search.call_args.args[0]
    assert result.diagnostics["rounds"] == 3


def test_expired_primary_phase_skips_primary_without_starving_fallback():
    from app import llm
    budget = MagicMock(provider_session=None)
    budget.remaining_seconds.return_value = 18
    budget.timeout_for.side_effect = [TimeoutError("primary phase expired"), 18]
    with (patch.object(llm, "_providers", return_value=[
              SimpleNamespace(role="primary"), SimpleNamespace(role="fallback")]),
          patch.object(llm, "monotonic", side_effect=[0, 0, 0]),
          patch.object(llm, "_generate_with_provider", return_value=SimpleNamespace(content="{}")) as generate):
        llm.generate_structured_result("public prompt", budget=budget)
    assert generate.call_count == 1
    assert generate.call_args.args[1].role == "fallback"
    assert generate.call_args.kwargs["timeout_seconds"] == 8


@pytest.mark.parametrize("scope", ["period_matches", "jurisdiction_matches"])
@pytest.mark.parametrize("unsupported", [False, True])
def test_later_applicability_rejection_invalidates_previous_quotes(scope, unsupported):
    source = chunk()
    good = EvidenceAssessment("partial", ("application documents",), supported_sources=(1,),
                              supported_quotes=((1, source.content),))
    changes = {scope: False}
    if unsupported:
        changes.update(status="insufficient", support=[])
    rejected = assess_evidence(plan(), [source], generate=MagicMock(
        return_value=proposal(source, **changes)))
    assert rejected.applicability_rejected and not rejected.supported_quotes
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[
                  EvidenceAssessment("insufficient", ("eligibility",)), good, rejected, rejected, rejected]),
          patch("app.rag.research_policy.research_evidence",
                return_value=ResearchOutcome([source], True, "ok")),
          patch("app.rag.research_policy.extract_passages", return_value={
              source.url: source.content + " A newer requirement."})):
        result = run_research_policy(plan(), [], generate=MagicMock(),
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True,
            max_results=4, timeout=4)
    assert result.source_quotes == () and result.chunks == []


def test_public_search_uses_general_country_and_restricts_known_official_host():
    # Ruling retained from the controlled live comparison recorded in
    # docs/superpowers/plans/2026-10-06-coach-definition-progress.md: with an
    # identified official host, `country="malaysia"` displaced substantive
    # official pages with clipped news snippets, so the restricted public search
    # carries NO country boost. Open public discovery (no identified host) still
    # gets the Malaysian boost. The direct low-level call is covered by
    # test_research_definition_recovery.test_official_domain_search_does_not_also_apply_country_reranking.
    import sys
    from app.rag import web_research as web
    client = MagicMock()
    client.search.return_value = {"results": [], "usage": {"credits": 1}}
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        web.research_evidence("waiver documents", api_key="test", single_search=True,
                              public_policy=True, official_domains=("ptptn.gov.my",))
    args = client.search.call_args.kwargs
    assert args["topic"] == "general" and "country" not in args
    assert args["include_domains_mode"] == "restrict"
    assert args["include_domains"] == ["ptptn.gov.my"]
    assert args["search_depth"] == "basic"
    client.search.reset_mock()
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        web.research_evidence("waiver documents", api_key="test", single_search=True,
                              public_policy=True)
    open_discovery = client.search.call_args.kwargs
    assert open_discovery["topic"] == "general"
    assert open_discovery["country"] == "malaysia"
    assert "include_domains" not in open_discovery


def test_request_cache_reuses_calls_but_extract_query_is_part_of_key():
    import sys
    from app.rag import web_research as web
    cache = web.WebResearchCache()
    client = MagicMock()
    client.search.return_value = {"results": [dict(url=chunk().url, title="PTPTN", content="Application guidance", score=.8)],
                                  "usage": {"credits": 1}}
    client.extract.return_value = {"results": [dict(url=chunk().url, raw_content=chunk().content)],
                                   "usage": {"credits": 0}}
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        for _ in range(2):
            web.research_evidence("waiver", api_key="test", single_search=True,
                                  public_policy=True, cache=cache)
        web.extract_passages([chunk().url], api_key="test", query="documents", cache=cache)
    assert client.search.call_count == 1
    assert client.extract.call_count == 2
    assert cache.search_calls == 1 and cache.extract_calls == 2
    assert cache.credits == 1


def test_extract_skips_invalid_subsecond_timeout():
    import sys
    from app.rag import web_research as web
    client = MagicMock()
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        assert web.extract_passages([chunk().url], api_key="test", timeout=.5) == {}
    client.extract.assert_not_called()


def test_checker_retry_is_once_per_request_and_does_not_search_fake_gaps():
    failure = EvidenceAssessment("insufficient", failure="assessment_invalid_schema")
    with (patch("app.rag.research_policy.assess_evidence", return_value=failure) as checker,
          patch("app.rag.research_policy.research_evidence",
                return_value=ResearchOutcome([chunk()], True, "ok")) as search):
        result = run_research_policy(plan(), [chunk()], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assert checker.call_count == 3  # corpus + one retry + mandatory current web assessment
    assert search.call_count == 1
    assert result.assessment.missing == ()
    assert result.failure == "assessment_invalid_schema"


def test_known_page_gap_uses_focused_extract_before_new_search():
    source = chunk()
    partial = EvidenceAssessment("partial", ("application documents",), supported_sources=(1,),
                                 supported_quotes=((1, source.content),))
    sufficient = EvidenceAssessment("sufficient", supported_sources=(1,),
                                    supported_quotes=((1, source.content),))
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[
              EvidenceAssessment("insufficient", ("eligibility",)), partial, sufficient]),
          patch("app.rag.research_policy.research_evidence",
                return_value=ResearchOutcome([source], True, "ok")) as search,
          patch("app.rag.research_policy.extract_passages", return_value={
              source.url: "Provide a certified transcript.",
          }) as extract):
        result = run_research_policy(plan(), [], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assert search.call_count == 1 and extract.call_count == 1
    assert "application documents" in extract.call_args.kwargs["query"]
    assert result.assessment.status == "sufficient"


def test_unchanged_bounded_extraction_continues_to_gap_discovery():
    source = chunk("Existing instructions. " * 90)
    source = replace(source, content=source.content[:1800])
    discovered = chunk("Submit the form with a certified transcript.",
                       url="https://www.ptptn.gov.my/documents")
    partial = EvidenceAssessment("partial", ("application documents",), supported_sources=(1,),
                                 supported_quotes=((1, source.content),))
    sufficient = EvidenceAssessment("sufficient", supported_sources=(2,),
                                    supported_quotes=((2, discovered.content),))
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[
              # The longer unit adds incomplete metadata to unchanged bounded
              # text. Recheck that restriction, then discover the next page.
              EvidenceAssessment("insufficient", ("eligibility",)), partial, partial, sufficient]),
          patch("app.rag.research_policy.research_evidence", side_effect=[
              ResearchOutcome([source], True, "ok"), ResearchOutcome([discovered], True, "ok")
          ]) as search,
          patch("app.rag.research_policy.extract_passages", return_value={
              source.url: source.content + " Newly extracted text outside the retained window.",
          }) as extract):
        result = run_research_policy(plan(), [], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assert search.call_count == 2 and extract.call_count == 1
    assert result.assessment.status == "sufficient"
    assert result.diagnostics["rounds"] == 3
    assert discovered.url in [item.url for item in result.chunks]


def test_later_checker_failure_preserves_supported_snapshot():
    source = chunk()
    partial = EvidenceAssessment("partial", ("application documents",), supported_sources=(1,),
                                 supported_quotes=((1, source.content),))
    failure = EvidenceAssessment("insufficient", failure="assessment_invalid_schema")
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[
              EvidenceAssessment("insufficient", ("eligibility",)), partial, failure, failure]),
          patch("app.rag.research_policy.research_evidence",
                return_value=ResearchOutcome([source], True, "ok")),
          patch("app.rag.research_policy.extract_passages", return_value={
              source.url: "Provide a certified transcript.",
          })):
        result = run_research_policy(plan(), [], generate=MagicMock(),
                                     budget=CoachRequestBudget.start(), api_key="test",
                                     web_enabled=True, max_results=4, timeout=4)
    assert result.assessment.status == "partial"
    assert result.source_quotes == (source.content,)
    assert result.chunks[0].content == source.content
    assert result.failure == "assessment_invalid_schema"


def test_real_gap_recovery_caps_actual_paid_calls():
    import sys
    from app.rag import web_research as web
    client = MagicMock()
    call_count = 0

    def search(**kwargs):
        nonlocal call_count
        call_count += 1
        return {"results": [dict(url=f"https://thestar.com.my/page{call_count}",
            title="PTPTN application", content="Apply through the official application portal.", score=.8)],
            "usage": {"credits": 1}}

    client.search.side_effect = search
    client.extract.return_value = {"results": [], "failed_results": [], "usage": {"credits": 0}}
    checks = 0

    def model(prompt, **kwargs):
        nonlocal checks
        checks += 1
        excerpts = json.loads(prompt.rsplit("Evidence: ", 1)[1])
        return SimpleNamespace(content=json.dumps(dict(status="partial",
            missing=[f"public application detail {checks}"], conflicting=False,
            jurisdiction_matches=True, period_matches=True,
            support=[dict(source_id=excerpts[0]["id"], quote=excerpts[0]["text"])])))

    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        result = run_research_policy(plan(), [], generate=model, budget=CoachRequestBudget.start(),
                                     api_key="test", web_enabled=True, max_results=20, timeout=4)
    assert client.search.call_count == 3 and client.extract.call_count == 3
    assert result.diagnostics["search_calls"] == 3
    assert result.diagnostics["extract_calls"] == 3
    assert result.diagnostics["tavily_credits"] == 3
    assert result.assessment.status == "partial"
    assert result.failure == "research_round_limit"
    assert all(call.kwargs["max_results"] <= 4 for call in client.search.call_args_list)


def test_partial_reply_preserves_fact_and_describes_actual_gap():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=[chunk().content], plan=plan(),
                                      missing=("application documents",))
    assert chunk().content in answer
    assert "application documents" in answer
    assert "could not complete the source search" not in answer


def test_research_reply_omits_button_text_and_unfinished_document_introductions():
    from app.rag.service import _compose_research_answer
    first = ("The AKPK DM Portal is the main online platform for customers to apply for "
             "and manage their Debt Management Programme (DMP).\n"
             "Access the AKPK DM Portal to:\nApply")
    second = ("You can apply for the DMP through the AKPK DM Portal. "
              "Complete the application form as guided. What documents ... "
              "upload the following documents. For employed:")
    answer = _compose_research_answer(quotes=[first, second], missing=("required documents",))
    assert "apply for and manage their Debt Management Programme (DMP)." in answer
    assert "You can apply for the DMP through the AKPK DM Portal." in answer
    assert "Complete the application form as guided." in answer
    assert "\nApply" not in answer
    assert "Access the AKPK DM Portal to:" not in answer
    assert "What documents" not in answer
    assert "upload the following documents" not in answer
    assert "For employed:" not in answer
    assert "required documents" in answer
    assert "salary slip" not in answer  # Never invent the missing list.


def test_checker_keeps_complete_fact_but_not_dangling_list_or_button():
    source = chunk("Apply for the programme through the official portal.\n"
                   "Access the portal to:\nApply")
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(source)))
    assert result.supported_quotes == ((1, "Apply for the programme through the official portal."),)


def test_trimmed_support_cannot_claim_complete_coverage():
    source = chunk("Apply through the official portal.\nRequired documents:\nUpload")
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, status="sufficient", missing=[])))
    assert result.status == "partial"
    assert result.missing  # Recovery must fetch the missing context.


@pytest.mark.parametrize("text", [
    "Access the portal to:\nApply", "Upload the following documents. For employed:",
    "Applicants qualify provided that", "Applicants qualify if they have ...",
])
def test_checker_rejects_incomplete_instruction_as_support(text):
    source = chunk(text)
    result = assess_evidence(plan(), [source], generate=MagicMock(return_value=proposal(
        source, status="sufficient", missing=[])))
    assert not result.supported_quotes
    assert result.status == "insufficient"


def test_complete_document_list_and_qualification_are_preserved():
    from app.rag.service import _compose_research_answer
    quote = "For employed:\n• Latest salary slip\n• Identity document\n\nOnly eligible applicants may apply."
    answer = _compose_research_answer(quotes=[quote])
    assert "Latest salary slip" in answer and "Identity document" in answer
    assert "Only eligible applicants may apply." in answer


def test_dangling_qualification_never_broadens_a_complete_fact():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=["Applicants may apply. Only if:\nApproved"])
    assert "Applicants may apply." not in answer


def test_empty_conditions_list_never_turns_into_unconditional_eligibility():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=["Applicants may apply. The following conditions:\nEligible"])
    assert "Applicants may apply." not in answer


def test_full_context_extraction_preserves_document_list_after_navigation():
    import sys
    from app.rag import web_research as web
    client = MagicMock()
    navigation = ("Home | About | Login | Services\n\n" * 80)
    section = "## Required documents\n\nFor employed:\n• Identity document\n• Latest salary slip\n• Loan statements"
    client.extract.return_value = {"results": [dict(url=chunk().url, raw_content=navigation + section)]}
    cache = web.WebResearchCache()
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        passages = web.extract_passages([chunk().url], api_key="test", query="required documents",
                                        complete_context=True, cache=cache)
    assert "query" not in client.extract.call_args.kwargs  # Avoid 500-character snippet cutoffs.
    assert "chunks_per_source" not in client.extract.call_args.kwargs
    assert section in passages[chunk().url]
    assert len(passages[chunk().url]) <= 2000


def test_short_and_full_context_extraction_have_separate_cache_entries():
    import sys
    from app.rag import web_research as web
    client = MagicMock()
    client.extract.side_effect = [
        {"results": [dict(url=chunk().url, raw_content="For employed:")]},
        {"results": [dict(url=chunk().url, raw_content="For employed:\n• Identity document\n• Salary slip")]},
    ]
    cache = web.WebResearchCache()
    with patch.dict(sys.modules, {"tavily": SimpleNamespace(TavilyClient=lambda **_: client)}):
        short = web.extract_passages([chunk().url], api_key="test", query="documents", cache=cache)
        full = web.extract_passages([chunk().url], api_key="test", query="documents", cache=cache,
                                   complete_context=True)
        again = web.extract_passages([chunk().url], api_key="test", query="documents", cache=cache,
                                    complete_context=True)
    assert short != full and again == full
    assert client.extract.call_count == 2 and cache.cache_hits == 1


def test_agency_discovery_is_not_restricted_to_a_bank_that_mentions_the_agency():
    from dataclasses import replace
    agency = replace(plan(), entities=("AKPK",), topic="AKPK DMP application")
    bank = chunk("AKPK runs a debt management programme.",
                 url="https://www.alliancebank.com.my/financial-advice", title="AKPK guidance")
    own = chunk("AKPK application requires an identity document.",
                url="https://www.akpk.org.my/application", title="AKPK application")
    partial = EvidenceAssessment("partial", ("required application documents",),
                                 supported_sources=(1,), supported_quotes=((1, bank.content),))
    sufficient = EvidenceAssessment("sufficient", supported_sources=(1,), supported_quotes=((1, own.content),))
    with (patch("app.rag.research_policy.assess_evidence", side_effect=[partial, sufficient]),
          patch("app.rag.research_policy.research_evidence", return_value=ResearchOutcome([own], True, "ok")) as search):
        result = run_research_policy(agency, [bank], generate=MagicMock(),
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4, timeout=4)
    assert "www.alliancebank.com.my" not in search.call_args.kwargs["official_domains"]
    assert result.assessment.status == "sufficient"


def test_research_reply_formats_inline_conditions_as_separate_numbered_items():
    from app.rag.service import _compose_research_answer
    quote = "Repayment conditions : 1. Study full time; 2. Obtain First Class; 3. Apply within 12 months."
    answer = _compose_research_answer(quotes=[quote, "Apply through the official portal."],
                                      plan=plan(), missing=("application documents",))
    assert "**Repayment conditions**\n\n1. Study full time" in answer
    assert "\n2. Obtain First Class" in answer
    assert "\n3. Apply within 12 months." in answer
    assert "• Repayment conditions" not in answer
    assert "**Still to check**\n\n• application documents" in answer


def test_research_reply_preserves_existing_paragraphs_and_numbered_lists():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=[
        "Application steps:\n\n1. Register your account.\n2. Submit the form.\n\nKeep a copy."])
    assert "1. Register your account.\n2. Submit the form.\n\nKeep a copy." in answer


def test_research_reply_normalizes_source_markdown_without_exposing_heading_symbols():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=[
        "## **Eligibility** * **Positive disposable income.** * **Not bankrupt.**"])
    assert "##" not in answer
    assert "**Eligibility**\n\n• **Positive disposable income.**" in answer
    assert "\n• **Not bankrupt.**" in answer


def test_research_reply_keeps_decimal_amounts_dates_and_qualifications():
    from app.rag.service import _compose_research_answer
    quote = "The rate is 2.75%, the fee is RM12.50, effective 1 January 2026, for eligible borrowers only."
    assert quote in _compose_research_answer(quotes=[quote])


def test_research_reply_formats_heading_spliced_into_an_extracted_paragraph():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=[
        "Apply within 12 months. [...] ### Repayment conditions :\n\n1. First condition;\n2. Second condition."])
    assert "###" not in answer
    assert "Apply within 12 months.\n\n**Repayment conditions :**" in answer
    assert "[...]" not in answer
    assert "\n1. First condition;\n2. Second condition." in answer


def test_no_evidence_reply_gives_next_step_without_invented_policy():
    from app.rag.service import _compose_research_answer
    answer = _compose_research_answer(quotes=[], plan=plan(), failure="assessment_invalid_schema")
    assert "PTPTN" in answer and "official" in answer
    assert "could not complete the source search" not in answer
    assert "First Class" not in answer


def test_probe_repository_and_corpus_client_forbid_persistence_and_private_access():
    from scripts.research_recovery_probe import NoPersistenceRepository, PublicCorpusClient
    repo = NoPersistenceRepository()
    assert repo.list_messages("any-session") == []
    payload = {"content": "public answer"}
    assert repo.complete_turn(assistant_payload=payload) is payload
    actual = MagicMock()
    corpus = PublicCorpusClient(actual)
    corpus.rpc("match_knowledge_documents", {"match_count": 3})
    with pytest.raises(AssertionError):
        corpus.table("transactions")
    with pytest.raises(AssertionError):
        corpus.rpc("restore_financial_backup_v1", {})
    assert corpus.forbidden_attempts == 2
    actual.table.assert_not_called()
    assert actual.rpc.call_count == 1


def test_official_discovery_rejects_lookalike_even_with_claimed_tier():
    from app.rag.research_policy import _official_domains
    fake = chunk(url="https://ptptn.gov.my.evil.example/application")
    assert _official_domains(plan(), [fake]) == ()
    assert _official_domains(plan(), [chunk()]) == ("www.ptptn.gov.my",)


def test_capacity_preserves_verified_sources_instead_of_claiming_complete_coverage():
    from app.rag.research_policy import _balanced_evidence
    old = [chunk(f"Verified application requirement number {i}.",
                 url=f"https://ptptn.gov.my/old{i}") for i in range(6)]
    new = [chunk("New application guidance.", url="https://ptptn.gov.my/new")]
    merged = _balanced_evidence(old, new, preserved=tuple((c, (c.content,)) for c in old))
    assert len(merged) == 6
    assert {c.url for c in merged} == {c.url for c in old}


def test_service_provider_failure_keeps_source_snapshot_without_pasting_excerpt():
    from app.rag.research_policy import ResearchDecision
    from app.rag.service import CoachingService
    question = "What are the current application steps?"
    source = chunk()
    decision = ResearchDecision([source], EvidenceAssessment("partial", ("application documents",),
        supported_sources=(1,), supported_quotes=((1, source.content),)),
        web_used=True, source_quotes=(source.content,))
    repo = MagicMock(user_id="u")
    repo.require_session.return_value = {"id": "s", "title": "Existing"}
    repo.find_user_message.return_value = None
    repo.insert_user_message.return_value = {"id": "m", "content": question}
    repo.list_messages.return_value = []
    repo.complete_turn.side_effect = lambda **kwargs: kwargs["assistant_payload"]
    with (patch("app.rag.service.COACH_RESEARCH_POLICY_ENABLED", True),
          patch("app.rag.service.interpret_question", return_value=plan()),
          patch("app.rag.service.retrieve", return_value=[]),
          patch("app.rag.service.run_research_policy", return_value=decision),
          patch("app.rag.service.generate_result", side_effect=TimeoutError()),
          patch("app.rag.research_answer.generate_fallback_result", side_effect=TimeoutError())):
        reply = CoachingService(repo, MagicMock()).send_message("s", "m", question)
    assistant = reply["assistant_message"]
    assert source.content not in assistant["content"]
    assert assistant["content"] == "The explanation could not be completed this time. Please try again."
    assert assistant["ui_payload"]["source_snapshot"][0]["url"] == source.url
    assert assistant["model"] == "fincoach-research-explanation"
