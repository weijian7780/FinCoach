"""Bounded explanation checking and recovery for approved public research.

Quotations are evidence, never a deterministic replacement for an explanation.
Legacy coaching validators remain unchanged; this path verifies meaning across
languages and checks complete document/application statements, not word overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from time import monotonic
from typing import Literal

from app.config import (COACH_PRODUCT_RECHECK_SECONDS, COACH_RESEARCH_MAX_WORDS,
                        COACH_RESEARCH_VERIFIER_MAX_SECONDS)
from app.llm import (
    AgentLLMResult, CoachRequestBudget, LLMResult,
)
from app.rag.grounding import (
    DISCLAIMER, REQUIRED_HEADINGS, GroundingClaim, _CURRENCY_AMOUNT, _numeric_values,
    contains_specific_product_recommendation,
)
from app.rag.evidence_text import allowed_generated_ending, complete_evidence_passages
from app.rag.research_policy import QuestionPlan, ResearchDecision, SEARCH_FAILURE_REASONS
from app.rag.research_coverage import (
    RequestedPart, clarification_question, clarification_part_ids, non_finance_part_ids,
)
from app.rag.prompts import RESEARCH_EXPLANATION_SYSTEM_PROMPT, build_research_recovery_prompt
from app.rag.verifier import (ResearchVerificationContext, verify_grounding_claims,
                              product_recommendation_matches_draft, recheck_product_policy)
from app.rag.research_checker_deadline import within_writer_deadline
from app.rag.research_answer_budget import (
    research_work_budget, correction_writer_budget,
)

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
# Content words that carry no topic meaning; part relevance must not hinge on them.
_STOPWORDS = frozenset(
    "what which does with that this these those your their from into about only also "
    "including include full name identity purpose used please give simple example shows "
    "and the for are how can you explain asked requested part parts need needs".split()
)


def _content_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.casefold())
            if len(word) > 3 and word not in _STOPWORDS}


def _claim_part_ids(claim_text: str, parts: tuple) -> tuple[str, ...]:
    """Which requested parts a claim's own wording addresses.

    Deterministic keyword membership, supplied to the verifier so it can reject
    advice that is unrelated to the whole request even when a source states it.
    A paraphrase or translation may not share a word, so an empty result is not a
    local rejection: the semantic checker still decides relevance.
    """
    words = _content_words(claim_text)
    return tuple(part.id for part in parts if words & _content_words(part.label))


def _generate_research_correction(prompt: str, *, budget: CoachRequestBudget,
                                  system_prompt: str) -> LLMResult:
    """Use the normal writer's provider selection within the correction budget.

    A checker rejection does not mean the primary provider failed. Reuse the
    existing primary/fallback path rather than require a working fallback for
    every correction. The caller still permits only one bounded rewrite.
    """
    from app.llm import generate_result
    return generate_result(prompt, budget=budget, system_prompt=system_prompt)


def approved_evidence(decision: ResearchDecision) -> tuple[tuple[int, str], ...]:
    """Literal approved quotations, reconstructed only from approved sources.

    A caller may hand over a decision whose sources were approved without the
    literal quotation list being carried (a corpus-only definition). The
    quotation must still appear verbatim in its approved source, so a
    reconstruction cannot authorize a claim the source does not state.
    """
    if decision.assessment.supported_quotes:
        return decision.assessment.supported_quotes
    approved: list[tuple[int, str]] = []
    for index in decision.assessment.supported_sources:
        if not 0 < index <= len(decision.chunks):
            continue
        content = " ".join(decision.chunks[index - 1].content.split())
        for quote in decision.source_quotes:
            normalized = " ".join(quote.split())
            if normalized and normalized in content:
                approved.append((index, quote))
    return tuple(dict.fromkeys(approved))


def with_approved_evidence(decision: ResearchDecision) -> ResearchDecision:
    evidence = approved_evidence(decision)
    if evidence == decision.assessment.supported_quotes:
        return decision
    return replace(decision, assessment=replace(decision.assessment, supported_quotes=evidence))


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


def _name_inline_sources(sentence: str, chunks) -> str:
    """Resolve source names by marker position, without language/phrase lists.

    A marker followed by continuing prose (including a comma) occupies an inline
    slot. End-of-sentence citation clusters remain markers. Keep the marker beside
    the name until verification, so attribution never grants citation authority.
    """
    def name(match):
        suffix = _MARKER.sub("", sentence[match.end():]).lstrip()
        prefix = _MARKER.sub("", sentence[:match.start()]).rstrip()
        if (not suffix or suffix[0] in ".!?。！？"
                or prefix and prefix[-1] in ".!?。！？"):
            return match.group()
        index = int(match.group(1))
        if not 1 <= index <= len(chunks):
            raise ValueError("Inline attribution has no source")
        source = chunks[index - 1]
        title = " ".join((source.title or source.source or "").split())
        # Metadata is display text, never additional Markdown or marker syntax.
        title = re.sub(r"[\[\]*`#<>]", "", title).strip()
        if not title:
            raise ValueError("Inline attribution has no source name")
        return title + match.group()
    return _MARKER.sub(name, sentence)


def research_verifier_max_tokens(claim_count: int) -> int:
    """Room for per-claim entailment plus coverage/product-policy fields."""
    return min(6000, max(2000, 1000 + 120 * claim_count))


def research_claim_limit() -> int:
    """Preserve 20 at the legacy word limit; allow 30 at 500 words."""
    return 20 + max(0, (COACH_RESEARCH_MAX_WORDS - 200) // 30)


def _render(units: list[tuple[str, str, int]]) -> str:
    return "\n\n".join(f"**{heading}**\n" + (
        DISCLAIMER if heading == "Educational guidance" else
        "\n".join(text for section, text, _ in units if section == heading)
    ) for heading in REQUIRED_HEADINGS if heading != "Recommended action"
        or any(section == heading for section, _, _ in units))


_NAMED_PARTIAL_NOTICES = {
    "en": "I couldn't fully confirm and explain: {parts}.",
    "ms": "Saya belum dapat mengesahkan dan menerangkan sepenuhnya: {parts}.",
    "zh": "以下部分尚未能完整确认和说明：{parts}。",
    "ta": "இவற்றை இன்னும் முழுமையாக உறுதிப்படுத்தி விளக்க முடியவில்லை: {parts}.",
}


_DETAIL_LEFT_OUT = {
    "en": "I could not verify every requested detail.",
    "ms": "Saya belum dapat mengesahkan semua butiran yang diminta.",
    "zh": "我尚未核实所有所需细节。",
    "ta": "கோரப்பட்ட எல்லா விவரங்களையும் என்னால் உறுதிப்படுத்த முடியவில்லை.",
}


def _partial_notice(question: str, missing: tuple[str, ...] = (), resolved_question: str = "", part_count: int = 1) -> str:
    """Delivery coverage is distinct from whether source evidence is sufficient.

    ``missing`` names the unanswered requested parts (the plan's own labels);
    without them the general sentence is used.
    """
    language = re.search(r"Response language:\s*([a-z]{2,3})", question)
    code = language.group(1) if language else "en"
    names = tuple(dict.fromkeys(label.strip() for label in missing if label and label.strip()))
    if names:
        if part_count > 1 and len(names) < part_count:
            template = _NAMED_PARTIAL_NOTICES.get(code, _NAMED_PARTIAL_NOTICES["en"])
            return template.format(parts="; ".join(f"“{name}”" for name in names))
        return _DETAIL_LEFT_OUT.get(code, _DETAIL_LEFT_OUT["en"])
    return {
        "ms": "Saya belum dapat menerangkan semua butiran yang diminta.",
        "zh": "部分问题尚未得到完整说明。",
        "ta": "கேட்ட அனைத்து விவரங்களையும் இன்னும் விளக்க முடியவில்லை.",
    }.get(code, "I could not explain all the requested details yet.")


def _missing_labels(verification, requested) -> tuple[str, ...]:
    """Unanswered requested parts, named only by the plan's own part labels."""
    by_id = {part.id: part.label for part in requested if part.label and part.label != part.id}
    labels = set(by_id.values())
    missing = tuple(dict.fromkeys(by_id.get(value, value) for value in
                    getattr(verification, "unanswered_requested_parts", ()) or ()
                    if value in labels or value in by_id))
    if missing:
        return missing
    # A verifier may report incomplete coverage without repeating the labels.
    # Use the planned labels for parts it did not mark answered.
    answered = set(getattr(verification, "answered_part_ids", ()) or ())
    return tuple(label for part_id, label in by_id.items() if part_id not in answered)


def normalize_research_layout(text: str) -> str:
    """Repair presentation only; the unchanged explanation is still verified.

    Plain generated prose does not need a paid rewrite just to add application
    headings. Partial/duplicate section layouts stay invalid rather than
    silently moving facts between sections or dropping their qualifications.
    """
    text = text.strip()
    cited = bool(_MARKER.search(text))
    text = re.sub(r'(?m)^[ \t]*\*\*(Insight|Recommended action|Educational guidance)[ \t]*:[ \t]*\*\*[ \t]*$'
                  r'|^[ \t]*\*\*(Insight|Recommended action|Educational guidance)\*\*[ \t]*:[ \t]*$',
                  lambda match: '**'+(match.group(1) or match.group(2))+'**', text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s*)?(Insight|Recommended action|Educational guidance)\s*:?\s*$',
                  lambda match: '**'+match.group(1)+'**', text)
    # Fixed presentation text; preserve subsequent/duplicate headings for validation.
    matches = list(_HEADING.finditer(text))
    for index in range(len(matches) - 1, -1, -1):
        heading = matches[index]
        if heading.group(1) == "Educational guidance":
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            if text[heading.end():end].strip() != DISCLAIMER:
                suffix = '\n\n' if end < len(text) else ''
                text = text[:heading.end()].rstrip() + '\n' + DISCLAIMER + suffix + text[end:]
    if not cited:
        return text
    headings = tuple(_HEADING.findall(text))
    if not headings and text:
        body = text.removesuffix(DISCLAIMER).rstrip()
        return '**Insight**\n'+body+'\n\n**Educational guidance**\n'+DISCLAIMER
    if headings in (('Insight',), ('Insight', 'Recommended action')):
        return text+'\n\n**Educational guidance**\n'+DISCLAIMER
    return text


# Written working: operands joined by symbol operators, then "=" or "≈" and a
# result. Language-neutral (symbols only); an operand may carry one unit word.
# Money uses the shared currency definition; no currency is named here.
_CURRENCY = re.sub(r"\(\?P<\w+>", "(?:", _CURRENCY_AMOUNT.pattern)
_CALC_NUMBER = rf"(?:{_CURRENCY}|\d[\d,]*(?:\.\d+)?%?)"
_CALC_OPERAND = rf"{_CALC_NUMBER}(?:\s+[^\W\d_]{{1,12}})?"
_CALC_OPERATOR = r"\s*(?:[×*÷/+−]|-(?=\s)|(?<=\s)x(?=\s))\s*"
_CALCULATION = re.compile(
    rf"(?P<left>{_CALC_OPERAND}(?:{_CALC_OPERATOR}{_CALC_OPERAND})+)\s*[=≈]\s*(?P<result>{_CALC_OPERAND})",
    re.IGNORECASE)


def _calc_number(token: str) -> tuple[str, bool] | None:
    """The written number of a calculation token and whether it is a percentage."""
    money = _CURRENCY_AMOUNT.match(token.strip())
    if money:
        return money.group("amount").replace("−", "-"), False
    plain = re.match(r"\s*(\d[\d,]*(?:\.\d+)?)(%?)", token)
    return (plain.group(1), bool(plain.group(2))) if plain else None


def _calc_value(token: str) -> Decimal | None:
    parsed = _calc_number(token)
    if parsed is None:
        return None
    value = Decimal(parsed[0].replace(",", ""))
    return value / 100 if parsed[1] else value


def _verified_calculations(sentence: str, allowed: set[str]) -> set[str]:
    """Result values of the written calculations in a sentence that code can
    verify: every money/percentage operand is already allowed (the user's own
    values, approved evidence or an earlier verified result), and the result
    equals the arithmetic to the precision it is shown with. Bare counts (4
    weeks, 12 months) are visible multipliers. Unverifiable results are not
    returned, so they still need source support."""
    verified: set[str] = set()
    allowed = set(allowed)
    for match in _CALCULATION.finditer(sentence):
        operands = re.findall(_CALC_OPERAND, match.group("left"), re.IGNORECASE)
        operators = [op.strip() for op in re.findall(_CALC_OPERATOR, match.group("left"))]
        if len(operators) != len(operands) - 1:
            continue
        if any(not _numeric_values(op) <= allowed for op in operands):
            continue
        values = [_calc_value(op) for op in operands]
        result = _calc_value(match.group("result"))
        if result is None or any(value is None for value in values):
            continue
        # Multiplication and division first, then addition and subtraction.
        terms, signs = [values[0]], []
        try:
            for operator, value in zip(operators, values[1:]):
                if operator in ("×", "*", "x", "X"):
                    terms[-1] *= value
                elif operator in ("÷", "/"):
                    terms[-1] /= value
                else:
                    signs.append(-1 if operator in ("-", "−") else 1)
                    terms.append(value)
        except (InvalidOperation, ZeroDivisionError):
            continue
        total = terms[0] + sum(sign * term for sign, term in zip(signs, terms[1:]))
        shown = match.group("result")
        number = _calc_number(shown)[0]
        places = len(number.split(".")[1]) if "." in number else 0
        scale = Decimal(1).scaleb(-places) / 2
        if "%" in shown:
            total *= 100
            result *= 100
        if abs(total - result) <= scale:
            verified |= _numeric_values(shown)
            allowed |= _numeric_values(shown)  # a later step may build on it
    return verified


def _verified_rank(diagnostics: dict | None) -> tuple[int, int]:
    """How much checked content an answer keeps: the requested parts its
    surviving claims address, then the number of approved claims."""
    diagnostics = diagnostics or {}
    return (len(diagnostics.get("addressed_part_ids") or ()), int(diagnostics.get("approved_claim_count") or 0))


def check_research_draft(draft: str, *, public_question: str,
                         decision: ResearchDecision, budget: CoachRequestBudget,
                         max_words: int | None = None, completion: LLMResult | None = None,
                         unit_bindings: dict[str, tuple[str, ...]] | None = None,
                         given_text: str = "", resolved_question: str = "") -> ResearchDraftCheck:
    """Strict structure/numbers followed by one semantic and quality batch.

    ``given_text`` is the user's own question. Numbers and codes the user
    wrote (parsed exactly like the draft's) are not sourced claims, so
    repeating them needs no source support; every other number still does.
    """
    text = draft.strip()
    word_limit = min(COACH_RESEARCH_MAX_WORDS,
                     COACH_RESEARCH_MAX_WORDS if max_words is None else max_words)
    # Models sometimes group citations as [S1, S2]. Canonicalize these before
    # checking source identities; the UI strips only the standard [S1] form.
    text = re.sub(r"\[S\d+(?:\s*,\s*S?\d+)+\]",
        lambda match: " ".join(f"[S{index}]" for index in re.findall(r"\d+", match.group())), text)
    errors = []
    headings = tuple(_HEADING.findall(text))
    if headings not in (REQUIRED_HEADINGS, ("Insight", "Educational guidance")) or not text.startswith("**Insight**"):
        errors.append("invalid_structure")
    # A token-limited generation is incomplete by construction: punctuation and a
    # later "supported" verdict cannot restore the words the provider never wrote.
    if completion is not None and str(completion.finish_reason or "").upper() in {"LENGTH", "MAX_TOKENS"}:
        errors.append("answer_output_truncated")
    # A stop flag is likewise not proof of grammatical completion. Never ship a
    # rule whose predicate or object is missing, whatever the verifier says.
    elif any(
        re.search(r"\b(?:and|or|of|for|with|the|a|an|your|their|not|dan|atau|untuk)\s*$",
                  _MARKER.sub("", sentence).strip().rstrip(".!?"), re.I)
        and not allowed_generated_ending(_MARKER.sub("", sentence))
        for _, sentence, _ in _body_units(text) if not sentence.endswith(":")
    ):
        errors.append("answer_output_truncated")
    educational = text.rsplit("**Educational guidance**", 1)[-1].strip()
    if educational != DISCLAIMER:
        errors.append("invalid_disclaimer")
    # The checker judges product steering by meaning. This word check only
    # decides when no usable verdict comes back, and is logged for comparison.
    old_filter_flagged = contains_specific_product_recommendation(text)
    if len(_MARKER.sub("", _HEADING.sub("", text)).split()) > word_limit:
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
    claim_bindings: list[tuple[int, tuple[str, ...]]] = []
    assessment_claim_ids = []
    numeric_rejections = set()
    calculated: set[str] = set()
    channel_rejections = set()
    notice_rejections = set()
    qualifications = {}
    # Requested-part relevance. A notice may only report a gap the REQUEST itself
    # has (a validated unresolved part); a request that never asked for a
    # comparison cannot receive a comparison-table disclaimer, whatever the
    # assessor wrote in its missing list.
    part_labels = tuple(decision.diagnostics.get("requested_part_labels", ()))
    requested_part_seq = tuple(RequestedPart(part.part_id, label) for part, label in
                               zip(decision.assessment.parts, part_labels or
                                   tuple(p.part_id for p in decision.assessment.parts)))
    validated_unresolved = tuple(p.part_id for p in decision.assessment.parts
                                 if p.status == "missing" and not p.complete)
    part_tracked = bool(decision.assessment.parts)
    source_bindings = {binding.binding_id: getattr(binding, "quote_index", None)
                       for binding in decision.assessment.fact_bindings}
    for position, (_, sentence, _) in enumerate(units):
        block = units[position][2]
        if sentence.endswith(":"):
            qualifications[block] = sentence
            continue
        # A possible coverage note still gets a verdict in the SAME semantic
        # batch. Its assessment support must not become a fake source citation,
        # and the verifier must reject any financial fact hidden inside it.
        is_coverage = bool(_GAP_NOTE.match(_MARKER.sub("", sentence)))
        if is_coverage and part_tracked and not validated_unresolved:
            # No requested part is unresolved, so this note reports a gap the
            # request does not have. It is unrelated advice, not coverage.
            notice_rejections.add(position)
            continue
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
        # Form identifiers contain numbers that the money parser intentionally
        # ignores. They still require literal support in approved evidence.
        form_codes = lambda value: {re.sub(r"[-\s]", "", code).casefold()
            for code in re.findall(r"\b[A-Z]{2,12}[- ]?\d{1,4}[A-Z]?\b", value)
            # Currency amounts are the shared money parser's job, not codes.
            if not _CURRENCY_AMOUNT.fullmatch(code)}
        # Values the sentence may state: approved evidence, the user's own
        # values, and results of written calculations that code verified
        # (here or earlier in the draft). Context is judged by the verifier.
        permitted = _numeric_values(positive) | _numeric_values(given_text) | calculated
        calculated |= _verified_calculations(sentence, permitted)
        if (not _numeric_values(sentence).issubset(permitted | calculated)
                or not form_codes(sentence).issubset(form_codes(positive) | form_codes(given_text))):
            # Reject this statement, while still checking independent useful
            # facts. A numeric mismatch cannot authorize the rest of a list.
            numeric_rejections.add(position)
        if re.search(r"\b(?:upload(?:s|ed|ing)?|(?:me)?muat\s+naik)\b", sentence, re.I):
            uncertain = ambiguous_online_forms([quote for source_id, quote in decision.assessment.supported_quotes
                                                if source_id in candidates])
            # Keep alternative clauses separate: a physical-delivery form can
            # coexist with uploading documents, but cannot become the upload's
            # object merely because both routes share a sentence.
            for clause in re.split(r"\b(?:or|atau)\b", sentence, flags=re.I):
                if not re.search(r"\b(?:upload(?:s|ed|ing)?|(?:me)?muat\s+naik)\b", clause, re.I):
                    continue
                claim_codes = form_codes(clause)
                handover_reference = re.search(
                    r"\b(?:(?:handover|(?:document\s+)?submission)\s+form|borang\s+serahan)\b", clause, re.I)
                if uncertain & claim_codes or uncertain and handover_reference and not claim_codes:
                    channel_rejections.add(position)
        try:
            named_sentence = _name_inline_sources(sentence, decision.chunks)
        except ValueError:
            errors.append("invalid_structure")
            named_sentence = sentence
        section, _, block = units[position]
        units[position] = (section, named_sentence, block)
        claim_text = _MARKER.sub("", named_sentence).strip()
        # A model verdict cannot supply a missing predicate or finish a rule.
        # Apply the same structural backstop used for retrieved quotations.
        if complete_evidence_passages(claim_text, generated=True) != (claim_text,):
            errors.append("incomplete_statement")
        if re.match(r"^(?:[-•▪]|\d+[.)])\s", sentence) and block in qualifications:
            claim_text = f"{qualifications[block]} {claim_text}"
        claim = GroundingClaim(len(claims) + 1, claim_text, candidates,
                               requires_citation=not bool(indices))
        claims.append(claim)
        claim_units[claim.id] = position
        # Narrow a part's binding union to the sentence's OWN cited source. Two
        # facts from one part must not let either sentence borrow the other
        # category's scope.
        from app.rag.research_blocks import unit_key
        declared = tuple((unit_bindings or {}).get(unit_key(sentence), ()))
        if declared:
            claim_bindings.append((claim.id, tuple(
                binding_id for binding_id in declared
                if source_bindings.get(binding_id) is None
                or source_bindings.get(binding_id) in set(candidates))))
        # Every statement is eligible for semantic *type* checking. Even a
        # "sufficient" assessment can have missed a genuine coverage gap.
        # Financial facts still need a real source; only pure metadata may get
        # the verifier's explicit assessment-supported verdict.
        assessment_claim_ids.append(claim.id)
    if not claims or all(not c.cited_indices for c in claims):
        errors.append("no_claims")
    if len(claims) > research_claim_limit():
        errors.append("too_many_claims")
    # Source names can be longer than markers. Count the text the reader gets,
    # while numeric validation above still applies to the original factual prose.
    if len(_MARKER.sub("", _HEADING.sub("", _render(units))).split()) > word_limit:
        errors.append("answer_too_long")
    if errors:
        return ResearchDraftCheck(False, tuple(dict.fromkeys(errors)), diagnostics={
            "candidate_claim_count": len(claims), "approved_claim_count": 0})
    try:
        verification = verify_grounding_claims(
            claims, approved_references(decision), timeout_seconds=budget.timeout_for("research_verifier"),
            max_tokens=research_verifier_max_tokens(len(claims)),
            research_context=ResearchVerificationContext(public_question, _render(units), decision.assessment.missing,
                                                        decision.assessment.conflicting,
                                                        tuple(assessment_claim_ids), enforce_scope=True,
                                                        assess_product_policy=True,
                                                        requested_parts=requested_part_seq,
                                                        coverage=decision.assessment.parts,
                                                        fact_bindings=decision.assessment.fact_bindings,
                                                        claim_bindings=tuple(claim_bindings),
                                                        claim_parts=tuple(
                                                            (claim.id, _claim_part_ids(claim.text,
                                                                                       requested_part_seq))
                                                            for claim in claims)),
        )
    except Exception:
        return ResearchDraftCheck(False, ("verifier_unavailable",))
    diagnostics = {"candidate_claim_count": len(claims), "approved_claim_count": 0,
                   "citation_repairs": citation_repairs,
                   "numeric_rejected_claim_count": len(numeric_rejections),
                   "channel_rejected_claim_count": len(channel_rejections),
                   "unrelated_notice_count": len(notice_rejections),
                   "model": verification.model, "prompt_tokens": verification.prompt_tokens,
                   "completion_tokens": verification.completion_tokens,
                   "elapsed_ms": verification.elapsed_ms}
    diagnostics.update(requested_scope_covered=verification.requested_scope_covered,
                       unanswered_requested_parts=list(verification.unanswered_requested_parts),
                       answered_part_ids=list(verification.answered_part_ids))
    if verification.applicability:
        diagnostics["applicability"] = {str(key): value
                                        for key, value in verification.applicability.items()}
    if verification.error_code:
        return ResearchDraftCheck(False, (verification.error_code,), diagnostics=diagnostics)
    # Defend the coordinator boundary too, including fakes/custom verifier clients.
    if (set(verification.verdicts) != set(claim_units) or any(
        verdict not in {"supported", "unsupported", "contradicted", "misapplied"}
        for verdict in verification.verdicts.values()
    )):
        return ResearchDraftCheck(False, ("invalid_verifier_response",), diagnostics=diagnostics)
    product_verdict = verification.product_verdict
    product_claim_ids = tuple(i for i in verification.product_claim_ids if i in claim_units)
    product_entity = verification.product_entity
    reason = None
    if product_verdict == "recommendation" and not product_recommendation_matches_draft(
            product_claim_ids, product_entity, text):
        reason = (f"named_entity {json.dumps(product_entity, ensure_ascii=False)} with claim_ids "
                  f"{list(product_claim_ids)} does not identify a name and claims in this draft")
        product_verdict = "uncertain"
    elif product_verdict not in {"allowed", "recommendation"}:
        reason = f"the verdict was {product_verdict}"
    first_verdict = product_verdict
    decided_by = "checker"
    if reason is not None:
        # The checker judges product steering by meaning; it is asked once more
        # with the exact reason. A push needs a named product in the draft, so a
        # verdict that still cannot point at one keeps the answer.
        claims_by_id = [claim for claim in claims if claim.id in claim_units]
        rechecked, recheck_ids, recheck_entity = recheck_product_policy(
            public_question, _render(units), claims_by_id, reason,
            timeout_seconds=min(COACH_PRODUCT_RECHECK_SECONDS, budget.remaining_seconds()))
        decided_by = "recheck"
        if rechecked == "recommendation":
            product_verdict, product_claim_ids, product_entity = "recommendation", recheck_ids, recheck_entity
        else:
            product_verdict, product_claim_ids = "allowed", ()
            decided_by = "recheck_" + rechecked
    product_rejections = ({claim_units[i] for i in product_claim_ids if i in claim_units}
                          if product_verdict == "recommendation" else set())
    # Codes and counts only. The old word check is computed for comparison and
    # no longer decides research answers.
    diagnostics["product_policy"] = {"verdict": product_verdict, "first_verdict": first_verdict,
                                     "decided_by": decided_by,
                                     "claim_count": len(product_rejections),
                                     "old_filter_flagged": old_filter_flagged}
    logger.info(json.dumps({"event": "coach_product_policy", **diagnostics["product_policy"]}))
    if product_verdict == "recommendation" and not product_rejections:
        return ResearchDraftCheck(False, ("product_recommendation",), diagnostics=diagnostics)
    # A scope error can accompany explicit claim-level rejections. Preserve
    # only independently approved blocks below; a global language/reference
    # error, or a scope error without identified rejected claims, still fails.
    scoped_rejections = (set(verification.quality_errors) == {'incomplete_supported_answer'}
        and any(verdict != 'supported' for verdict in verification.verdicts.values()))
    if verification.quality_errors and not scoped_rejections:
        return ResearchDraftCheck(False, verification.quality_errors, diagnostics=diagnostics)
    if not verification.source_indices:
        misapplied_only = any(verdict == "misapplied" for verdict in verification.verdicts.values())
        return ResearchDraftCheck(False, ("misapplied_claim" if misapplied_only else "no_supported_facts",),
                                  diagnostics=diagnostics)
    misapplied_ids = {claim_id for claim_id, verdict in verification.verdicts.items()
                      if verdict == "misapplied"}
    # A gap note about something the request never asked is dropped on its
    # own: it is not missing requested information, so it neither removes the
    # verified sentences beside it nor triggers the partial-answer caveat.
    rejected_blocks = set()
    for claim in claims:
        position = claim_units[claim.id]
        section, sentence, block = units[position]
        if position in numeric_rejections or position in channel_rejections or position in product_rejections:
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
    # A part has a displayed explanation only when the semantic verifier bound
    # it to a positive claim that survives local checks. Shared document/source
    # numbers carry evidence identity, not which question a sentence answers.
    retained_claims = {
        claim.id for claim in claims
        if verification.verdicts.get(claim.id) == "supported"
        and claim.id in verification.source_indices
        and claim.id not in verification.assessment_supported_ids
        and units[claim_units[claim.id]][2] not in rejected_blocks
        and claim_units[claim.id] not in notice_rejections
    }
    diagnostics["addressed_part_ids"] = [
        part_id for part_id, claim_ids in verification.answered_part_claims
        if set(claim_ids) & retained_claims
    ]
    # Coverage completeness and having any displayed answer are distinct.
    # Missing semantic mappings are unknown, not proof of a missing answer.
    part_claims = dict(verification.answered_part_claims)
    note_missing = tuple(part.label for part in requested_part_seq
                         if part_claims and part_labels
                         and not set(part_claims.get(part.id, ())) & retained_claims)
    diagnostics['gap_note_parts'] = list(note_missing)
    # Partial coverage remains diagnostic; display no longer promotes it into prose.
    diagnostics['gap_note_added'] = False
    if rejected_blocks:
        # Removing an optional aside does not remove a requested answer. Keep a
        # part complete only if BOTH coverage gates passed and ALL the positive
        # claims the verifier bound to that part survived local validation.
        # A missing mapping is not proof of completeness (legacy replies remain
        # conservative); sharing a source or retaining just one claim is not enough.
        eligible = {part.part_id for part in decision.assessment.parts if part.complete}
        surviving_parts = {
            part_id for part_id, claim_ids in verification.answered_part_claims
            if part_id in verification.answered_part_ids and part_id in eligible
            and claim_ids and set(claim_ids) <= retained_claims
        }
        diagnostics["answered_part_ids"] = [
            part.id for part in requested_part_seq if part.id in surviving_parts]
        missing = tuple(part.label for part in requested_part_seq if part.id not in surviving_parts)
        displayed_complete = bool(requested_part_seq) and not missing and not verification.quality_errors
        diagnostics["requested_scope_covered"] = displayed_complete
        diagnostics["unanswered_requested_parts"] = list(missing) if requested_part_seq else list(dict.fromkeys((
            *verification.unanswered_requested_parts, "requested details removed during verification")))[:6]
        approved = [unit for position, unit in enumerate(units)
                    if unit[2] not in rejected_blocks and position not in notice_rejections]
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
            # Partial coverage stays in diagnostics, not displayed prose.
            if len(_MARKER.sub("", _HEADING.sub("", _render(approved))).split()) > word_limit:
                usable = False
        diagnostics["approved_claim_count"] = sum(
            units[position][2] not in rejected_blocks for position in claim_units.values()) if usable else 0
        code = ("product_recommendation" if product_rejections else
                "ambiguous_submission_channel" if channel_rejections else
                "unsupported_number" if numeric_rejections else
                "misapplied_claim" if misapplied_ids else "unsupported_claim")
        valid = usable and displayed_complete
        return ResearchDraftCheck(valid, () if valid else (code,), _render(approved) if usable else None,
                                  diagnostics=diagnostics)
    diagnostics["approved_claim_count"] = len(claims)
    units = [unit for position, unit in enumerate(units) if position not in notice_rejections]
    if verification.requested_scope_covered is False:
        # Retain verified statements for the one grounded rewrite. Coverage is
        # independent of factual entailment; a useful partial need not disappear.
        # Preserve coverage diagnostics and recovery decisions without a notice.
        if len(_MARKER.sub("", _HEADING.sub("", _render(units))).split()) > word_limit:
            return ResearchDraftCheck(False, ("answer_too_long",), diagnostics=diagnostics)
        # An already honest, verified partial cannot gain missing source facts
        # from a writer retry. Rewrite only a draft that concealed its coverage
        # gap (or the existing quality gate detected omitted supported details).
        honest_partial = bool(verification.assessment_supported_ids)
        return ResearchDraftCheck(honest_partial, () if honest_partial else ("requested_scope_incomplete",),
                                  _render(units), diagnostics)
    return ResearchDraftCheck(True, approved_text=_render(units), diagnostics=diagnostics)


_TEMPORARY_FAILURE_MESSAGES = {
    "en": "I could not retrieve the source details needed for this question. Please try again.",
    "ms": "Saya tidak dapat mendapatkan maklumat sumber yang diperlukan kali ini. Sila cuba lagi.",
    "zh": "这次未能获取所需的来源信息，请重试。",
    "ta": "தேவையான ஆதாரத் தகவலை இம்முறை பெற முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
}
_INSUFFICIENT_EVIDENCE_MESSAGES = {
    "en": "I couldn't find enough reliable information to answer that accurately, so I won't guess. "
          "You could rephrase it or ask about a more specific financial topic.",
    "ms": "Saya tidak menemui maklumat yang cukup boleh dipercayai untuk menjawabnya dengan tepat, "
          "jadi saya tidak akan meneka. Cuba ubah soalan anda atau tanya tentang topik kewangan yang lebih khusus.",
    "zh": "我没有找到足够可靠的信息来准确回答这个问题，所以不会妄加猜测。"
          "你可以换个方式提问，或询问更具体的理财话题。",
    "ta": "இதற்குத் துல்லியமாகப் பதிலளிக்கப் போதுமான நம்பகமான தகவல் கிடைக்கவில்லை, எனவே நான் ஊகிக்க மாட்டேன். "
          "கேள்வியை மாற்றிக் கேட்கலாம் அல்லது மேலும் குறிப்பிட்ட நிதித் தலைப்பைப் பற்றிக் கேட்கலாம்.",
}
_OUT_OF_SCOPE_MESSAGES = {
    "en": "I don't have enough information to answer this topic. Please refer to learning resources on the subject.",
    "ms": "Saya tidak mempunyai maklumat yang cukup untuk menjawab topik ini. Sila rujuk sumber pembelajaran "
          "tentang subjek tersebut.",
    "zh": "我没有足够的信息来回答这个话题。请参考该学科的学习资源。",
    "ta": "இந்தத் தலைப்புக்குப் பதிலளிக்கப் போதுமான தகவல் என்னிடம் இல்லை. அந்தப் பாடம் தொடர்பான கற்றல் "
          "வளங்களைப் பார்க்கவும்.",
}
_NON_FINANCE_PART_MESSAGES = {
    "en": "For the part of your question outside financial topics, I don't have enough information. "
          "Please refer to learning resources on the subject.",
    "ms": "Bagi bahagian soalan anda di luar topik kewangan, saya tidak mempunyai maklumat yang cukup. "
          "Sila rujuk sumber pembelajaran tentang subjek tersebut.",
    "zh": "对于你问题中与理财无关的部分，我没有足够的信息。请参考该学科的学习资源。",
    "ta": "உங்கள் கேள்வியில் நிதி அல்லாத பகுதிக்கு என்னிடம் போதுமான தகவல் இல்லை. அந்தப் பாடம் தொடர்பான "
          "கற்றல் வளங்களைப் பார்க்கவும்.",
}


# These keys are checker/generator diagnostics, never text from the question.
_FAILURE_CODES = {
    "product_steering": {"product_recommendation"},
    "no_evidence": {"no_approved_evidence", "no_supported_facts", "misapplied_claim",
                    "unsupported_claim", "unsupported_number", "ambiguous_submission_channel"},
    "technical": {"verifier_unavailable", "verifier_timeout", "verifier_http_error",
                  "answer_generation_unavailable", "recovery_generation_unavailable",
                  "provider_auth_error", "provider_configuration_error", "research_time_exhausted"},
    "unusable_draft": {"invalid_structure", "answer_output_truncated", "answer_too_long",
                       "no_claims", "incomplete_statement", "invalid_disclaimer", "too_many_claims",
                       "requested_scope_incomplete", "invalid_verifier_response", "verifier_invalid_json",
                       "verifier_output_truncated", "language_mismatch", "raw_reference_dump",
                       "incomplete_supported_answer"},
}

_RETRY_MESSAGES = {
    "en": UNAVAILABLE_MESSAGE,
    "ms": "Penjelasan ini belum dapat diselesaikan. Sila cuba lagi.",
    "zh": "这次未能完成说明，请重试。",
    "ta": "இம்முறை விளக்கத்தை முடிக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
}
_PRODUCT_MESSAGES = {
    "en": "I can explain how to compare options, but I can't pick a company for you.",
    "ms": "Saya boleh menerangkan cara membandingkan pilihan, tetapi saya tidak boleh memilih syarikat untuk anda.",
    "zh": "我可以说明怎样比较不同选项，但不能替你挑选公司。",
    "ta": "விருப்பங்களை ஒப்பிடும் முறையை என்னால் விளக்க முடியும். உங்களுக்காக ஒரு நிறுவனத்தைத் தேர்ந்தெடுக்க முடியாது.",
}
_UNKNOWN_MESSAGES = {
    "en": "I couldn't complete this explanation.",
    "ms": "Saya tidak dapat melengkapkan penjelasan ini.",
    "zh": "我未能完成这段说明。",
    "ta": "இந்த விளக்கத்தை என்னால் முடிக்க முடியவில்லை.",
}


def _failure_reply(language, cause_codes, errors):
    # If the attempted correction never produced a draft, it has no new
    # evidence about the original rejection. Prefer that original diagnosis.
    codes = errors or cause_codes
    if codes == ("recovery_generation_unavailable",) and cause_codes:
        codes = cause_codes
    reason = next((key for key, members in _FAILURE_CODES.items()
                   if any(code in members for code in codes)), "unknown")
    messages = {"technical": _RETRY_MESSAGES, "unusable_draft": _RETRY_MESSAGES,
                "product_steering": _PRODUCT_MESSAGES, "no_evidence": _INSUFFICIENT_EVIDENCE_MESSAGES,
                "unknown": _UNKNOWN_MESSAGES}[reason]
    return reason, messages.get((language or "en").lower().split("-")[0], messages["en"])


def non_finance_part_note(plan: QuestionPlan, parts) -> str | None:
    """Short referral for a labelled non-finance part that the final answer
    does not cover; None when every such part was answered.

    ``parts`` is the final coverage: part IDs the checked answer actually
    answers (or coverage rows with ``complete``). A source that was found but
    did not support the explanation the user receives does not count.
    """
    scope = getattr(plan, "finance_scope", None)
    if not (scope == "mixed" or (scope == "non_finance" and getattr(plan, "part_domains", ()))):
        return None
    blocked = set(non_finance_part_ids(plan))
    covered = {part if isinstance(part, str) else part.part_id for part in parts or ()
               if isinstance(part, str) or part.complete}
    if not blocked or blocked <= covered:
        return None
    language = (plan.response_language or "en").split("-")[0]
    return _NON_FINANCE_PART_MESSAGES.get(language, _NON_FINANCE_PART_MESSAGES["en"])


def no_evidence_message(plan: QuestionPlan, failure: str | None) -> str:
    """Public wording for a research turn that produced no approved evidence.

    Fixed text only. A technical failure comes first (temporary wording), so
    an outage is never presented as out of scope; a non-finance question skips
    the web on purpose, so its "search_disabled" is not one. Then a validated
    non-finance question gets the referral (published knowledge was checked),
    and anything else says the evidence fell short. Provider and
    configuration details never reach the user.
    """
    language = (plan.response_language or "en").split("-")[0]
    non_finance = getattr(plan, "finance_scope", None) == "non_finance"
    if failure in SEARCH_FAILURE_REASONS and not (non_finance and failure == "search_disabled"):
        messages = _TEMPORARY_FAILURE_MESSAGES
    elif non_finance and getattr(plan, "part_domains", ()):
        # The labelled non-finance part left after the rest of a mixed
        # question was answered: its referral is the part note, given once.
        return ""
    elif non_finance:
        messages = _OUT_OF_SCOPE_MESSAGES
    else:
        messages = _INSUFFICIENT_EVIDENCE_MESSAGES
    return messages.get(language, messages["en"])


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
    budget = research_work_budget(budget)
    checks = []
    initial_candidate = None
    initial_check = None
    used = False
    rewrite_skipped_for_time = False
    errors = (initial_failure,) if initial_failure else ()
    cause_codes = errors
    # Approved evidence is whatever literal quotation(s) the approved sources
    # actually contain; a corpus-only decision may arrive without the list.
    decision = with_approved_evidence(decision)
    # The user's own question: values they wrote (e.g. their own target) may
    # be repeated without source support; they are parsed like draft numbers.
    given_text = getattr(plan, "original_question", "") or ""
    question_reserve = len((clarification_question(plan) or "").split()) if clarification_part_ids(plan) else 0
    max_words = COACH_RESEARCH_MAX_WORDS - question_reserve
    def record(result):
        tokens.append({"model": result.model, "prompt_tokens": result.prompt_tokens,
                       "completion_tokens": result.completion_tokens})
    if draft is not None:
        record(draft)

    def finish(result, mode, content, *, complete=False, reply_reason=None):
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
        # Referral coverage follows the semantic claim-to-part links of the
        # displayed answer. A source number may support several unrelated
        # topics, so citing it cannot grant coverage to every such topic.
        shown_check = initial_check if initial_candidate and result is draft else checks[-1] if checks else {}
        answered = () if mode == "research_explanation_unavailable" and not used_indices else tuple(
            {*shown_check.get("answered_part_ids", ()), *shown_check.get("addressed_part_ids", ())})
        note = non_finance_part_note(plan, answered)
        if note and note in content:
            note = None
        # One assembly: verified personal answer, the explanation, the referral.
        content = "\n\n".join(piece for piece in (personal_facts, content, note) if piece)
        wrapped = AgentLLMResult(content, result.model, result.prompt_tokens, result.completion_tokens)
        diagnostics = {"reply_reason": reply_reason or ("complete" if complete else "partial"), "recovery_used": used, "error_codes": list(errors),
                       "rewrite_skipped_for_time": rewrite_skipped_for_time,
                       "cause_codes": list(cause_codes or errors), "verification": checks,
                       "generation_tokens": tokens, "displayed_model": result.model,
                       "complete": complete, "used_source_indices": used_indices,
                       "clarification_part_ids": list(clarification_part_ids(plan))}
        displayed_check = initial_check if initial_candidate and result is draft else checks[-1] if checks else {}
        diagnostics.update(requested_scope_covered=displayed_check.get("requested_scope_covered"),
            answered_part_ids=displayed_check.get("answered_part_ids", []),
            addressed_part_ids=displayed_check.get("addressed_part_ids", []),
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
            "terminal_reason": diagnostics["terminal_reason"], "reply_reason": diagnostics["reply_reason"],
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
        source_message = no_evidence_message(plan, decision.failure)
        if plan.clarification_facts:
            # A concrete clarification can move the conversation forward even
            # when the independently requested source facts are unavailable.
            source_message = {
                "ms": "Saya belum dapat memastikan maklumat bagi bahagian lain soalan anda.",
                "zh": "我暂时还未确认你所问的其他细节。",
                "ta": "உங்கள் கேள்வியின் மற்ற விவரங்களை இன்னும் உறுதிப்படுத்தவில்லை.",
            }.get(language, "I haven't established the other requested details yet.")
        return finish(AgentLLMResult("", "fincoach-research-explanation"),
                      "research_explanation_unavailable", source_message,
                      reply_reason=("clarification" if plan.clarification_facts else
                                    "technical" if decision.failure in SEARCH_FAILURE_REASONS
                                    and not (getattr(plan, "finance_scope", None) == "non_finance"
                                             and decision.failure == "search_disabled") else
                                    "out_of_scope" if getattr(plan, "finance_scope", None) == "non_finance"
                                    else "no_evidence"))
    if draft is not None and budget.remaining_seconds() > 0:
        checked = check_research_draft(normalize_research_layout(draft.content), public_question=public_question,
            max_words=max_words, completion=draft, given_text=given_text, resolved_question=plan.question or "",
            decision=decision, budget=budget.for_stage(max_seconds=COACH_RESEARCH_VERIFIER_MAX_SECONDS))
        checks.append(checked.diagnostics)
        if checked.is_valid:
            return finish(draft, "research_explanation", checked.approved_text,
                          complete=(not checked.diagnostics.get("coverage_note_count")
                                    and checked.diagnostics.get("requested_scope_covered") is not False))
        if checked.approved_text:
            initial_candidate = checked.approved_text
            initial_check = checked.diagnostics
        errors = checked.error_codes
        cause_codes = errors
    # At most ONE corrective generation, and only when a useful rewrite plus the
    # final semantic check still fit inside the ORIGINAL deadline.
    correction_budget = correction_writer_budget(budget)
    if correction_budget is None and initial_failure not in {"provider_auth_error", "provider_configuration_error"}:
        rewrite_skipped_for_time = True
        logger.info(json.dumps({"event": "coach_rewrite_skipped", "reason": "insufficient_time",
            "remaining_seconds": round(budget.remaining_seconds(), 3),
            "checked_answer_available": bool(initial_candidate)}))
    if (initial_failure not in {"provider_auth_error", "provider_configuration_error"}
            and correction_budget is not None):
        used = True
        try:
            recovered = within_writer_deadline(
                lambda: _generate_research_correction(
                    build_research_recovery_prompt(public_question, decision, errors),
                    # Leave the measured checker allowance within the work deadline.
                    budget=correction_budget,
                    system_prompt=RESEARCH_EXPLANATION_SYSTEM_PROMPT,
                ),
                correction_budget.remaining_seconds(),
            )
            record(recovered)
            checked = check_research_draft(normalize_research_layout(recovered.content), public_question=public_question,
                max_words=max_words, completion=recovered, given_text=given_text, resolved_question=plan.question or "",
                decision=decision, budget=budget.for_stage(max_seconds=COACH_RESEARCH_VERIFIER_MAX_SECONDS))
            checks.append(checked.diagnostics)
            if (not checked.is_valid and checked.approved_text and initial_candidate
                    and _verified_rank(checked.diagnostics) < _verified_rank(initial_check)):
                # The rewrite kept less verified content than the first draft:
                # show the first draft's checked answer instead of replacing it.
                errors = checked.error_codes
                return finish(draft, "research_explanation_recovery", initial_candidate)
            if checked.is_valid or checked.approved_text:
                errors = checked.error_codes
                return finish(recovered, "research_explanation_recovery", checked.approved_text,
                              complete=(checked.is_valid
                                        and not checked.diagnostics.get("coverage_note_count")
                                        and checked.diagnostics.get("requested_scope_covered") is not False))
            errors = checked.error_codes
        except Exception:
            errors = ("recovery_generation_unavailable",)
    if initial_candidate:
        return finish(draft, "research_explanation_recovery", initial_candidate)
    if not errors and not cause_codes and (budget.remaining_seconds() <= 0 or correction_budget is None):
        errors = ("research_time_exhausted",)
    reason, message = _failure_reply(plan.response_language, cause_codes, errors)
    return finish(AgentLLMResult("", "fincoach-research-explanation"),
                  "research_explanation_unavailable", message, reply_reason=reason)
