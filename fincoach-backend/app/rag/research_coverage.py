"""Request-local scope shared by research and explanation verification.

These rows describe coverage, not facts. Positive facts always retain their
literal source quotation and undergo the independent grounding verifier.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.rag.research_policy import QuestionPlan


@dataclass(frozen=True)
class RequestedPart:
    id: str
    label: str
    kind: str = "general"
    entity: str | None = None
    programme: str | None = None
    official_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class PartCoverage:
    part_id: str
    status: Literal["confirmed", "reported", "missing", "conflicting"]
    # One-based indices into EvidenceAssessment.supported_quotes, NOT chunks.
    support_indices: tuple[int, ...] = ()
    resolution: Literal["direct", "not_required"] = "direct"
    complete: bool = False


def requested_parts(plan: QuestionPlan) -> tuple[RequestedPart, ...]:
    import re
    from app.rag.web_research import build_research_query
    labels = []
    seen = set()
    for fact in plan.required_facts or (plan.topic,):
        label = build_research_query(str(fact))[:100].strip()
        key = " ".join(label.casefold().split())
        if label and key not in seen:
            seen.add(key)
            labels.append(label)
        if len(labels) == 6:
            break

    default_entity = plan.entities[0] if plan.entities else None
    if plan.entities and len(plan.entities) > 1 and plan.subject_kind == "agency":
        from app.rag.research_policy import _search_entities
        ents = _search_entities(plan)
        if ents:
            default_entity = ents[0]

    programme = plan.application_subject or None

    parts = []
    for i, label in enumerate(labels, 1):
        if re.search(r"\b(?:document|documents|documentation|dokumen|sokongan)\b", label, re.I):
            kind = "documents"
        elif re.search(r"\b(?:apply|applying|application|permohonan|memohon|process|steps|kaedah|cara)\b", label, re.I):
            kind = "application"
        elif re.search(r"\b(?:eligib\w*|criteria|qualif\w*|syarat|kelayakan)\b", label, re.I):
            kind = "eligibility"
        elif re.search(r"\b(?:duties|roles?|functions?|purpose|peranan|fungsi|tugas)\b", label, re.I):
            kind = "duties"
        elif re.search(r"\b(?:identity|full name|nama penuh|profil)\b", label, re.I):
            kind = "identity"
        else:
            kind = "general"

        part_entity = default_entity
        if len(plan.entities) > 1:
            for ent in plan.entities:
                if ent.casefold() in label.casefold():
                    part_entity = ent
                    break

        parts.append(RequestedPart(
            id=f"p{i}",
            label=label,
            kind=kind,
            entity=part_entity,
            programme=programme,
            official_domains=(),
        ))
    return tuple(parts)


def select_unresolved_part(parts: tuple[PartCoverage, ...], attempts: dict[str, int]) -> str | None:
    unresolved = [part for part in parts if not part.complete]
    return min(unresolved, key=lambda part: attempts.get(part.part_id, 0)).part_id if unresolved else None


def researchable_parts(plan: QuestionPlan) -> tuple[RequestedPart, ...]:
    """Filter ambiguity without changing the original coverage identities."""
    if plan.clarification and not plan.clarification_facts:
        return ()  # Older proposals cannot identify a safe independent part.
    blocked = set(clarification_part_ids(plan))
    return tuple(part for part in requested_parts(plan) if part.id not in blocked)


def clarification_part_ids(plan: QuestionPlan) -> tuple[str, ...]:
    from app.rag.web_research import build_research_query
    # Use the same transformation as requested_parts. Raw labels may contain
    # identifiers removed by de-identification; comparison must not bypass it.
    labels = {build_research_query(fact)[:100].strip() for fact in plan.clarification_facts}
    return tuple(part.id for part in requested_parts(plan) if part.label in labels)


def clarification_question(plan: QuestionPlan) -> str | None:
    """Render an intent question, never unchecked provider-authored assertions."""
    import re
    if not plan.clarification:
        return None
    labels = " ".join(plan.clarification_facts or plan.required_facts)
    kind = ("application" if re.search(r"\b(?:apply|application|applying|permohonan|memohon)\b", labels, re.I)
            else "period" if re.search(r"\b(?:year|period|date|tahun|tempoh)\b", labels, re.I) else "subject")
    texts = {
        "en": {"application": "Which programme or service would you like to apply for?",
               "period": "Which year or period do you mean?",
               "subject": "Which subject do you mean for the remaining part of your question?"},
        "ms": {"application": "Program atau perkhidmatan mana yang anda ingin mohon?",
               "period": "Tahun atau tempoh mana yang anda maksudkan?",
               "subject": "Apakah perkara yang anda maksudkan untuk bahagian soalan yang selebihnya?"},
        "zh": {"application": "你想申请哪个计划或服务？", "period": "你指的是哪一年或哪个时期？",
               "subject": "你所问的其余部分具体指什么？"},
        "ta": {"application": "எந்தத் திட்டம் அல்லது சேவைக்கு விண்ணப்பிக்க விரும்புகிறீர்கள்?",
               "period": "எந்த ஆண்டு அல்லது காலத்தைக் குறிப்பிடுகிறீர்கள்?",
               "subject": "உங்கள் கேள்வியின் மீதிப் பகுதியில் எந்த விஷயத்தைக் குறிப்பிடுகிறீர்கள்?"},
    }
    return texts.get((plan.response_language or "en").split("-")[0], texts["en"])[kind]


def requires_full_clarification(plan: QuestionPlan) -> bool:
    return bool(plan.clarification and not researchable_parts(plan))
