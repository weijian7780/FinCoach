"""Fair discovery scheduler for requested public research parts."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from app.config import (
    COACH_RESEARCH_MAX_SEARCH_CALLS,
    COACH_RESEARCH_MAX_EXTRACT_CALLS,
    COACH_RESEARCH_MAX_ASSESSMENT_CALLS,
    COACH_RESEARCH_MAX_UNIQUE_URLS,
    COACH_RESEARCH_MAX_PART_VARIANTS,
)
from app.rag.research_coverage import (
    RequestedPart,
    clarification_part_ids,
)

if TYPE_CHECKING:
    from app.rag.research_policy import QuestionPlan, EvidenceAssessment
    from app.rag.retrieval import RetrievedChunk


@dataclass(frozen=True)
class ResearchPartState:
    part_id: str
    status: Literal["open", "satisfied", "clarify", "exhausted"]
    search_attempts: int = 0
    inspected_hashes: tuple[str, ...] = ()
    terminal_reason: str | None = None


def select_discovery_part(states: tuple[ResearchPartState, ...]) -> str | None:
    """Select the next open part for discovery.

    Every open part gets one discovery opportunity before any second variant.
    Among parts with equal attempts, least-attempted parts take priority.
    """
    open_states = [s for s in states if s.status == "open" and s.search_attempts < COACH_RESEARCH_MAX_PART_VARIANTS]
    if not open_states:
        return None
    # Give every open part its first discovery opportunity (0 attempts) first:
    zero_attempts = [s for s in open_states if s.search_attempts == 0]
    if zero_attempts:
        return zero_attempts[0].part_id
    # Otherwise pick the least attempted:
    return min(open_states, key=lambda s: s.search_attempts).part_id


def query_variants(plan: QuestionPlan, part: RequestedPart) -> tuple[str, ...]:
    """Generate at most two query variants for an open requested part."""
    from app.rag.research_policy import part_research_query
    from app.rag.web_research import build_research_query

    # Variant 1: Official focused query
    v1 = part_research_query(plan, part)

    # Variant 2: Alternative vocabulary / synonym formulation
    entity_str = part.entity or (plan.entities[0] if plan.entities else "") or plan.topic
    prog_str = part.programme or plan.application_subject or ""
    period_str = plan.period or ""

    if plan.jurisdiction.casefold() == "malaysia":
        if part.kind == "documents":
            v2_raw = f"{entity_str} {prog_str} dokumen sokongan permohonan rasmi {period_str} Malaysia"
        elif part.kind == "application":
            v2_raw = f"{entity_str} {prog_str} cara memohon borang permohonan online rasmi {period_str} Malaysia"
        elif part.kind == "eligibility":
            v2_raw = f"{entity_str} {prog_str} syarat kelayakan permohonan {period_str} Malaysia"
        elif part.kind == "duties":
            v2_raw = f"{entity_str} fungsi peranan tugas rasmi {period_str} Malaysia"
        elif part.kind == "identity":
            v2_raw = f"{entity_str} profil nama penuh fungsi rasmi {period_str} Malaysia"
        else:
            v2_raw = f"{part.label} {entity_str} {prog_str} panduan rasmi {period_str} Malaysia"
    else:
        v2_raw = f"{entity_str} {prog_str} {part.label} official guidance {period_str} {plan.jurisdiction}"

    v2 = build_research_query(v2_raw)
    variants = [v1]
    if v2 and v2 != v1:
        variants.append(v2)
    return tuple(variants[:COACH_RESEARCH_MAX_PART_VARIANTS])


class ResearchScheduler:
    """Request-local fair discovery scheduler managing quotas and part states."""

    def __init__(
        self,
        plan: QuestionPlan,
        parts: tuple[RequestedPart, ...],
        *,
        max_search_calls: int = COACH_RESEARCH_MAX_SEARCH_CALLS,
        max_extract_calls: int = COACH_RESEARCH_MAX_EXTRACT_CALLS,
        max_assessment_calls: int = COACH_RESEARCH_MAX_ASSESSMENT_CALLS,
        max_unique_urls: int = COACH_RESEARCH_MAX_UNIQUE_URLS,
        max_part_variants: int = COACH_RESEARCH_MAX_PART_VARIANTS,
    ):
        self.plan = plan
        self.parts = parts
        self.max_search_calls = max_search_calls
        self.max_extract_calls = max_extract_calls
        self.max_assessment_calls = max_assessment_calls
        self.max_unique_urls = max_unique_urls
        self.max_part_variants = max_part_variants

        blocked = set(clarification_part_ids(plan))
        self.states: dict[str, ResearchPartState] = {
            p.id: ResearchPartState(
                part_id=p.id,
                status="clarify" if p.id in blocked else "open",
                search_attempts=0,
                inspected_hashes=(),
                terminal_reason=None,
            )
            for p in parts
        }
        self.searched_queries: set[tuple[str, str]] = set()
        self.assessed_evidence_hashes: set[str] = set()
        self.unique_urls: set[str] = set()
        self.terminal_reason: str | None = None

    def get_states(self) -> tuple[ResearchPartState, ...]:
        return tuple(self.states.values())

    def select_part(self) -> str | None:
        return select_discovery_part(self.get_states())

    def record_search_attempt(self, part_id: str, query: str, mode: str = "institution") -> None:
        if part_id in self.states:
            st = self.states[part_id]
            attempts = st.search_attempts + 1
            status = st.status
            terminal = st.terminal_reason
            if attempts >= self.max_part_variants and status == "open":
                # Marked exhausted only after all variants have been attempted without success
                status = "exhausted"
                terminal = terminal or "variants_exhausted"
            self.states[part_id] = replace(
                st,
                search_attempts=attempts,
                status=status,
                terminal_reason=terminal,
            )
        self.searched_queries.add((query, mode))

    def record_inspected_hash(self, part_id: str, content_hash: str) -> None:
        if part_id in self.states:
            st = self.states[part_id]
            if content_hash not in st.inspected_hashes:
                self.states[part_id] = replace(
                    st,
                    inspected_hashes=(*st.inspected_hashes, content_hash),
                )

    def record_stop(self, reason: str) -> None:
        """On global limit/deadline, record terminal reason on open parts without erasing them."""
        self.terminal_reason = reason
        for pid, st in self.states.items():
            if st.status == "open":
                self.states[pid] = replace(st, terminal_reason=reason)

    def update_from_assessment(self, assessed: EvidenceAssessment) -> None:
        for part in assessed.parts:
            if part.part_id in self.states:
                st = self.states[part.part_id]
                if part.complete:
                    self.states[part.part_id] = replace(st, status="satisfied", terminal_reason=None)
        if assessed.failure in {"no_api_key", "sdk_unavailable", "auth_error", "quota"}:
            for pid, st in self.states.items():
                if st.status == "open":
                    self.states[pid] = replace(st, status="exhausted", terminal_reason=assessed.failure)

    def is_complete(self) -> bool:
        return all(s.status in {"satisfied", "clarify", "exhausted"} for s in self.states.values())

    @staticmethod
    def evidence_signature(chunks: list[RetrievedChunk]) -> str:
        items = [f"{c.url or ''}:{c.evidence_window_id or hashlib.sha256(c.content.encode()).hexdigest()}" for c in chunks]
        return hashlib.sha256("|".join(sorted(items)).encode()).hexdigest()

    def has_assessed_evidence(self, chunks: list[RetrievedChunk]) -> bool:
        sig = self.evidence_signature(chunks)
        return sig in self.assessed_evidence_hashes

    def note_assessed_evidence(self, chunks: list[RetrievedChunk]) -> None:
        sig = self.evidence_signature(chunks)
        self.assessed_evidence_hashes.add(sig)
