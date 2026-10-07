"""Shared coverage, authority and link-recovery regressions for open questions."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.llm import CoachRequestBudget
from app.rag.research_policy import QuestionPlan, assess_evidence
from app.rag.retrieval import RetrievedChunk


def plan(**kwargs):
    return QuestionPlan("Example assistance", False, True, "current",
                        entities=("Example",), required_facts=("application", "documents"),
                        part_tracking=True, **kwargs)


def chunk(text, url="https://example.gov.my/guidance", tier=1):
    return RetrievedChunk(1, "Example guidance", "example", None, 0, text, .8,
                          source_type="web", url=url, tier=tier,
                          confidence="established" if tier in (1, 2) else "reported")


def assess(p, text, rows):
    payload = dict(status="sufficient", missing=[], conflicting=False,
                   jurisdiction_matches=True, period_matches=True,
                   support=[dict(source_id=1, quote=text)], coverage=rows)
    return assess_evidence(p, [chunk(text)],
                          generate=lambda *a, **k: SimpleNamespace(content=json.dumps(payload)),
                          budget=CoachRequestBudget.start())


def test_requested_parts_are_public_bounded_deduplicated_and_stable():
    from app.rag.research_coverage import requested_parts
    p = replace(plan(), required_facts=("Application", "application", "documents", *map(str, range(8))))
    parts = requested_parts(p)
    assert [x.id for x in parts] == ["p1", "p2", "p3", "p4", "p5", "p6"]
    assert parts[1].label == "documents"
    assert len(requested_parts(replace(p, required_facts=()))) == 1


def test_explicit_no_application_resolves_requested_application_part():
    text = "No separate application is required. Eligibility is assessed automatically."
    rows = [dict(part_id="p1", status="confirmed", support_indices=[1], resolution="not_required", complete=True),
            dict(part_id="p2", status="missing", support_indices=[], resolution="direct", complete=False)]
    result = assess(plan(), text, rows)
    assert result.status == "partial"
    assert result.parts[0].complete and result.parts[0].resolution == "not_required"
    assert result.missing == ("documents",)


def test_absent_details_do_not_prove_no_application_required():
    text = "The programme supports qualifying households with assistance."
    rows = [dict(part_id="p1", status="confirmed", support_indices=[99], resolution="not_required", complete=True)]
    result = assess(plan(), text, rows)
    assert result.status != "sufficient"
    assert not any(x.complete for x in result.parts)
    rows[0]["support_indices"] = [1]
    result = assess(plan(), text, rows)
    assert not result.parts[0].complete


def test_explicit_malay_no_application_resolves_application_part():
    text = "Tiada permohonan diperlukan. Kelayakan disemak secara automatik."
    rows = [dict(part_id="p1", status="confirmed", support_indices=[1],
                 resolution="not_required", complete=True)]
    result = assess(plan(), text, rows)
    assert result.parts[0].complete


@pytest.mark.parametrize('text', [
    "Check eligibility on the official portal or wait for notification letters and SMS messages.",
    "Check application status on the official portal.",
    "Semak status permohonan di portal rasmi.",
])
def test_status_check_is_not_complete_application_guidance(text):
    rows = [dict(part_id="p1", status="confirmed", support_indices=[1],
                 resolution="direct", complete=True)]
    result = assess(plan(), text, rows)
    assert not result.parts[0].complete


def test_nonautomatic_approval_does_not_prove_no_application_required():
    rows = [dict(part_id='p1', status='confirmed', support_indices=[1],
                 resolution='not_required', complete=True)]
    result = assess(plan(), 'Permohonan tidak diluluskan secara automatik.', rows)
    assert not result.parts[0].complete


@pytest.mark.parametrize('text', [
    'Applications must be made online through the official portal. Check eligibility there.',
    'Permohonan boleh dibuat secara dalam talian. Semak status di portal rasmi.',
])
def test_application_method_with_status_check_remains_complete(text):
    rows = [dict(part_id='p1', status='confirmed', support_indices=[1],
                 resolution='direct', complete=True)]
    assert assess(plan(), text, rows).parts[0].complete


def test_incomplete_or_missing_rows_cannot_authorize_complete_coverage():
    text = "Applications are submitted through the Example public portal."
    rows = [dict(part_id="p1", status="confirmed", support_indices=[1], resolution="direct", complete=True)]
    result = assess(plan(), text, rows)
    assert result.status == "partial" and result.missing == ("documents",)
    duplicate = assess(plan(), text, rows + rows)
    assert not any(x.complete for x in duplicate.parts)


def test_scheduler_visits_other_gaps_before_repeating():
    from app.rag.research_coverage import PartCoverage, select_unresolved_part
    parts = (PartCoverage("p1", "confirmed", complete=True), PartCoverage("p2", "missing"), PartCoverage("p3", "missing"))
    assert select_unresolved_part(parts, {}) == "p2"
    assert select_unresolved_part(parts, {"p2": 1}) == "p3"


def test_secondary_site_does_not_inherit_first_party_authority():
    from app.rag.research_policy import evidence_basis
    text = "Example programme applicants must provide their identity document in 2026."
    bank = chunk(text, "https://maybank.com/guidance", 2)
    assert evidence_basis(plan(), (1,), ((1, text),), [bank]) == "reported"
    assert evidence_basis(plan(), (1,), ((1, text),), [chunk(text)]) == "confirmed"


def test_reported_status_is_not_promoted_by_a_related_bank_entity():
    p = replace(plan(), topic="AKPK debt management programme", entities=("AKPK", "Maybank"), required_facts=("AKPK documents",))
    text = "AKPK applicants must provide an identity card in 2026, Maybank reports."
    payload = dict(status="sufficient", missing=[], conflicting=False, jurisdiction_matches=True, period_matches=True,
        support=[dict(source_id=1, quote=text)],
        coverage=[dict(part_id="p1", status="reported", support_indices=[1], resolution="direct", complete=True)])
    result = assess_evidence(p, [chunk(text, "https://maybank.com/akpk", 2)],
        generate=lambda *a, **k: SimpleNamespace(content=json.dumps(payload)), budget=CoachRequestBudget.start())
    assert result.parts[0].status == "reported" and not result.parts[0].complete


def test_same_full_article_with_different_quoted_sentences_is_one_origin():
    from app.rag.research_policy import _independent_reports
    a = "For 2026 applicants Example asks for their identity card."
    b = "Households enrolling in Example in 2026 should prepare the national identity document."
    full = a + "\n" + b
    assert not _independent_reports(plan(), (1, 2), ((1, a), (2, b)),
        [chunk(full, "https://thestar.com.my/example", 3), chunk(full, "https://nst.com.my/example", 3)])


@pytest.mark.parametrize("target", ["http://127.1/documents", "https://example.gov.my/documents?id=900101010001"])
def test_observed_links_reject_short_numeric_hosts_and_identifier_queries(target):
    from app.rag.web_research import linked_guidance_urls
    assert not linked_guidance_urls("https://example.gov.my/apply", f"[Example documents]({target})",
        subject_query="Example", part_label="documents", visited=frozenset())


@pytest.mark.parametrize("urls,texts,complete", [
    (("https://reuters.com/a", "https://bernama.com/b"),
     ("For 2026 Example applicants the identity card is the sole document required.",
      "The Example scheme in 2026 asks households to submit only their national identity card."), True),
    (("https://reuters.com/a", "https://bernama.com/b"),
     ("Example requires an identity card in 2026.", "Example requires an identity card in 2026."), False),
    (("https://reuters.com/a", "https://www.reuters.com/b"),
     ("Example requires an identity card in 2026.", "In 2026 applicants must show identity cards for Example."), False),
    (("https://reuters.com/a", "https://bernama.com/b"),
     ("Example requires an identity card.", "For Example applicants provide an identity card."), False),
])
def test_reported_requirements_need_distinct_applicable_origins(urls, texts, complete):
    p = replace(plan(), required_facts=("documents",))
    payload = dict(status="sufficient", missing=[], conflicting=False, jurisdiction_matches=True,
                   period_matches=True, support=[dict(source_id=i, quote=t) for i, t in enumerate(texts, 1)],
                   coverage=[dict(part_id="p1", status="reported", support_indices=[1, 2], resolution="direct", complete=True)])
    result = assess_evidence(p, [chunk(t, u, 3) for t, u in zip(texts, urls)],
        generate=lambda *a, **k: SimpleNamespace(content=json.dumps(payload)), budget=CoachRequestBudget.start())
    assert result.parts[0].status == "reported"
    assert result.parts[0].complete is complete


def test_tracked_comparison_does_not_remove_primary_source_gate():
    p = replace(plan(), topic="bank rates", entities=("Maybank", "CIMB"),
                original_question="Compare current Maybank and CIMB deposit rates", required_facts=("rates",))
    text = "Maybank offers 2% and CIMB offers 3% in 2026."
    result = assess(p, text, [dict(part_id="p1", status="confirmed", support_indices=[1], resolution="direct", complete=True)])
    assert result.status != "sufficient"


def test_broader_search_drops_domain_cage_and_has_distinct_cache_key():
    from unittest.mock import MagicMock
    from app.rag.web_research import WebResearchCache, _search_pass
    cache, client = WebResearchCache(), MagicMock()
    client.search.return_value = {"results": []}
    for mode in ("institution", "broader", "broader"):
        _search_pass(client, "Example documents", caged=True, max_results=4, timeout=3,
                     public_policy=True, official_domains=("example.gov.my",), cache=cache, discovery_mode=mode)
    assert client.search.call_count == 2 and cache.search_calls == 2
    assert "include_domains" in client.search.call_args_list[0].kwargs
    assert "include_domains" not in client.search.call_args_list[1].kwargs


def test_observed_links_are_ranked_and_unsafe_links_are_rejected():
    from app.rag.web_research import linked_guidance_urls
    markdown = """[Example required documents](/documents.pdf)
[Other scheme](/unrelated)
[Example documents](http://127.0.0.1/private)
[Example documents](https://example.gov.my/download?token=secret)
[Example documents](https://user:password@example.gov.my/private)
[Example eligibility](/eligibility)
"""
    urls = linked_guidance_urls("https://example.gov.my/apply", markdown,
                               subject_query="Example", part_label="required documents", visited=frozenset())
    assert urls == ("https://example.gov.my/documents.pdf",)


def test_policy_follows_observed_document_link_without_another_search():
    from unittest.mock import patch
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    from app.rag.web_research import ResearchOutcome
    app_text = "Applications are submitted through the Example public portal."
    doc_text = "Example applicants must provide their national identity card."
    source = chunk(app_text)
    calls = []
    def search(*a, **k):
        k["cache"].search_calls += 1
        k["cache"].full_pages[source.url] = app_text + "\n[Example required documents](/documents.pdf)"
        return ResearchOutcome([source], True, "ok")
    def extract(urls, **k):
        calls.append(urls)
        k["cache"].extract_calls += 1
        return {url: doc_text for url in urls if url.endswith("documents.pdf")}
    def check(_plan, sources, **k):
        if not sources:
            return policy.EvidenceAssessment("insufficient", ("application", "documents"))
        pairs = tuple((i, s.content) for i, s in enumerate(sources, 1))
        refs = {"p1": (), "p2": ()}
        for i, (_sid, text) in enumerate(pairs, 1):
            if text == app_text: refs["p1"] = (i,)
            if text == doc_text: refs["p2"] = (i,)
        parts = tuple(PartCoverage(key, "confirmed" if val else "missing", val, complete=bool(val)) for key, val in refs.items())
        missing = tuple(part.label for part in policy.requested_parts(_plan) if not refs[part.id])
        return policy.EvidenceAssessment("partial" if missing else "sufficient", missing,
             supported_sources=tuple(range(1, len(sources)+1)), supported_quotes=pairs, parts=parts)
    with patch.object(policy, "research_evidence", side_effect=search) as searches, \
         patch.object(policy, "extract_passages", side_effect=extract), \
         patch.object(policy, "assess_evidence", side_effect=check):
        result = policy.run_research_policy(plan(), [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4, timeout=8)
    assert result.assessment.status == "sufficient"
    assert searches.call_count == 1
    assert any("https://example.gov.my/documents.pdf" in urls for urls in calls)
    for part in result.assessment.parts:
        assert part.complete and part.support_indices
        text = result.assessment.supported_quotes[part.support_indices[0]-1][1]
        assert text == (app_text if part.part_id == "p1" else doc_text)


def test_policy_broadens_targeted_gaps_without_researching_answered_parts():
    from unittest.mock import patch
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    from app.rag.web_research import ResearchOutcome
    p = replace(plan(), required_facts=("application", "documents", "eligibility"))
    text = "Applications are submitted through the Example public portal."
    source = chunk(text)
    partial = policy.EvidenceAssessment("partial", ("documents", "eligibility"),
        supported_sources=(1,), supported_quotes=((1, text),),
        parts=(PartCoverage("p1", "confirmed", (1,), complete=True), PartCoverage("p2", "missing"), PartCoverage("p3", "missing")))
    def search(*a, **k):
        k["cache"].search_calls += 1
        return ResearchOutcome([source], True, "ok") if k["cache"].search_calls == 1 else ResearchOutcome([], True, "no_results")
    with patch.object(policy, "research_evidence", side_effect=search) as searches, \
         patch.object(policy, "extract_passages", return_value={}), \
         patch.object(policy, "assess_evidence", return_value=partial):
        result = policy.run_research_policy(p, [source], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4, timeout=8)
    later = searches.call_args_list[1:]
    assert later and all(not ("documents" in c.args[0] and "eligibility" in c.args[0]) for c in later)
    assert any(c.kwargs.get("discovery_mode") == "broader" for c in searches.call_args_list)
    # The bound is the request-local envelope, not the legacy three-round stop.
    # This plan has three requested parts, so the fair budget allows each missing
    # part one query plus one second variant, while still never re-searching the
    # part already confirmed. The old `<= 3` bound is exactly what left a third
    # requested part with no discovery attempt at all.
    assert result.assessment.supported_quotes
    assert result.diagnostics["search_calls"] <= 4


def test_verifier_shares_part_scope_and_rejects_unknown_answered_ids():
    from unittest.mock import patch
    from app.rag.grounding import GroundingClaim
    from app.rag.research_coverage import PartCoverage, requested_parts
    from app.rag.verifier import ResearchVerificationContext, verify_grounding_claims
    from app.llm import LLMResult
    context = ResearchVerificationContext("Explain application and documents", "Apply online", (),
        enforce_scope=True, requested_parts=requested_parts(plan()),
        coverage=(PartCoverage("p1", "confirmed", (1,), complete=True), PartCoverage("p2", "missing")))
    payload = dict(claims=[dict(id=1, verdict="supported", source_index=1)], quality_errors=[],
                   requested_scope_covered=True, unanswered_requested_parts=[], answered_part_ids=["p1", "p9"])
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    with patch("app.rag.verifier._create_verifier_client") as factory:
        factory.return_value.chat.completions.create.return_value = response
        result = verify_grounding_claims([GroundingClaim(1, "Apply online", (1,))], ["Apply online"],
                                        timeout_seconds=5, research_context=context)
    assert result.error_code == "verifier_invalid_json"
    assert "no separate application" in factory.return_value.chat.completions.create.call_args.kwargs["messages"][1]["content"].lower()


def test_verifier_does_not_mark_omitted_requested_part_complete():
    from unittest.mock import patch
    from app.rag.grounding import GroundingClaim
    from app.rag.research_coverage import PartCoverage, requested_parts
    from app.rag.verifier import ResearchVerificationContext, verify_grounding_claims
    from app.llm import LLMResult
    context = ResearchVerificationContext("Explain application and documents", "Apply online", (),
        enforce_scope=True, requested_parts=requested_parts(plan()),
        coverage=(PartCoverage("p1", "confirmed", (1,), complete=True), PartCoverage("p2", "missing")))
    payload = dict(claims=[dict(id=1, verdict="supported", source_index=1)], quality_errors=[],
                   requested_scope_covered=True, unanswered_requested_parts=[], answered_part_ids=["p1"])
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    with patch("app.rag.verifier._create_verifier_client") as factory:
        factory.return_value.chat.completions.create.return_value = response
        result = verify_grounding_claims([GroundingClaim(1, "Apply online", (1,))], ["Apply online"],
                                        timeout_seconds=5, research_context=context)
    assert result.error_code is None
    assert result.requested_scope_covered is False and result.unanswered_requested_parts == ("documents",)


def test_new_institutional_overview_without_coverage_progress_broadens_next_slot():
    from unittest.mock import patch
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    from app.rag.web_research import ResearchOutcome
    text = "Applications are submitted through the Example public portal."
    partial = policy.EvidenceAssessment("partial", ("documents",), supported_sources=(1,),
        supported_quotes=((1, text),), parts=(PartCoverage("p1", "confirmed", (1,), complete=True), PartCoverage("p2", "missing")))
    def search(*a, **k):
        k["cache"].search_calls += 1
        n = k["cache"].search_calls
        return ResearchOutcome([chunk(text + (" More context." if n > 1 else ""), f"https://example.gov.my/overview{n}")], True, "ok")
    with patch.object(policy, "research_evidence", side_effect=search) as searches, \
         patch.object(policy, "extract_passages", return_value={}), \
         patch.object(policy, "assess_evidence", return_value=partial):
        policy.run_research_policy(plan(), [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4, timeout=8)
    assert any(c.kwargs.get("discovery_mode") == "broader" for c in searches.call_args_list)


def test_probe_assessment_snapshot_serializes_nested_coverage():
    from scripts.research_recovery_probe import assessment_snapshot
    from app.rag.research_policy import EvidenceAssessment
    from app.rag.research_coverage import PartCoverage
    value = EvidenceAssessment("partial", ("documents",), parts=(PartCoverage("p1", "confirmed", (1,), complete=True),))
    restored = json.loads(json.dumps(assessment_snapshot(value)))
    assert restored["parts"][0]["complete"] is True and restored["missing"] == ["documents"]


def test_community_quotes_never_authorize_policy_requirements():
    text = "Applicants must provide their identity card in 2026."
    payload = dict(status="sufficient", missing=[], conflicting=False, jurisdiction_matches=True, period_matches=True,
        support=[dict(source_id=1, quote=text)],
        coverage=[dict(part_id="p1", status="reported", support_indices=[1], resolution="direct", complete=True)])
    p = replace(plan(), required_facts=("documents",))
    result = assess_evidence(p, [chunk(text, "https://reddit.com/thread", 5)],
        generate=lambda *a, **k: SimpleNamespace(content=json.dumps(payload)), budget=CoachRequestBudget.start())
    assert not result.supported_quotes


def test_focused_query_does_not_reintroduce_other_parts_or_all_admin_entities():
    from app.rag.research_policy import part_research_query
    from app.rag.research_coverage import requested_parts
    p = replace(plan(), topic="Sumbangan Tunai Rahmah application process and required documents",
        entities=("Lembaga Hasil Dalam Negeri", "Kementerian Kewangan"),
        required_facts=("Application process for Sumbangan Tunai Rahmah", "Required documents for married applicants"))
    query = part_research_query(p, requested_parts(p)[0])
    assert "documents" not in query.lower()
    assert "Kementerian" not in query and "Lembaga" not in query
    assert query.lower().count("sumbangan") == 1


def test_empty_evidence_still_reports_each_requested_part():
    from app.rag.research_policy import run_research_policy
    result = run_research_policy(plan(), [], generate=lambda *a, **k: None,
        budget=CoachRequestBudget.start(), api_key="", web_enabled=False, max_results=4, timeout=8)
    assert [p.part_id for p in result.assessment.parts] == ["p1", "p2"]
    assert all(not p.complete for p in result.assessment.parts)
    assert result.diagnostics["requested_part_labels"] == ["application", "documents"]


@pytest.mark.parametrize("subject", ["Example benefit", "Education withdrawal"])
def test_flattened_pdf_selects_late_required_document_section(subject):
    from app.rag.web_research import _complete_page_window
    raw = (subject + " 2026. Application guidance. " + "General introduction. " * 150
           + "7. Q: Which documents are required? A: Required documents: national identity card, "
           "enrolment letter and latest fee statement. Submit all copies with the application. "
           + "Other guidance. " * 160)
    selected = _complete_page_window(raw, f"{subject} required documents", subject_query=subject)
    assert "national identity card" in selected and "latest fee statement" in selected
    assert selected in raw and len(selected) <= 1800


def test_flattened_faq_prefers_general_document_question_over_special_case():
    from app.rag.web_research import _complete_page_window
    raw = ("Example assistance 2026. General guidance. " * 80
        + "7. S: Apakah dokumen yang perlu dikemukakan? J: Salinan dokumen sokongan "
          "termasuk kad pengenalan dan sijil pengajian, jika berkaitan. "
        + "Other guidance. " * 180
        + "19. S: Sijil saya telah hilang, apakah dokumen sokongan pengganti? "
          "J: Dokumen sokongan pengganti Example assistance termasuk surat pendaftaran. " * 8)
    result = _complete_page_window(raw, "Example assistance required documents", subject_query="Example assistance")
    assert "sijil pengajian, jika berkaitan" in result
    assert "Dokumen sokongan pengganti" not in result


def test_repeated_cached_window_cannot_use_all_remaining_recovery_rounds():
    from unittest.mock import patch
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    from app.rag.web_research import ResearchOutcome
    application = "Applications are submitted through the Example public portal."
    source = chunk(application)
    partial = policy.EvidenceAssessment("partial", ("documents",), supported_sources=(1,),
        supported_quotes=((1, application),), parts=(PartCoverage("p1", "confirmed", (1,), complete=True), PartCoverage("p2", "missing")))
    def search(*a, **k):
        k["cache"].search_calls += 1
        k["cache"].full_pages[source.url] = application + " More application guidance."
        return ResearchOutcome([source], True, "ok")
    with patch.object(policy, "research_evidence", side_effect=search) as searches, \
         patch.object(policy, "extract_passages", return_value={source.url: application + " More application guidance."}), \
         patch.object(policy, "assess_evidence", return_value=partial):
        result = policy.run_research_policy(plan(), [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4, timeout=8)
    assert searches.call_count >= 2
    assert result.diagnostics["search_calls"] <= 3 and result.diagnostics["assessment_calls"] <= 6


def test_unapproved_cached_sections_do_not_displace_remaining_searches():
    from unittest.mock import patch
    from app.rag import research_policy as policy
    from app.rag.research_coverage import PartCoverage
    from app.rag.web_research import ResearchOutcome
    source = chunk("Example updates are available through its public portal.")
    empty = policy.EvidenceAssessment("insufficient", ("application", "documents"),
        parts=(PartCoverage("p1", "missing"), PartCoverage("p2", "missing")))
    def search(*a, **k):
        k["cache"].search_calls += 1
        k["cache"].full_pages[source.url] = "Unrelated update instructions."
        return ResearchOutcome([source], True, "ok")
    def extract(*a, **k):
        return {source.url: "An unrelated section for " + k["query"] + "."}
    with patch.object(policy, "research_evidence", side_effect=search), \
         patch.object(policy, "extract_passages", side_effect=extract), \
         patch.object(policy, "assess_evidence", return_value=empty):
        result = policy.run_research_policy(plan(), [], generate=lambda *a, **k: None,
            budget=CoachRequestBudget.start(), api_key="test", web_enabled=True, max_results=4, timeout=8)
    assert result.diagnostics["search_calls"] == 3
    assert result.diagnostics["assessment_calls"] <= 6
    assert not result.assessment.supported_quotes
