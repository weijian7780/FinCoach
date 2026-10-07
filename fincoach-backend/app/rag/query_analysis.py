"""Deterministic topic analysis for FinCoach knowledge retrieval.

This module intentionally performs no provider call.  It recognises the small,
curated Malaysian-finance corpus before routing or retrieval so acronym typos
and multi-topic questions do not depend on one dense query vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


_WORD = re.compile(r"[a-z0-9]+")
_FOLLOW_UP = re.compile(
    r"^(?:(?:what|how)\s+about|and|also|then|for\s+(?:that|it)|that)\b",
    re.IGNORECASE,
)
_FUZZY_THRESHOLD = 0.80
_FUZZY_MARGIN = 0.08
_MAX_TOPICS = 3


@dataclass(frozen=True)
class KnowledgeTopic:
    """One official whole-document topic in the curated corpus."""

    topic_id: str
    source: str
    canonical_terms: tuple[str, ...]
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class TopicMatch:
    topic: KnowledgeTopic
    confidence: float
    matched_alias: str
    fuzzy: bool = False
    position: int = 0


@dataclass(frozen=True)
class SearchSubquery:
    """A topic-specific retrieval query with its required corpus source."""

    topic_id: str | None
    source: str | None
    text: str


@dataclass(frozen=True)
class KnowledgeQueryAnalysis:
    original: str
    normalized: str
    topic_matches: tuple[TopicMatch, ...]
    subqueries: tuple[SearchSubquery, ...]
    inherited: bool = False
    clarification: str | None = None

    @property
    def has_knowledge_intent(self) -> bool:
        return bool(self.topic_matches)


KNOWLEDGE_TOPICS: tuple[KnowledgeTopic, ...] = (
    KnowledgeTopic(
        "akpk",
        "official_akpk_debt_help_and_financial_education.md",
        ("AKPK", "debt management", "credit counselling"),
        ("akpk", "credit counselling", "debt counselling"),
    ),
    KnowledgeTopic(
        "bnpl",
        "official_bnpl_and_responsible_credit.md",
        ("BNPL", "buy now pay later", "responsible credit"),
        ("bnpl", "buy now pay later", "beli sekarang bayar kemudian"),
    ),
    KnowledgeTopic(
        "compound_interest",
        "official_compound_interest_and_savings_growth.md",
        ("compound interest", "compounding", "faedah kompaun"),
        (
            "compound interest",
            "compounding",
            "compounded",
            "compound",
            "faedah kompaun",
            "faedah berganda",
            "kompaun",
        ),
    ),
    KnowledgeTopic(
        "emergency_fund",
        "official_budgeting_and_emergency_fund.md",
        ("emergency fund", "dana kecemasan", "budgeting"),
        ("emergency fund", "dana kecemasan", "simpanan kecemasan"),
    ),
    KnowledgeTopic(
        "credit_records",
        "official_credit_records_and_eccris.md",
        ("CCRIS", "eCCRIS", "credit record"),
        ("ccris", "eccris", "credit record", "credit report"),
    ),
    KnowledgeTopic(
        "digital_assets",
        "official_digital_assets_and_crypto.md",
        ("digital assets", "crypto", "kripto"),
        ("crypto", "cryptocurrency", "kripto", "digital assets"),
    ),
    KnowledgeTopic(
        "digital_banks",
        "official_digital_banks_and_ewallets.md",
        ("digital bank", "e-wallet", "e-dompet"),
        ("digital bank", "ewallet", "e wallet", "e-dompet", "edomet"),
    ),
    KnowledgeTopic(
        "epf",
        "official_epf_for_students_and_new_workers.md",
        ("EPF", "KWSP", "Employees Provident Fund"),
        ("epf", "kwsp", "employees provident fund", "provident fund"),
    ),
    KnowledgeTopic(
        "financial_complaints",
        "official_financial_service_complaints.md",
        ("financial service complaint", "aduan perkhidmatan kewangan"),
        ("financial service complaint", "bank complaint", "aduan perkhidmatan kewangan"),
    ),
    KnowledgeTopic(
        "perkeso",
        "official_perkeso_employee_protection.md",
        ("PERKESO", "SOCSO", "Social Security Organisation"),
        ("perkeso", "socso", "social security organisation"),
    ),
    KnowledgeTopic(
        "pidm",
        "official_pidm_deposit_protection.md",
        ("PIDM", "deposit protection"),
        ("pidm", "deposit protection", "perlindungan deposit"),
    ),
    KnowledgeTopic(
        "ptptn",
        "official_ptptn_loan_guidance.md",
        ("PTPTN", "education loan", "student loan"),
        ("ptptn", "education loan", "study loan", "student loan"),
    ),
    KnowledgeTopic(
        "scams",
        "official_scam_and_investment_safety.md",
        ("investment scam", "financial scam", "penipuan"),
        ("investment scam", "financial scam", "penipuan pelaburan"),
    ),
    KnowledgeTopic(
        "shariah",
        "official_shariah_compliant_investing.md",
        ("Shariah-compliant investing", "patuh Syariah"),
        ("shariah compliant", "patuh syariah", "syariah"),
    ),
    KnowledgeTopic(
        "student_aid",
        "official_student_financial_aid_and_scholarships.md",
        ("student financial aid", "scholarship", "biasiswa"),
        ("financial aid", "student aid", "scholarship", "scholarships", "biasiswa"),
    ),
    KnowledgeTopic(
        "takaful",
        "official_takaful_and_insurance_protection.md",
        ("takaful", "insurance protection", "insurans"),
        ("takaful", "insurance protection", "insurans"),
    ),
    KnowledgeTopic(
        "tax",
        "official_tax_for_part_time_and_side_income.md",
        ("tax", "part-time income", "side income", "cukai"),
        ("part time tax", "side income tax", "cukai pendapatan"),
    ),
)


def normalise_knowledge_text(text: str) -> str:
    """Return a conservative form suitable for alias matching."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_WORD.findall(without_marks.casefold()))


def detect_knowledge_topics(text: str) -> tuple[TopicMatch, ...]:
    """Detect exact aliases first, then only high-confidence unique typos."""
    normalized = normalise_knowledge_text(text)
    if not normalized:
        return ()
    padded = f" {normalized} "
    matches: dict[str, TopicMatch] = {}
    for topic in KNOWLEDGE_TOPICS:
        for alias in topic.aliases:
            normalized_alias = normalise_knowledge_text(alias)
            if normalized_alias and f" {normalized_alias} " in padded:
                matches[topic.topic_id] = TopicMatch(
                    topic,
                    1.0,
                    alias,
                    position=padded.index(f" {normalized_alias} "),
                )
                break

    for token_match in _WORD.finditer(normalized):
        token = token_match.group(0)
        if len(token) < 4:
            continue
        candidate_matches: list[tuple[float, KnowledgeTopic, str]] = []
        for topic in KNOWLEDGE_TOPICS:
            if topic.topic_id in matches:
                continue
            for alias in topic.aliases:
                normalized_alias = normalise_knowledge_text(alias)
                if " " in normalized_alias or len(normalized_alias) < 4:
                    continue
                score = SequenceMatcher(a=token, b=normalized_alias).ratio()
                candidate_matches.append((score, topic, alias))
        candidate_matches.sort(key=lambda item: item[0], reverse=True)
        if not candidate_matches:
            continue
        best_score, topic, alias = candidate_matches[0]
        second_score = candidate_matches[1][0] if len(candidate_matches) > 1 else 0.0
        if best_score >= _FUZZY_THRESHOLD and best_score - second_score >= _FUZZY_MARGIN:
            matches[topic.topic_id] = TopicMatch(
                topic,
                best_score,
                alias,
                fuzzy=True,
                position=token_match.start(),
            )

    return tuple(sorted(matches.values(), key=lambda match: match.position))


def analyze_knowledge_query(
    content: str,
    *,
    history: list[dict] | None = None,
    current_message_id: str | None = None,
    max_topics: int = _MAX_TOPICS,
) -> KnowledgeQueryAnalysis:
    """Create bounded, topic-specific retrieval work without an LLM call."""
    original = " ".join(str(content or "").strip().split())
    normalized = normalise_knowledge_text(original)
    matches = detect_knowledge_topics(original)
    inherited = False
    clarification: str | None = None

    if not matches and _is_follow_up(original):
        previous_topics = _previous_user_topics(history or [], current_message_id)
        if len(previous_topics) == 1:
            matches = previous_topics
            inherited = True
        elif len(previous_topics) > 1:
            clarification = "Which topic do you mean? Please name one financial topic."

    if len(matches) > max_topics:
        clarification = "Please ask about up to three financial topics at a time."
        subqueries: tuple[SearchSubquery, ...] = ()
    elif clarification:
        subqueries = ()
    elif matches:
        subqueries = tuple(
            SearchSubquery(
                topic_id=match.topic.topic_id,
                source=match.topic.source,
                text=" ".join(match.topic.canonical_terms),
            )
            for match in matches
        )
    else:
        subqueries = (SearchSubquery(None, None, original),) if original else ()

    return KnowledgeQueryAnalysis(
        original=original,
        normalized=normalized,
        topic_matches=matches,
        subqueries=subqueries,
        inherited=inherited,
        clarification=clarification,
    )


def _previous_user_topics(history: list[dict], current_message_id: str | None) -> tuple[TopicMatch, ...]:
    for message in reversed(history):
        if message.get("role") != "user" or (
            current_message_id and message.get("id") == current_message_id
        ):
            continue
        matches = detect_knowledge_topics(str(message.get("content") or ""))
        if matches:
            return matches
    return ()


def _is_follow_up(content: str) -> bool:
    return bool(_FOLLOW_UP.search(" ".join(str(content or "").strip().split())))
