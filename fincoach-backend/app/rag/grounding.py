"""Deterministic guardrails for provider-generated educational answers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil
import re


REQUIRED_HEADINGS = (
    "Insight",
    "Recommended action",
    "Educational guidance",
)
DISCLAIMER = "This is educational guidance, not licensed financial advice."
_HEADING = re.compile(r"^\*\*(.+?)\*\*\s*$", re.MULTILINE)
_SOURCE_MARKER = re.compile(r"\[S(\d+)\]")
_NUMERIC_CLAIM = re.compile(
    r"(?:RM\s?[-+\u2212]?\d[\d,]*(?:\.\d{1,2})?|\b\d+(?:[.,]\d+)?\s?(?:%|"
    r"percent|days?|months?|years?|hari|bulan|tahun))",
    re.IGNORECASE,
)
_CURRENCY_AMOUNT = re.compile(
    r"(?P<currency>RM|\$)\s?(?P<amount>[-+\u2212]?\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_EXAMPLE_WINDOW = 60
_EXAMPLE_CUE = re.compile(
    r"\b(?:for\s+example|for\s+instance|as\s+an\s+example|let'?s\s+say|"
    r"let\s+us\s+say|suppose|imagine|hypothetical(?:ly)?|say|such\s+as|"
    r"contoh(?:nya)?|sebagai\s+contoh|misal(?:nya)?|umpama(?:nya)?|"
    r"katakan(?:lah)?|andai(?:kan)?)\b|(?:e\.?g\.?|i\.?e\.?)",
    re.IGNORECASE,
)
_EXAMPLE_SENTENCE_BOUNDARY = re.compile(r"[.!?](?:\s|$)|\n")
_CALCULATION_BLOCK = re.compile(
    r"Calculation:\s*(.+?)(?:\n|$)", re.IGNORECASE
)
_SPECIFIC_PRODUCT_RECOMMENDATION = re.compile(
    r"\b(?:open|choose|switch\s+to|sign\s+up\s+for|buy|use)\b"
    r".{0,80}\b(?:account|app|wallet|provider|coin|stock|fund|policy|product)\b",
    re.IGNORECASE,
)
_EXTERNAL_FACT_CUE = re.compile(
    r"\b(?:is|are|was|were|protect(?:s|ed)?|cover(?:s|ed)?|"
    r"require(?:s|d)?|allow(?:s|ed)?|provide(?:s|d)?|mean(?:s|t)?|"
    r"eligible|automatic|free|affect(?:s|ed)?|must|cannot|may|"
    r"guarantee(?:s|d)?|include(?:s|d)?|exclude(?:s|d)?|"
    r"qualif(?:y|ies|ied)|appl(?:y|ies|ied)|limit(?:s|ed)?|"
    r"help(?:s|ed)?|regulate(?:s|d)?|"
    # Malay fact/relation cues so a Bahasa Melayu external claim is held to
    # the same citation requirement as its English equivalent. Over-matching
    # only sends more educational statements to the verifier (fail-safe); the
    # casual route is never validated, so common modals here are acceptable.
    r"adalah|ialah|melindungi|dilindungi|meliputi|merangkumi|termasuk|"
    r"memerlukan|perlu|mesti|wajib|membenarkan|dibenarkan|boleh|"
    r"menyediakan|memberikan|memberi|bermaksud|bererti|bermakna|"
    r"layak|automatik|percuma|menjamin|terjamin|dijamin|"
    r"mengecualikan|dikecualikan|terhad|membantu|dikawal\s+selia|"
    r"mengawal\s+selia|terpakai|menawarkan|mengenakan)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-zA-Z][a-zA-Z'-]{2,}")
_NEGATION = re.compile(
    r"\b(?:not|no|never|without|neither|nor|"
    # Malay negations keep polarity checks honest for Bahasa Melayu claims.
    r"tidak|bukan|tiada|tanpa|jangan|belum)\b",
    re.IGNORECASE,
)
_PASSAGE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")
_SUPPORT_STOP_WORDS = frozenset({
    "about", "action", "advice", "and", "before", "check", "current",
    "educational", "fincoach", "for", "from", "guidance", "insight", "into",
    "official", "recommended", "source", "that", "the", "this", "with",
    "are", "does", "from", "have", "is", "may", "was", "were", "will",
    "can", "through", "you",
})
_SUPPORT_TOKEN_ALIASES = {
    "contribution": "contribute",
    "voluntarily": "voluntary",
}


@dataclass(frozen=True)
class GroundingValidation:
    is_valid: bool
    errors: tuple[str, ...] = ()
    hard_errors: tuple[str, ...] = ()
    uncertain_claims: tuple["GroundingClaim", ...] = ()


@dataclass(frozen=True)
class GroundingClaim:
    """A cited factual statement whose lexical evidence match is uncertain."""

    id: int
    text: str
    cited_indices: tuple[int, ...]
    requires_citation: bool = False


def _line_references(line: str) -> tuple[int, ...]:
    return tuple(int(item) for item in _SOURCE_MARKER.findall(line))


def _numeric_values(text: str) -> set[str]:
    values: set[str] = set()
    for item in _NUMERIC_CLAIM.findall(text):
        raw = item.casefold().replace(",", "").replace("\u2212", "-").strip()
        unit = "number"
        if raw.startswith("rm"):
            unit = "rm"
            raw = raw[2:].strip()
        elif raw.endswith("percent"):
            unit = "percent"
            raw = raw.removesuffix("percent").strip()
        elif raw.endswith("%"):
            unit = "percent"
            raw = raw.removesuffix("%").strip()
        else:
            match = re.search(r"(days?|months?|years?|hari|bulan|tahun)$", raw)
            if match:
                unit = {
                    "day": "days", "days": "days", "hari": "days",
                    "month": "months", "months": "months", "bulan": "months",
                    "year": "years", "years": "years", "tahun": "years",
                }[match.group(1)]
                raw = raw[:match.start()].strip()
        try:
            number = Decimal(raw)
        except InvalidOperation:
            continue
        canonical = format(number if number else Decimal("0"), "f")
        if "." in canonical:
            canonical = canonical.rstrip("0").rstrip(".")
        values.add(f"{unit}:{canonical}")
    return values


def _example_amount_values(text: str) -> set[str]:
    """Canonical numeric values explicitly labeled as illustrative examples.

    A value qualifies only when an example cue ("for example", "e.g.", "contoh",
    ...) appears just before it within the same sentence. This keeps a clearly
    hypothetical amount from being rejected as an unsupported factual claim,
    while an unlabeled number is still held to the supplied evidence.
    """
    values: set[str] = set()
    source = str(text or "")
    for match in _NUMERIC_CLAIM.finditer(source):
        window = source[max(0, match.start() - _EXAMPLE_WINDOW):match.start()]
        cues = list(_EXAMPLE_CUE.finditer(window))
        if not cues:
            continue
        tail = window[cues[-1].end():]
        if not _EXAMPLE_SENTENCE_BOUNDARY.search(tail):
            values.update(_numeric_values(match.group(0)))
    return values


def _verify_calculation_claims(content: str, evidence_values: set[str]) -> set[str]:
    """Allow exact addition/subtraction of verified MYR inputs, with units intact.

    The numeric guard uses canonical strings such as ``rm:1200``, not Decimals.
    Parse only the displayed operators; never guess a different operation that
    happens to produce the model's answer, and never evaluate model-written code.
    """
    verified_derived: set[str] = set()
    for match in _CALCULATION_BLOCK.finditer(content):
        expression = match.group(1).replace("**", "").strip()
        left, separator, right = expression.partition("=")
        operands = list(_CURRENCY_AMOUNT.finditer(left))
        result_match = _CURRENCY_AMOUNT.match(right.strip())
        if not separator or "=" in right or not operands or not result_match:
            continue
        if left[:operands[0].start()].strip() or left[operands[-1].end():].strip():
            continue
        if _CURRENCY_AMOUNT.search(right.strip()[result_match.end():]):
            continue
        operators = [left[a.end():b.start()].strip() for a, b in zip(operands, operands[1:])]
        if any(operator not in {"+", "-", "\u2212"} for operator in operators):
            continue
        if not all(_numeric_values(f"RM{operand.group('amount')}").issubset(evidence_values)
                   for operand in operands):
            continue
        amounts = [Decimal(operand.group("amount").replace(",", "").replace("\u2212", "-"))
                   for operand in operands]
        computed = amounts[0]
        for operator, amount in zip(operators, amounts[1:]):
            computed += amount if operator == "+" else -amount
        result_value = Decimal(result_match.group("amount").replace(",", "").replace("\u2212", "-"))
        if computed == result_value:
            verified_derived.update(_numeric_values(f"RM{result_match.group('amount')}"))
    return verified_derived


def normalise_and_validate_numeric_claims(content: str, evidence: str) -> str | None:
    """Allow only numbers supported by this turn's prompt, sources, or tool data.

    A provider is never evidence for a financial amount. Dollar labels are repaired
    only when the exact amount is verified as Malaysian Ringgit in trusted evidence.
    """
    evidence_values = _numeric_values(evidence)
    calculation_derived = _verify_calculation_claims(content, evidence_values)
    evidence_values = evidence_values | calculation_derived

    def replace_currency(match: re.Match[str]) -> str:
        if match.group("currency") != "$":
            return match.group(0)
        canonical_value = _numeric_values(f"RM{match.group('amount')}")
        if canonical_value.intersection(evidence_values):
            return f"RM{match.group('amount')}"
        return ""

    normalised = _CURRENCY_AMOUNT.sub(replace_currency, str(content or ""))
    # A blank replacement means the provider emitted an unsupported dollar amount.
    if normalised != str(content or "") and "$" in str(content or "") and "$" in normalised:
        return None
    if "$" in str(content or "") and "$" not in normalised and not normalised:
        return None
    if "$" in str(content or "") and not all(
        _numeric_values(f"RM{match.group('amount')}").intersection(evidence_values)
        for match in _CURRENCY_AMOUNT.finditer(str(content or ""))
        if match.group("currency") == "$"
    ):
        return None
    for match in _NUMERIC_CLAIM.finditer(normalised):
        claim_values = _numeric_values(match.group(0))
        if claim_values.intersection(evidence_values):
            continue
        # An example exemption belongs to this occurrence, never every later
        # occurrence of the same number in the answer.
        prefix = normalised[max(0, match.start() - _EXAMPLE_WINDOW):match.start()]
        cues = list(_EXAMPLE_CUE.finditer(prefix))
        if cues and not _EXAMPLE_SENTENCE_BOUNDARY.search(prefix[cues[-1].end():]):
            continue
        return None
    return normalised


def recorded_money_claims_match_tools(content: str, tool_records: tuple | list) -> bool:
    """Conservative field-aware backstop for provider-written recorded claims.

    This is not a semantic proof engine: ambiguous claims fail closed. A value
    occurring in a different financial field is not supporting evidence.
    """
    fields: dict[str, set[str]] = {}

    def collect(value):
        if isinstance(value, dict):
            if value.get("status") not in (None, "ok"):
                return
            for key, item in value.items():
                if isinstance(item, str) and item.upper().startswith("RM"):
                    fields.setdefault(key, set()).update(_numeric_values(item))
                elif isinstance(item, (dict, list)):
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for entry in tool_records:
        if isinstance(entry, dict) and isinstance(entry.get("result"), dict) and entry["result"].get("status") == "ok":
            collect(entry["result"])
    # Split on sentence boundaries, not decimal points.
    for sentence in re.split(r"(?<=[.!?])\s+|\n", content.replace("**", "")):
        if not _CURRENCY_AMOUNT.search(sentence):
            continue
        if _EXAMPLE_CUE.search(sentence) and not re.search(r"\b(?:recorded|verified|your|my|anda|rekod)\b", sentence, re.I):
            continue
        cues = [
            (r"\b(?:remaining|left|baki)\b", ("remaining", "projected_remaining")),
            (r"\b(?:allowance|elaun)\b", ("monthly_allowance",)),
            (r"\b(?:spent|spending|expenses?|belanja|perbelanjaan)\b", ("expense_total", "recorded_spending", "recorded_expenses", "spent", "amount", "projected_month_spending")),
            (r"\b(?:limit|had)\b", ("monthly_limit", "limit")),
            (r"\b(?:income|pendapatan)\b", ("income", "monthly_allowance")),
            (r"\b(?:target)\b", ("target_amount",)),
            (r"\b(?:saved|savings|save|saveable|simpan)\b", ("current_amount", "projected_saveable", "projected_remaining")),
            (r"\b(?:projected|estimated|predicted|forecast|anggaran)\b", ("projected_remaining", "projected_saveable", "projected_month_spending", "estimated_available_by_month_end")),
            (r"\b(?:daily|per\s+day|sehari)\b", ("daily_spending_rate",)),
        ]
        matching = [(pattern, keys) for pattern, keys in cues if re.search(pattern, sentence, re.I)]
        if len(matching) == 1:
            allowed = set().union(*(fields.get(key, set()) for key in matching[0][1]))
            if not _numeric_values(" ".join(m.group(0) for m in _CURRENCY_AMOUNT.finditer(sentence))).issubset(allowed):
                return False
        elif not matching and re.search(r"\b(?:recorded|verified|your|anda|rekod)\b", sentence, re.I):
            # No reliable field binding: do not accept a recorded claim merely
            # because its amount occurs in an unrelated tool field.
            return False
        elif len(matching) > 1:
            # Multiple fields in one sentence are difficult to bind reliably.
            # Validate each amount against its nearest preceding field cue.
            for amount in _CURRENCY_AMOUNT.finditer(sentence):
                preceding = []
                for pattern, keys in matching:
                    for cue in re.finditer(pattern, sentence[:amount.start()], re.I):
                        preceding.append((cue.end(), keys))
                if not preceding:
                    return False
                keys = max(preceding, key=lambda item: item[0])[1]
                allowed = set().union(*(fields.get(key, set()) for key in keys))
                if not _numeric_values(amount.group(0)).issubset(allowed):
                    return False
    return True


def _support_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for word in _WORD.findall(_SOURCE_MARKER.sub("", text)):
        raw = word.casefold()
        normalised = _normalise_word(raw)
        if raw not in _SUPPORT_STOP_WORDS and normalised not in _SUPPORT_STOP_WORDS:
            tokens.add(normalised)
    return tokens


def _normalise_word(word: str) -> str:
    """Keep simple inflections from making evidence appear unrelated."""
    token = word.casefold().removesuffix("'s").removesuffix("â€™s")
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        token = token[:-1]
    return _SUPPORT_TOKEN_ALIASES.get(token, token)


def _citation_supports_claim(line: str, source_texts: list[str]) -> bool:
    """Check a claim against cited evidence while preserving negation polarity."""
    claim_tokens = _support_tokens(line)
    if not claim_tokens:
        return True
    claim_is_negative = bool(_NEGATION.search(line))
    evidence_tokens: set[str] = set()
    for source_text in source_texts:
        for passage in _PASSAGE_BOUNDARY.split(source_text):
            if claim_is_negative == bool(_NEGATION.search(passage)):
                evidence_tokens.update(_support_tokens(passage))
    matched = claim_tokens.intersection(evidence_tokens)
    return len(matched) >= ceil(len(claim_tokens) * 0.8)


def _has_same_negation_polarity(line: str, source_texts: list[str]) -> bool:
    """Return whether a cited passage can support the claim's polarity."""
    claim_is_negative = bool(_NEGATION.search(line))
    return any(
        claim_is_negative == bool(_NEGATION.search(passage))
        for source_text in source_texts
        for passage in _PASSAGE_BOUNDARY.split(source_text)
        if passage.strip()
    )


def attach_verified_citations(
    content: str,
    claims: list[GroundingClaim],
) -> str | None:
    """Attach verified source markers to uniquely located uncited statements."""
    repaired = content
    for claim in claims:
        if not claim.requires_citation or len(claim.cited_indices) != 1:
            return None
        if repaired.count(claim.text) != 1:
            return None
        marker = f"[S{claim.cited_indices[0]}]"
        if claim.text.endswith((".", "!", "?")):
            replacement = f"{claim.text[:-1]} {marker}{claim.text[-1]}"
        else:
            replacement = f"{claim.text} {marker}"
        repaired = repaired.replace(claim.text, replacement, 1)
    return repaired


def validate_coach_answer(
    content: str,
    reference_contents: list[str],
    verified_context: str,
    *,
    allow_uncited_numbers: bool = False,
    require_source_for_facts: bool = True,
) -> GroundingValidation:
    """Validate format and prevent unsupported financial claims from shipping."""
    text = str(content or "").strip()
    hard_errors: list[str] = []
    uncertain_claims: list[GroundingClaim] = []
    example_values = _example_amount_values(text)
    headings = tuple(match.strip() for match in _HEADING.findall(text))
    if headings != REQUIRED_HEADINGS:
        hard_errors.append("response must use exactly the required Coach headings")
    if not text.endswith(DISCLAIMER):
        hard_errors.append("response must end with the exact educational disclaimer")

    for marker in _SOURCE_MARKER.findall(text):
        source_index = int(marker)
        if source_index < 1 or source_index > len(reference_contents):
            hard_errors.append(f"citation [S{source_index}] does not exist")

    if _SPECIFIC_PRODUCT_RECOMMENDATION.search(text):
        hard_errors.append("specific product recommendation is not allowed")

    section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        heading_match = _HEADING.fullmatch(line)
        if heading_match:
            section = heading_match.group(1).strip()
            continue
        if line == DISCLAIMER:
            continue
        line_cited_indices = _line_references(line)
        for statement in _PASSAGE_BOUNDARY.split(line):
            statement = statement.strip()
            if not statement:
                continue
            statement_cited_indices = _line_references(statement)
            cited_indices = statement_cited_indices or line_cited_indices
            source_texts = [
                reference_contents[index - 1]
                for index in cited_indices
                if 1 <= index <= len(reference_contents)
            ]
            statement_numeric_values = _numeric_values(statement)
            has_verified_context_number = bool(
                statement_numeric_values.intersection(_numeric_values(verified_context))
            )
            if (
                require_source_for_facts
                and _EXTERNAL_FACT_CUE.search(statement)
                and not cited_indices
                and not has_verified_context_number
            ):
                candidate_indices = tuple(range(1, len(reference_contents) + 1))
                if candidate_indices:
                    uncertain_claims.append(
                        GroundingClaim(
                            id=len(uncertain_claims) + 1,
                            text=statement,
                            cited_indices=candidate_indices,
                            requires_citation=True,
                        )
                    )
                else:
                    hard_errors.append("external financial fact requires a source marker")
            citation_needs_textual_support = section == "Insight" and (
                bool(statement_cited_indices) or (
                    bool(line_cited_indices) and not has_verified_context_number
                )
            ) or bool(
                statement_numeric_values
                and cited_indices
                and not has_verified_context_number
            )
            if citation_needs_textual_support and not _citation_supports_claim(
                statement, source_texts
            ):
                if source_texts and not _has_same_negation_polarity(
                    statement, source_texts
                ):
                    hard_errors.append("cited source has opposite negation polarity")
                else:
                    uncertain_claims.append(
                        GroundingClaim(
                            id=len(uncertain_claims) + 1,
                            text=statement,
                            cited_indices=tuple(dict.fromkeys(cited_indices)),
                        )
                    )
            for claim in _NUMERIC_CLAIM.findall(statement):
                claim_values = _numeric_values(claim)
                supported_by_reference = any(
                    bool(claim_values.intersection(_numeric_values(source)))
                    for source in source_texts
                )
                supported_by_context = bool(
                    claim_values.intersection(_numeric_values(verified_context))
                )
                is_labeled_example = bool(claim_values) and claim_values.issubset(
                    example_values
                )
                if supported_by_reference or supported_by_context or is_labeled_example:
                    continue
                if allow_uncited_numbers and not cited_indices:
                    continue
                hard_errors.append(f"unsupported numeric claim: {claim}")

    support_errors = tuple(
        "external financial fact requires a source marker"
        if claim.requires_citation
        else "cited source does not support the financial claim"
        for claim in uncertain_claims
    )
    errors = tuple(hard_errors) + support_errors
    return GroundingValidation(
        not errors,
        errors,
        tuple(hard_errors),
        tuple(uncertain_claims),
    )


def grounding_retry_prompt(prompt: str, content: str, errors: tuple[str, ...]) -> str:
    """Ask for one corrected answer without granting the provider new evidence."""
    issue_list = "\n".join(f"- {error}" for error in errors)
    return f"""{prompt}

<draft_answer_to_correct>
{content}
</draft_answer_to_correct>

<validation_errors>
{issue_list}
</validation_errors>

Rewrite the draft using only the supplied evidence. Do not add facts. Return only
the three required Coach sections and the exact educational disclaimer. Write one cited
fact per sentence using source wording closely, and keep practical advice separate."""


def safe_grounding_fallback(*, has_sources: bool = True) -> str:
    insight = (
        "FinCoach found relevant official sources, but it could not safely "
        "validate the generated wording."
        if has_sources
        else "FinCoach could not find an official source it could safely cite "
        "for this question."
    )
    return f"""**Insight**
{insight}
**Recommended action**
Check the relevant institution's current official website before acting.
**Educational guidance**
{DISCLAIMER}"""


def contains_specific_product_recommendation(content: str) -> bool:
    """Report whether an answer pushes the user toward a specific product.

    Route-independent backstop: the education validator already blocks this, but
    casual, personal, and agent replies are not validated, so this lets the
    orchestrator scrub a leaked "open/use/buy this account/app/fund" from any
    route before it ships.
    """
    return bool(_SPECIFIC_PRODUCT_RECOMMENDATION.search(str(content or "")))


def safe_product_redirect() -> str:
    """A neutral, route-independent reply for product-selection requests.

    FinCoach explains how products work but never recommends or ranks a specific
    provider; this canned answer ships without calling a provider.
    """
    return f"""**Insight**
FinCoach explains how financial products work but does not recommend or rank a specific provider, bank, e-wallet, app, card, fund, insurance product, or investment.
**Recommended action**
Compare the official options yourself: check Bank Negara Malaysia's authorised lists and each provider's current published terms before deciding.
**Educational guidance**
{DISCLAIMER}"""
