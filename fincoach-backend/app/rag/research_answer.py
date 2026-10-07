"""Bounded explanation checking and recovery for approved public research.

Quotations are evidence, never a deterministic replacement for an explanation.
Legacy coaching validators remain unchanged; this path verifies meaning across
languages and checks complete document/application statements, not word overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import logging
import re
from time import monotonic
from typing import Literal

from app.llm import AgentLLMResult, CoachRequestBudget, LLMResult, generate_fallback_result
from app.config import LLM_FALLBACK_TIMEOUT_SECONDS
from app.rag.grounding import (
    DISCLAIMER, REQUIRED_HEADINGS, GroundingClaim, _numeric_values,
    contains_specific_product_recommendation,
)
from app.rag.research_policy import QuestionPlan, ResearchDecision
from app.rag.research_coverage import RequestedPart, clarification_question, clarification_part_ids
from app.rag.prompts import RESEARCH_EXPLANATION_SYSTEM_PROMPT, build_research_recovery_prompt
from app.rag.verifier import ResearchVerificationContext, verify_grounding_claims

_MARKER = re.compile(r"\[S(\d+)\]")
_HEADING = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)
_GAP_NOTE = re.compile(
    r"^(?:(?:the\s+)?(?:available\s+)?sources?\s+(?:do not|does not|did not|don'?t)\s+"
    r"(?:establish|confirm|specify|provide|explain)\b|"
    r"(?:I|we)\s+(?:haven'?t|have not|could not|couldn'?t|cannot|can'?t|have yet to)\s+"
    r"(?:confirm(?:ed)?|verify|verified|find|found|establish(?:ed)?)\b)", re.I,
)
logger = logging.getLogger("uvicorn.error")
UNAVAILABLE_MESSAGE = "The explanation could not be completed this time. Please try again."


@dataclass(frozen=True)
class ResearchDraftCheck:
    is_valid: bool
    error_codes: tuple[str, ...] = ()
    approved_text: str | None = None
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchAnswerOutcome:
    result: AgentLLMResult
    mode: Literal["research_explanation", "research_explanation_recovery", "research_explanation_unavailable"]
    recovery_used: bool
    error_codes: tuple[str, ...]
    diagnostics: dict = field(default_factory=dict)


def ambiguous_online_forms(quotes: list[str]) -> set[str]:
    """Do not move a conditional handover form into a different upload route.

    This narrow English/Malay guard detects competing objects, not ordinary
    pronoun paraphrases. Explicitly naming the form in an upload clause resolves
    the ambiguity. Other meanings still go through the semantic verifier.
    """
    code_pattern = r"\b[A-Z]{2,12}-?\d{1,4}[A-Z]?\b"
    normalize = lambda code: re.sub(r"[-\s]", "", code).casefold()
    ambiguous, explicit = set(), set()
    for quote in quotes:
        clauses = re.split(r"\b(?:or|atau)\b", quote, flags=re.I)
        for index, clause in enumerate(clauses):
            codes = {normalize(code) for code in re.findall(code_pattern, clause)}
            if re.search(r"\b(?:upload(?:s|ed|ing)?|(?:me)?muat\s+naik)\b", clause, re.I):
                explicit.update(normalize(code) for code in re.findall(code_pattern, clause, re.I))
            if (index + 1 < len(clauses) and codes
                    and re.search(r"\b(?:form|borang)\b", clause, re.I)
                    and re.search(r"\b(?:when|upon|semasa)\b", clause, re.I)
                    and re.search(r"\b(?:documents?|dokumen)\b", clause, re.I)
                    and re.search(r"\b(?:office|physically|pejabat)\b", clause, re.I)
                    and re.search(r"\b(?:upload(?:s|ed|ing)?|(?:me)?muat\s+naik)\b", clauses[index + 1], re.I)):
                ambiguous.update(codes)
    return ambiguous - explicit


def approved_references(decision: ResearchDecision) -> list[str]:
    """Positive evidence and constraining context are explicitly separated."""
    references = []
    for index, source in enumerate(decision.chunks, 1):
        quotes = [quote for source_id, quote in decision.assessment.supported_quotes
                  if source_id == index and " ".join(quote.split()) in " ".join(source.content.split())]
        uncertain_forms = ambiguous_online_forms(quotes)
        references.append(
            "APPROVED EVIDENCE (only this supports positive facts):\n" + "\n".join(quotes)
            + "\nQUALIFICATION CONTEXT (may constrain, never expand evidence):\n"
            + source.content[:1800]
            + ("\nQUALIFICATION: The handover-form condition is tied to physical delivery; "
               "the alternate upload clause does not name these forms: " + ", ".join(sorted(uncertain_forms))
               + ". Do not infer an online requirement for them. Explain the clear document-upload route instead."
               if uncertain_forms else "")
            + "\nSOURCE PROVENANCE: " + json.dumps({"title": source.title, "url": source.url,
                "tier": source.tier, "confidence": source.confidence, "published_date": source.published_date})
        )
    return references


def _body_units(draft: str) -> list[tuple[str, str, int]]:
    """Own citations by sentence; retain list/category context in one unit.

    Qualified lists share a block. Prose is checked as independent complete
    sentences, so one rejected assertion cannot erase other verified facts.
    """
    units = []
    section = ""
    block = 0
    # Normalize trailing markers before sentence splitting, not across sentences.
    text = re.sub(r"([.!?])\s+(\[S\d+\](?:\s*\[S\d+\])*)", r" \2\1", draft)
    # Markdown commonly separates a category introduction from its list with a
    # blank line. They remain one salvage block, with the category on every claim.
    text = re.sub(r"(:\n)\s*\n(?=(?:[-•▪]|\d+[.)])\s)", r"\1", text)
    for paragraph in re.split(r"\n\s*\n", text):
        lines = paragraph.strip().splitlines()
        body = []
        for line in lines:
            match = _HEADING.fullmatch(line.strip())
            if match:
                section = match.group(1)
            elif line.strip() and line.strip() != DISCLAIMER:
                body.append(line.strip())
        if not body:
            continue
        block += 1
        # Verify individual items, retaining a shared qualified salvage block.
        if any(line.endswith(":") or re.match(r"^(?:[-•▪]|\d+[.)])\s", line) for line in body):
            units.extend((section, line, block) for line in body)
        else:
            for line in body:
                for part in re.split(r"(?<=[.!?])\s+", line):
                    if part.strip():
                        block += 1
                        units.append((section, part.strip(), block))
    return units


def _with_citation(text: str, index: int) -> str:
    if text.endswith((".", "!", "?")):
        return f"{text[:-1]} [S{index}]{text[-1]}"
    return f"{text} [S{index}]"


def _render(units: list[tuple[str, str, int]]) -> str:
    return "\n\n".join(f"**{heading}**\n" + (
        DISCLAIMER if heading == "Educational guidance" else
        "\n".join(text for section, text, _ in units if section == heading)
    ) for heading in REQUIRED_HEADINGS if heading != "Recommended action"
        or any(section == heading for section, _, _ in units))


def _partial_notice(question: str) -> str:
    """Delivery coverage is distinct from whether source evidence is sufficient."""
    language = re.search(r"Response language:\s*([a-z]{2,3})", question)
    code = language.group(1) if language else "en"
    return {
        "ms": "Saya belum dapat menerangkan semua butiran yang diminta.",
        "zh": "部分问题尚未得到完整说明。",
        "ta": "கேட்ட அனைத்து விவரங்களையும் இன்னும் விளக்க முடியவில்லை.",
    }.get(code, "I could not explain all the requested details yet.")


def normalize_research_layout(text: str) -> str:
    """Repair presentation only; the unchanged explanation is still verified.

    Plain generated prose does not need a paid rewrite just to add application
    headings. Partial/duplicate section layouts stay invalid rather than
    silently moving facts between sections or dropping their qualifications.
    """
    text = text.strip()
    if not _MARKER.search(text):
        return text  # A free-form uncited draft needs normal grounded recovery.
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s*)?(Insight|Recommended action|Educational guidance)\s*:?\s*$',
                  lambda match: '**'+match.group(1)+'**', text)
    headings = tuple(_HEADING.findall(text))
    if not headings and text:
        body = text.removesuffix(DISCLAIMER).rstrip()
        return '**Insight**\n'+body+'\n\n**Educational guidance**\n'+DISCLAIMER
    if headings in (('Insight',), ('Insight', 'Recommended action')):
        return text+'\n\n**Educational guidance**\n'+DISCLAIMER
    return text


def check_research_draft(draft: str, *, public_question: str,
                         decision: ResearchDecision, budget: CoachRequestBudget,
                         max_words: int = 200) -> ResearchDraftCheck:
    """Strict structure/numbers followed by one semantic and quality batch."""
    text = draft.strip()
    # Models sometimes group citations as [S1, S2]. Canonicalize these before
    # checking source identities; the UI strips only the standard [S1] form.
    text = re.sub(r"\[S\d+(?:\s*,\s*S?\d+)+\]",
        lambda match: " ".join(f"[S{index}]" for index in re.findall(r"\d+", match.group())), text)
    errors = []
    headings = tuple(_HEADING.findall(text))
    if headings not in (REQUIRED_HEADINGS, ("Insight", "Educational guidance")) or not text.startswith("**Insight**"):
        errors.append("invalid_structure")
    educational = text.rsplit("**Educational guidance**", 1)[-1].strip()
    if educational != DISCLAIMER:
        errors.append("invalid_disclaimer")
    if contains_specific_product_recommendation(text):
        errors.append("product_recommendation")
    if len(_MARKER.sub("", _HEADING.sub("", text)).split()) > min(200, max_words):
        errors.append("answer_too_long")
    allowed = {i for i, quote in decision.assessment.supported_quotes
               if 1 <= i <= len(decision.chunks) and
               " ".join(quote.split()) in " ".join(decision.chunks[i - 1].content.split())}
    # A malformed marker is a citation proposal, not a fact. Treat it like a
    # missing citation and ask the same semantic batch to establish a real one.
    # An invented claim still fails; source numbering cannot authorize facts.
    citation_repairs = 0
    units = _body_units(text)
    claims = []
    claim_units = {}
    assessment_claim_ids = []
    numeric_rejections = set()
    channel_rejections = set()
    qualifications = {}
    for position, (_, sentence, _) in enumerate(units):
        block = units[position][2]
        if sentence.endswith(":"):
            qualifications[block] = sentence
            continue
        # A possible coverage note still gets a verdict in the SAME semantic
        # batch. Its assessment support must not become a fake source citation,
        # and the verifier must reject any financial fact hidden inside it.
        is_coverage = bool(_GAP_NOTE.match(_MARKER.sub("", sentence)))
        raw_indices = tuple(dict.fromkeys(int(i) for i in _MARKER.findall(sentence)))
        indices = tuple(i for i in raw_indices if i in allowed)
        if any(i not in allowed for i in raw_indices):
            citation_repairs += 1
            # Any invalid marker removes the sentence's citation authority: use
            # only the approved candidate pool and let the verifier pick support.
            indices = ()
        candidates = indices or tuple(sorted(allowed))
        if is_coverage:
            candidates = ()
        if not candidates and not is_coverage:
            errors.append("no_approved_evidence")
            continue
        positive = "\n".join(quote for source_id, quote in decision.assessment.supported_quotes
                             if source_id in candidates)
        if not _numeric_values(sentence).issubset(_numeric_values(positive)):
            # Reject this statement, while still checking independent useful
            # facts. A numeric mismatch cannot authorize the rest of a list.
            numeric_rejections.add(position)
        if re.search(r"\b(?:upload(?:s|ed|ing)?|(?:me)?muat\s+naik)\b", sentence, re.I):
            uncertain = ambiguous_online_forms([quote for source_id, quote in decision.assessment.supported_quotes
                                                if source_id in candidates])
            claim_codes = {re.sub(r"[-\s]", "", code).casefold()
                for code in re.findall(r"\b[A-Z]{2,12}[- ]?\d{1,4}[A-Z]?\b", sentence, re.I)}
            handover_reference = re.search(
                r"\b(?:(?:handover|(?:document\s+)?submission)\s+form|borang\s+serahan)\b", sentence, re.I)
            if uncertain & claim_codes or uncertain and handover_reference and not claim_codes:
                channel_rejections.add(position)
        claim_text = _MARKER.sub("", sentence).strip()
        if re.match(r"^(?:[-•▪]|\d+[.)])\s", sentence) and block in qualifications:
            claim_text = f"{qualifications[block]} {claim_text}"
        claim = GroundingClaim(len(claims) + 1, claim_text, candidates,
                               requires_citation=not bool(indices))
        claims.append(claim)
        claim_units[claim.id] = position
        # Every statement is eligible for semantic *type* checking. Even a
        # "sufficient" assessment can have missed a genuine coverage gap.
        # Financial facts still need a real source; only pure metadata may get
        # the verifier's explicit assessment-supported verdict.
        assessment_claim_ids.append(claim.id)
    if not claims or all(not c.cited_indices for c in claims):
        errors.append("no_claims")
    if len(claims) > 20:
        errors.append("too_many_claims")
    if errors:
        return ResearchDraftCheck(False, tuple(dict.fromkeys(errors)), diagnostics={
            "candidate_claim_count": len(claims), "approved_claim_count": 0})
    try:
        verification = verify_grounding_claims(
            claims, approved_references(decision), timeout_seconds=budget.timeout_for("verifier"),
            max_tokens=1500,
            research_context=ResearchVerificationContext(public_question, text, decision.assessment.missing,
                                                        decision.assessment.conflicting,
                                                        tuple(assessment_claim_ids), enforce_scope=True,
                                                        requested_parts=tuple(RequestedPart(p.part_id, label)
                                                            for p, label in zip(decision.assessment.parts,
                                                                decision.diagnostics.get("requested_part_labels", ()))),
                                                        coverage=decision.assessment.parts),
        )
    except Exception:
        return ResearchDraftCheck(False, ("verifier_unavailable",))
    diagnostics = {"candidate_claim_count": len(claims), "approved_claim_count": 0,
                   "citation_repairs": citation_repairs,
                   "numeric_rejected_claim_count": len(numeric_rejections),
                   "channel_rejected_claim_count": len(channel_rejections),
                   "model": verification.model, "prompt_tokens": verification.prompt_tokens,
                   "completion_tokens": verification.completion_tokens,
                   "elapsed_ms": verification.elapsed_ms}
    diagnostics.update(requested_scope_covered=verification.requested_scope_covered,
                       unanswered_requested_parts=list(verification.unanswered_requested_parts),
                       answered_part_ids=list(verification.answered_part_ids))
    if verification.error_code:
        return ResearchDraftCheck(False, (verification.error_code,), diagnostics=diagnostics)
    # Defend the coordinator boundary too, including fakes/custom verifier clients.
    if (set(verification.verdicts) != set(claim_units) or any(
        verdict not in {"supported", "unsupported", "contradicted"}
        for verdict in verification.verdicts.values()
    )):
        return ResearchDraftCheck(False, ("invalid_verifier_response",), diagnostics=diagnostics)
    # A scope error can accompany explicit claim-level rejections. Preserve
    # only independently approved blocks below; a global language/reference
    # error, or a scope error without identified rejected claims, still fails.
    scoped_rejections = (set(verification.quality_errors) == {'incomplete_supported_answer'}
        and any(verdict != 'supported' for verdict in verification.verdicts.values()))
    if verification.quality_errors and not scoped_rejections:
        return ResearchDraftCheck(False, verification.quality_errors, diagnostics=diagnostics)
    if not verification.source_indices:
        return ResearchDraftCheck(False, ("no_supported_facts",), diagnostics=diagnostics)
    rejected_blocks = set()
    for claim in claims:
        position = claim_units[claim.id]
        section, sentence, block = units[position]
        if position in numeric_rejections or position in channel_rejections:
            rejected_blocks.add(block)
            continue
        if claim.id in verification.assessment_supported_ids:
            if (verification.verdicts[claim.id] != "supported"
                    or claim.id not in assessment_claim_ids
                    or claim.id in verification.source_indices):
                rejected_blocks.add(block)
            else:
                units[position] = (section, _MARKER.sub("", sentence).strip(), block)
            continue
        index = verification.source_indices.get(claim.id)
        supporting = verification.supporting_sources.get(claim.id, (index,))
        if (verification.verdicts[claim.id] != "supported" or index not in claim.cited_indices
                or not supporting or any(i not in claim.cited_indices for i in supporting)):
            rejected_blocks.add(block)
            continue
        # Only source identities established by the verdict survive in the body
        # and cards; remove candidate markers that did not support this claim.
        cited = " ".join(f"[S{i}]" for i in supporting)
        clean = _MARKER.sub("", sentence).strip()
        if clean.endswith((".", "!", "?")):
            clean = f"{clean[:-1].rstrip()} {cited}{clean[-1]}"
        else:
            clean = f"{clean} {cited}"
        units[position] = (section, clean, block)
    diagnostics["coverage_note_count"] = len(verification.assessment_supported_ids)
    if rejected_blocks:
        # The semantic coverage verdict described the original draft. Removing
        # a requested fact makes it unsafe to claim full displayed coverage.
        diagnostics["requested_scope_covered"] = False
        diagnostics["answered_part_ids"] = []
        diagnostics["unanswered_requested_parts"] = list(dict.fromkeys((
            *verification.unanswered_requested_parts, "requested details removed during verification")))[:6]
        approved = [unit for unit in units if unit[2] not in rejected_blocks]
        # Never ship a fragments-only salvage; retain at least one independently
        # supported substantive block. Otherwise the one rewrite is the remedy.
        usable = any(unit[2] not in rejected_blocks and claim.cited_indices
                     and verification.verdicts.get(claim.id) == "supported"
                     for claim in claims for unit in (units[claim_units[claim.id]],))
        if usable:
            # A retained instruction is also a substantive explanation. If its
            # intro was rejected, present the complete instruction in Insight.
            if not any(section == "Insight" for section, _, _ in approved):
                approved = [("Insight" if section == "Recommended action" else section, sentence, block)
                            for section, sentence, block in approved]
            approved.append(("Insight", _partial_notice(public_question), -1))
            if len(_MARKER.sub("", _HEADING.sub("", _render(approved))).split()) > min(200, max_words):
                usable = False
        diagnostics["approved_claim_count"] = sum(
            units[position][2] not in rejected_blocks for position in claim_units.values()) if usable else 0
        code = ("ambiguous_submission_channel" if channel_rejections else
                "unsupported_number" if numeric_rejections else "unsupported_claim")
        return ResearchDraftCheck(False, (code,), _render(approved) if usable else None,
                                  diagnostics=diagnostics)
    diagnostics["approved_claim_count"] = len(claims)
    if verification.requested_scope_covered is False:
        # Retain verified statements for the one grounded rewrite. Coverage is
        # independent of factual entailment; a useful partial need not disappear.
        if not verification.assessment_supported_ids:
            units.append(("Insight", _partial_notice(public_question), -1))
        if len(_MARKER.sub("", _HEADING.sub("", _render(units))).split()) > min(200, max_words):
            return ResearchDraftCheck(False, ("answer_too_long",), diagnostics=diagnostics)
        # An already honest, verified partial cannot gain missing source facts
        # from a writer retry. Rewrite only a draft that concealed its coverage
        # gap (or the existing quality gate detected omitted supported details).
        honest_partial = bool(verification.assessment_supported_ids)
        return ResearchDraftCheck(honest_partial, () if honest_partial else ("requested_scope_incomplete",),
                                  _render(units), diagnostics)
    return ResearchDraftCheck(True, approved_text=_render(units), diagnostics=diagnostics)


def recover_research_answer(*, plan: QuestionPlan, decision: ResearchDecision,
                            draft: LLMResult | None, budget: CoachRequestBudget,
                            public_question: str, personal_facts: str = "",
                            initial_failure: str | None = None) -> ResearchAnswerOutcome:
    """One normal check, at most one explanation rewrite, then one final check.

    Public generation never receives private tool records. The service can attach
    those records independently; the already verified facts are woven in here
    deterministically, after public verification.
    """
    tokens = []
    checks = []
    initial_candidate = None
    initial_check = None
    used = False
    errors = (initial_failure,) if initial_failure else ()
    cause_codes = errors
    question_reserve = len((clarification_question(plan) or "").split()) if clarification_part_ids(plan) else 0
    max_words = 200 - question_reserve
    def record(result):
        tokens.append({"model": result.model, "prompt_tokens": result.prompt_tokens,
                       "completion_tokens": result.completion_tokens})
    if draft is not None:
        record(draft)

    def finish(result, mode, content, *, complete=False):
        clarification = clarification_question(plan) if clarification_part_ids(plan) else None
        if clarification:
            # This is a validated intent question, not a cited financial fact.
            # Insert it after verification; it cannot grant factual coverage.
            if "**Educational guidance**" in content:
                content = content.replace("**Educational guidance**",
                    clarification + "\n\n**Educational guidance**", 1)
            else:
                content = content + "\n\n" + clarification
            complete = False
        used_indices = sorted({int(i) for i in _MARKER.findall(content)})
        if personal_facts:
            content = f"{personal_facts}\n\n{content}"
        wrapped = AgentLLMResult(content, result.model, result.prompt_tokens, result.completion_tokens)
        diagnostics = {"recovery_used": used, "error_codes": list(errors),
                       "cause_codes": list(cause_codes or errors), "verification": checks,
                       "generation_tokens": tokens, "displayed_model": result.model,
                       "complete": complete, "used_source_indices": used_indices,
                       "clarification_part_ids": list(clarification_part_ids(plan))}
        displayed_check = initial_check if initial_candidate and result is draft else checks[-1] if checks else {}
        diagnostics.update(requested_scope_covered=displayed_check.get("requested_scope_covered"),
            answered_part_ids=displayed_check.get("answered_part_ids", []),
            unanswered_requested_parts=displayed_check.get("unanswered_requested_parts", []),
            terminal_reason=(decision.failure or "no_approved_evidence") if not decision.assessment.supported_quotes
                            else errors[0] if mode == "research_explanation_unavailable" and errors else None)
        if clarification:
            diagnostics["requested_scope_covered"] = False
            diagnostics["answered_part_ids"] = [part for part in diagnostics["answered_part_ids"]
                                                 if part not in clarification_part_ids(plan)]
        # Codes and counts only: production logs never contain source/draft text
        # or user records. Costs remain associated with the real generation.
        logger.info(json.dumps({"event": "coach_answer_recovery", "stage": mode,
            "cause_codes": list(cause_codes or errors), "recovery_count": int(used),
            "error_codes": list(errors),
            "candidate_sources": len(decision.chunks), "model": result.model,
            "candidate_claim_count": displayed_check.get("candidate_claim_count", 0),
            "approved_claim_count": displayed_check.get("approved_claim_count", 0),
            "requested_scope_covered": diagnostics["requested_scope_covered"],
            "terminal_reason": diagnostics["terminal_reason"],
            "role": "retained_draft" if initial_candidate and result is draft else
                    "fallback" if used and mode != "research_explanation_unavailable" else
                    "draft" if mode == "research_explanation" else "policy",
            "elapsed_ms": round((monotonic() - budget.started_at) * 1000, 1),
            "remaining_seconds": round(budget.remaining_seconds(), 2)}))
        return ResearchAnswerOutcome(wrapped, mode, used, errors, diagnostics)

    # No approved source facts means there is nothing to synthesize. Available
    # cards/assessment gaps remain in provenance; quotations never become body.
    if not decision.assessment.supported_quotes:
        errors = ("no_approved_evidence",)
        # Distinguish a source failure from a writer failure. The quotations are
        # still never copied into the body or replaced with unsupported memory.
        language = plan.response_language or "en"
        source_message = {
            "ms": "Saya tidak dapat mendapatkan maklumat sumber yang diperlukan kali ini. Sila cuba lagi.",
            "zh": "这次未能获取所需的来源信息，请重试。",
            "ta": "தேவையான ஆதாரத் தகவலை இம்முறை பெற முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
        }.get(language, "I could not retrieve the source details needed for this question. Please try again.")
        if plan.clarification_facts:
            # A concrete clarification can move the conversation forward even
            # when the independently requested source facts are unavailable.
            source_message = {
                "ms": "Saya belum dapat memastikan maklumat bagi bahagian lain soalan anda.",
                "zh": "我暂时还未确认你所问的其他细节。",
                "ta": "உங்கள் கேள்வியின் மற்ற விவரங்களை இன்னும் உறுதிப்படுத்தவில்லை.",
            }.get(language, "I haven't established the other requested details yet.")
        return finish(AgentLLMResult("", "fincoach-research-explanation"),
                      "research_explanation_unavailable", source_message)
    if draft is not None and budget.remaining_seconds() > 0:
        checked = check_research_draft(normalize_research_layout(draft.content), public_question=public_question,
            max_words=max_words,
            decision=decision, budget=budget.for_stage(max_seconds=5, reserve_after_seconds=(
                10 if budget.remaining_seconds() >= 15 else 0)))
        checks.append(checked.diagnostics)
        if checked.is_valid:
            return finish(draft, "research_explanation", checked.approved_text,
                          complete=not checked.diagnostics.get("coverage_note_count"))
        if checked.approved_text:
            initial_candidate = checked.approved_text
            initial_check = checked.diagnostics
        errors = checked.error_codes
        cause_codes = errors
    if initial_failure not in {"provider_auth_error", "provider_configuration_error"} and budget.remaining_seconds() > 0:
        used = True
        try:
            recovered = generate_fallback_result(
                build_research_recovery_prompt(public_question, decision, errors),
                # Spend the remaining shared allowance up to the configured
                # provider cap, retaining time for the final semantic check.
                budget=budget.for_stage(stage_name="answer_recovery", max_seconds=LLM_FALLBACK_TIMEOUT_SECONDS,
                    reserve_after_seconds=min(5, budget.remaining_seconds() / 2)),
                system_prompt=RESEARCH_EXPLANATION_SYSTEM_PROMPT,
            )
            record(recovered)
            checked = check_research_draft(normalize_research_layout(recovered.content), public_question=public_question,
                max_words=max_words,
                decision=decision, budget=budget.for_stage(max_seconds=5))
            checks.append(checked.diagnostics)
            if checked.is_valid or checked.approved_text:
                errors = checked.error_codes
                return finish(recovered, "research_explanation_recovery", checked.approved_text,
                              complete=checked.is_valid and not checked.diagnostics.get("coverage_note_count"))
            errors = checked.error_codes
        except Exception:
            errors = ("recovery_generation_unavailable",)
    if initial_candidate:
        return finish(draft, "research_explanation_recovery", initial_candidate)
    return finish(AgentLLMResult("", "fincoach-research-explanation"),
                  "research_explanation_unavailable", UNAVAILABLE_MESSAGE)
