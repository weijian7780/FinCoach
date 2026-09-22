# FinCoach Read Routing and Clarification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve financial intent while safely resolving parameters, and complete the clarification loop through saved state and existing Coach UI controls.

**Architecture:** Keep deterministic intent selection, parameter resolution, execution readiness, and answer formatting distinct. Extend the existing resolver and typed tools; save versioned read state through the existing message JSON payload. Deliver backend correctness first, then durable clarification and mobile chips.

**Tech Stack:** Existing Python/FastAPI/Pydantic/Supabase backend; React Native/Expo/TypeScript mobile; pytest and Vitest.

**Spec:** `fincoach-backend/docs/superpowers/specs/2026-09-22-read-routing-and-clarification.md` (repository-root-relative).

## Global Constraints

- Scope is the AI Financial Coaching module.
- Backend remains FastAPI/Python with real Supabase persistence and owner-scoped reads.
- Use Asia/Kuala_Lumpur for user-facing date semantics.
- Preserve spending consent, provider consent, numeric grounding, tool allowlists, and existing write-action policy.
- No additional model call or new provider dependency for parameter resolution.
- No Jev activation, provider migration, ranked-confidence router, or retrieval redesign in this change.
- No new financial-record write tool or automatic financial-record mutation.
- Preserve the existing FinCoach UI direction and use responsive, accessible controls.
- No deployment, schema migration, APK build, or device installation is part of writing this plan.

## Review Focus

- Malaysia month/year rollover and leap February must produce the requested comparison dates (Task 2).
- A known topic embedded in an educational follow-up must not trigger a personal read (Tasks 1 and 3).
- A pending clarification followed by a new topic, cancellation, or stale chip must not execute the previous request (Task 4).
- Consent withdrawn between clarification and reply must still block the eventual read (Task 4).
- Existing clients, failed messages, duplicate requests, and process restarts must not produce guessed state or duplicate side effects (Tasks 4 and 5).

## File ownership and execution conventions

All paths below are relative to the repository root unless a command explicitly runs inside a project directory.

| File | Responsibility |
|---|---|
| `fincoach-backend/app/rag/routing.py` | Intent detection, read contract, parameter policy, explicit/context/default resolution |
| `fincoach-backend/app/agent_tools.py` | Typed argument validation and owner-scoped comparison execution |
| `fincoach-backend/app/rag/read_clarification.py` (new) | Versioned pending-read serialization, validation, questions, and reply resolution |
| `fincoach-backend/app/rag/service.py` | Readiness gate, saved-state integration, existing verified result formatting |
| `fincoach-backend/app/coaching_history.py` | Existing owner-scoped message lookup, only extended if needed for eligibility checks |
| `fincoach-backend/app/rag/follow_ups.py` | Suppress normal next-step suggestions while clarification is pending |
| `fincoach-mobile/src/lib/types.ts`, `coach-agent.ts` | Read clarification payload type and runtime recognition |
| `fincoach-mobile/src/components/coach/coach-message.tsx`, `coach-interaction-card.tsx` | Reuse clarification controls for read questions |

Before implementation, inspect `git status --short` and preserve unrelated edits. Routing/service files changed concurrently while this plan was written; re-run the documented probes before editing and retain existing `get_period_comparison` support. Do not replace existing large routing/service files wholesale. Prefer the existing virtual environment. Unit tests may use the repository's controlled fakes; application code must continue using real Supabase. Local unit tests are not a live-backend claim.

Each task below ends with a scoped diff review and a commit containing only that task's files, when repository policy allows commits. Do not stage unrelated work. Tasks are sequential because later tasks use the earlier contracts.

## Task 1: Stop incorrect inheritance and clarification bypass

**Files:** Modify `fincoach-backend/app/rag/routing.py` and `fincoach-backend/app/rag/service.py`; test `fincoach-backend/tests/test_accuracy_routing.py` and `fincoach-backend/tests/test_rag_pipeline.py`.

**Interfaces:** Keep `resolve_read_request(content, history, *, current_message_id=None, now=None) -> ResolvedReadRequest` intact. Preserve existing direct-tool and argument functions. New behaviour returns clarification without a guessed tool for an ambiguous savings request or unresolved transaction reference.

- [ ] Add failing resolver regression tests, using the existing `AccuracyRoutingTests.resolve` helper. Include these exact assertions:

```python
def test_savings_topic_change_does_not_inherit_food_spending(self):
    result = self.resolve("What about my savings?", [
        {"role": "user", "content": "Show my spending on Food"},
    ])
    self.assertFalse(result.inherited)
    self.assertIsNone(result.tool_name)
    self.assertNotIn("category_name", result.arguments)
    self.assertIsNotNone(result.clarification)

def test_unresolved_transaction_reference_requires_clarification(self):
    result = self.resolve("Show me that transaction")
    self.assertIsNotNone(result.clarification)

def test_food_before_budget_is_extracted(self):
    result = self.resolve("Show my September food budget")
    self.assertEqual(result.arguments["category_name"], "Food")
```

- [ ] In the service test class, reuse the `test_simple_profile_read_skips_the_llm_after_the_verified_tool_result` repository setup with content `Only food` and empty prior history. Patch `AgentToolExecutor.execute`, `generate_result`, and `generate_agent_result` to raise `AssertionError` if called. Assert the returned assistant text asks which financial record to use. Add a control for `What about PTPTN?` after spending history: it remains educational with no personal read.
- [ ] Run from `fincoach-backend`: `.\.venv\Scripts\python.exe -m pytest tests/test_accuracy_routing.py tests/test_rag_pipeline.py -q -p no:cacheprovider`. Confirm new tests fail for the reported behaviour before editing.
- [ ] Tighten modifier eligibility: detect a savings topic change before generic `what about` inheritance. Treat bare savings as an ambiguous personal topic, with a question offering saved-goal progress versus estimated saving capacity. Preserve explicit savings-goal/prediction routing. Expand bounded category parsing for category-before-budget/spending phrasing without consuming month names or arbitrary sentences as categories; still verify the category in the executor. Recognise unresolved demonstrative transaction references before broad search selection.
- [ ] Resolve knowledge-topic inheritance first, then evaluate `resolved_read.clarification` before casual generation. Keep existing disabled-write and product-policy handling ahead of execution. Remove the duplicated read-clarification branch. The essential order is:

```python
# After knowledge inheritance and applicable action/product policy checks:
if resolved_read.clarification:
    result = AgentLLMResult(content=resolved_read.clarification, model="fincoach-router")
    response_mode = "clarification"
elif route == CoachingRoute.CASUAL:
    result = generate_result(prompt, reasoning_effort=reasoning_effort, budget=request_budget)
    response_mode = "llm"
# Existing validated personal/education handling follows.
```

- [ ] Repeat the targeted tests. Add Malay equivalents for the new savings/transaction cues and a positive same-intent month/category continuation test. Review and commit only Task 1 files.

**Exit:** Wrong spending inheritance and broad unresolved-reference reads stop; orphan modifier questions cannot bypass clarification.

## Task 2: Validate and integrate the existing period comparison tool

**Files:** Review and modify only where tests expose gaps: `fincoach-backend/app/rag/routing.py`, `fincoach-backend/app/agent_tools.py`, and `fincoach-backend/app/rag/service.py`; add regression coverage to `fincoach-backend/tests/test_accuracy_routing.py`, `test_accuracy_tools.py`, and `test_rag_pipeline.py`.

**Current-workspace update:** Comparison support was added concurrently during planning. The current resolver returns `get_period_comparison` with `metric: spending` and `periods: [2026-06, 2026-08]` for June/August. Preserve this work; do not add a competing pair of comparison-date arguments to `get_spending_summary`.

**Interfaces:** Reuse `parse_comparison_request(content, *, now=None) -> dict | None`, `_PeriodComparisonArgs`, and `AgentToolExecutor._period_comparison`. Arguments are `metric`, `periods`, optional `category_name`, and optional `baseline`. Result records are `periods` entries containing `month`, `start`, `end`, `total`, and `change`; preserve existing incomplete-month behaviour and `_format_period_comparison`.

- [ ] Add a resolver regression test for the already-fixed case:

```python
result = self.resolve("Compare my spending in June 2026 and August 2026")
self.assertEqual(result.tool_name, "get_period_comparison")
self.assertEqual(result.arguments, {
    "metric": "spending", "periods": ["2026-06", "2026-08"],
})
```

- [ ] Add a tool regression using the existing controlled executor fixture:

```python
tools = executor([
    expense("may", 999, "Food", "2026-05-02"),
    expense("jun", 100, "Food", "2026-06-02"),
    expense("aug", 250, "Food", "2026-08-02"),
])
result = tools.execute("get_period_comparison", {
    "metric": "spending", "periods": ["2026-06", "2026-08"],
})
self.assertEqual([row["month"] for row in result["periods"]], ["2026-06", "2026-08"])
self.assertEqual([row["total"] for row in result["periods"]], ["RM100.00", "RM250.00"])
```

- [ ] Add failure-focused tests for `Compare spending for the last 13 months`, two custom partial date ranges, and an invalid explicit month/year. Assert clarification and zero tool execution instead of truncation or defaulting. Existing `_MAX_COMPARISON_MONTHS` slicing must not silently reduce a requested set. Add rollover/leap-February tests and verify category constraints reach every compared month.
- [ ] Run from `fincoach-backend`: `.\.venv\Scripts\python.exe -m pytest tests/test_accuracy_routing.py tests/test_accuracy_tools.py tests/test_rag_pipeline.py -q -p no:cacheprovider`. Already-fixed cases should pass; establish which newly added boundary tests fail before editing.
- [ ] Fix only the exposed parser/validation boundaries. Replace silent truncation with a limit check before slicing, using this behaviour:

```python
months = sorted(set(months))
if len(months) > _MAX_COMPARISON_MONTHS:
    raise ValueError("Please compare at most twelve calendar months at a time.")
```

  Detect unsupported explicit custom comparisons before the single-period fallback and ask for calendar months. Preserve the existing bare-comparison default (current month versus previous month), the supported multi-month tool, and explicit baseline choices. Do not reinterpret `last month` alone as a request for an extra comparison.
- [ ] Add service checks that formatted answers name the actual compared months, retain current-month incompleteness disclosures, and make no extra provider call for deterministic verified comparisons. Unknown categories must request clarification, not become all-category comparisons. Confirm existing savings/budget comparison semantics before changing shared parsing.
- [ ] Run affected tests and `tests/test_financial_grounding.py`; review the diff against the concurrent implementation and commit only this task's added fixes/tests.

**Exit / Milestone A:** Confirmed routing failures are covered and current comparison support is preserved with validated boundaries. No new comparison engine is introduced by this plan.

## Task 3: Give reads a shared readiness and parameter contract

**Files:** Modify `fincoach-backend/app/rag/routing.py` and `fincoach-backend/app/rag/service.py`; create `fincoach-backend/tests/test_read_resolution.py`.

**Interfaces:** Extend the existing frozen `ResolvedReadRequest` with defaulted fields, so existing constructors continue to work:

```python
class ReadReadiness(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"

# Add to ResolvedReadRequest; import dataclasses.field.
intent: str | None = None
readiness: ReadReadiness = ReadReadiness.READY
missing_required: tuple[str, ...] = ()
invalid_fields: tuple[str, ...] = ()
parameter_sources: dict[str, str] = field(default_factory=dict)
```

Use stable intent values `spending_summary`, `spending_comparison`, `period_comparison`, `transaction_search`, `transaction_reference`, `budget_status`, `financial_overview`, `financial_profile`, `savings_goals`, `savings_prediction`, `weekly_savings_plan`, `cashflow_forecast`, `upcoming_reminders`, `report_summary`, and `savings_unspecified`. Casual/education-only requests have no read intent. Do not introduce a second independent intent classifier.

- [ ] Add failing tests for default/explicit/inherited provenance and blocking invalid supplied values:

```python
from datetime import date
from app.rag.routing import ReadReadiness, resolve_read_request

def test_default_period_is_explicit_in_contract():
    result = resolve_read_request("Show my spending", [], now=date(2026, 9, 22))
    assert result.readiness == ReadReadiness.READY
    assert result.arguments["start_date"] == "2026-09-01"
    assert result.parameter_sources["start_date"] == "default"

def test_invalid_period_keeps_budget_intent():
    result = resolve_read_request("Show my budget last week", [], now=date(2026, 9, 22))
    assert result.tool_name == "get_budget_status"
    assert result.readiness == ReadReadiness.NEEDS_CLARIFICATION
    assert result.invalid_fields == ("month",)
```

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_read_resolution.py -q -p no:cacheprovider` and establish failures.
- [ ] Define a small parameter-policy mapping next to the read contract. Values use `required`, `defaultable`, or `optional`; each entry also states whether same-intent inheritance is allowed. Map spending/search/report ranges, monthly budget/overview/prediction/weekly-plan month, optional supported category/name/text filters, reminder range, and `get_period_comparison` metric/periods/baseline. Its periods are required (2–12 unique months), metric defaults to spending only when no explicit metric conflicts, and category/baseline are optional. Incompatible comparison parameters reset on intent change. Profile/cashflow reads have no inherited unsupported filters. A `transaction_reference` requires a resolved search filter before it becomes `transaction_search`; `savings_unspecified` requires an intent choice.
- [ ] Apply the order explicit -> compatible context -> default. Record sources for populated fields. Materialise concrete default dates using the passed `now`, and preserve effective defaults across recognised same-intent continuations rather than recalculating them across a month boundary. Retain executor defaults for backward compatibility with older tool callers.
- [ ] Populate readiness and invalid/missing fields at each clarification return. Reserve `UNSUPPORTED` for a known read operation outside supported capabilities (for example transaction attachment/image inspection); ambiguity stays `NEEDS_CLARIFICATION`. Service handling must stop before records/provider work for both non-ready states. Unknown category errors from the executor must become the same clarification state without dropping the category constraint.
- [ ] Update existing expectations that deliberately asserted `{}` for default arguments. Add tests for explicit override, no stale category after topic change, unknown category, unsupported operation, and personal-to-education transition. Assert concrete argument values and no execution when non-ready, not just the enum value.
- [ ] Run new tests plus Task 1/2 tests; review and commit Task 3 files.

**Exit:** Every read decision exposes why it can execute, why it cannot, and where its resolved parameters came from.

## Task 4: Persist and resume pending read clarification

**Files:** Create `fincoach-backend/app/rag/read_clarification.py` and `fincoach-backend/tests/test_read_clarification.py`; modify `fincoach-backend/app/rag/service.py`, `fincoach-backend/app/rag/follow_ups.py`; extend `fincoach-backend/app/coaching_history.py` only for an owner-scoped latest-eligible lookup if existing bounded history cannot establish eligibility. Test `test_coaching_history.py`, `test_coach_routes.py`, and `test_rag_pipeline.py` too.

**Interfaces:** New module exports `build_read_clarification(request: ResolvedReadRequest, *, origin_message_id: str, anchor_date: date) -> dict` and `resume_read_clarification(payload: dict, reply: str, *, now: date) -> ResolvedReadRequest`. These pure functions do not query Supabase; service/repository code establishes ownership and eligibility before passing saved state. Serialized `state.version` is `1`.

Payload shape:

```json
{
  "type": "read_clarification",
  "question": "Which month should I use for your budget?",
  "input_type": "single_select",
  "field": "month",
  "options": [{"id": "this_month", "label": "This month", "value": "2026-09"}],
  "allow_other": true,
  "state": {
    "version": 1, "origin_message_id": "original-user-message-id",
    "anchor_date": "2026-09-22", "intent": "budget_status",
    "route": "personal_finance", "tool_name": "get_budget_status",
    "arguments": {}, "parameter_sources": {},
    "missing_required": [], "invalid_fields": ["month"]
  }
}
```

- [ ] Add failing pure round-trip tests:

```python
def test_short_answer_resumes_budget_not_casual():
    pending = resolve_read_request("Show my budget last week", [], now=date(2026, 9, 22))
    payload = build_read_clarification(pending, origin_message_id="u1", anchor_date=date(2026, 9, 22))
    resumed = resume_read_clarification(payload, "July", now=date(2026, 9, 22))
    assert resumed.tool_name == "get_budget_status"
    assert resumed.arguments["month"] == "2026-07"
    assert resumed.readiness == ReadReadiness.READY
```

- [ ] Run the new test file to establish failure. Implement strict deserialization with version, route/tool/intent allowlist checks, supported fields only, bounded strings, and existing argument validation. Treat malformed saved state as unavailable context with a helpful question; never as permission to broaden the read. Build bounded options for missing month, ambiguous savings intent, and transaction filter collection. Support no-option free-text questions for missing comparison months or unsupported custom ranges that need calendar-month clarification.
- [ ] Integrate payload storage with the existing `complete_turn` assistant payload. On successful reads, save compatible `read_context` state beside other UI metadata. Reuse existing owner/session-scoped retrieval; validate assistant role and completed status. Do not read user-supplied `ui_payload` as authoritative state.
- [ ] Dispatch `interaction_reply` by the persisted payload type before the existing write-enabled check: `read_clarification` enters the normal validated read path; legacy action clarification retains its current write policy. The client supplies only the assistant message ID and answer value. Resolve intent, tool, and arguments from server-saved state. Both resumed and fresh reads must recheck current consent and use the same executor/grounding path.
- [ ] For ordinary chat replies, inspect the latest eligible completed assistant state before falling back to historical user-text replay. A compatible short answer updates its missing/invalid slot. Explicit new intent, `cancel`, `never mind`, `batal`, greeting, or thanks ends implicit pending context. Do not resume an older card after a later completed user/assistant turn supersedes it. Failed/retried current user turns do not falsely supersede the pending question. Define eligibility from saved turn/reply linkage and chronological history, not a process-local dictionary.
- [ ] Add service tests for `Only food` (zero reads/providers), pending budget -> `July` (one budget read), restart by reconstructing the service over saved rows, invalid reply -> another question, new savings topic -> no old budget read, revoked consent, foreign session/message, stale chip, duplicate request ID, and writes disabled. Assert endpoint responses and actual attempted tool names/arguments. Add a repository test proving the owner and session restrictions are applied.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_read_clarification.py tests/test_read_resolution.py tests/test_coaching_history.py tests/test_coach_routes.py tests/test_rag_pipeline.py tests/test_coach_follow_ups.py -q -p no:cacheprovider`. Confirm ordinary follow-up suggestions are suppressed during read clarification. Review and commit Task 4 files.

**Exit:** Clarification is a complete saved conversation operation that works through plain text, survives service restarts, and never depends on enabling write actions.

## Task 5: Reuse clarification cards for read queries

**Files:** Modify `fincoach-mobile/src/lib/types.ts`, `fincoach-mobile/src/lib/coach-agent.ts`, `fincoach-mobile/src/components/coach/coach-message.tsx`, and `fincoach-mobile/src/components/coach/coach-interaction-card.tsx`; test `fincoach-mobile/src/lib/coach-agent.test.ts`, `coach-interaction-ui.test.ts`, and `coach-api.test.ts`.

**Interfaces:** Add `CoachReadClarificationPayload` with discriminant `type: 'read_clarification'` and the shared question/input/field/options/allow_other fields. Add it to `CoachUiPayload`. Expose `isCoachReadClarification(value: unknown): value is CoachReadClarificationPayload`. The card accepts the union of legacy and read clarification payloads; it never reads or transmits the saved `state`. Keep `CoachInteractionReply` unchanged (`assistant_message_id`, `value`).

- [ ] Read the applicable mobile AGENTS instructions and the required versioned Expo documentation before editing mobile code. Inspect the configured visual-reference folder without its nested folders. Reuse current card styles and responsive layouts.
- [ ] Add a failing runtime-guard test:

```typescript
it('recognises a read question without a write action type', () => {
  expect(isCoachReadClarification({
    type: 'read_clarification', question: 'Which month?',
    input_type: 'single_select', field: 'month',
    options: [{ id: 'july', label: 'July', value: '2026-07' }],
    allow_other: true,
  })).toBe(true);
});
```

- [ ] Run from `fincoach-mobile`: `npm test -- src/lib/coach-agent.test.ts src/lib/coach-interaction-ui.test.ts src/lib/coach-api.test.ts` and establish failure.
- [ ] Extend the union and runtime guard; validate each option's string `id`, `label`, and `value`, and allow only supported input modes. Keep `isCoachAction` unchanged so a read card cannot become an executable write card. Render either clarification type through the same card. Preserve assistant-message linkage in the existing reply callback. Use `AppTextInput` when touching the input, matching project accessibility/scaling rules.
- [ ] Add tests that read-card selection and free text send the same `interaction_reply` structure as existing clarification, stale/disabled cards cannot submit while disabled, old action cards still render, and unknown future payload types fall back to assistant text. Make questions readable even without chips.
- [ ] Run the targeted tests, `npm run typecheck`, and `npm run lint`. Inspect the card on Honor 200 and a small emulator during implementation when available; record device limitations explicitly. Check wrapped option labels, keyboard visibility, scrolling, and repeated-tap handling.
- [ ] Review and commit Task 5 files.

**Exit / Milestone B:** Users can answer read clarification through saved chat or chips, without changing the existing visual direction or enabling write actions.

## Task 6: Verify the complete routing contract and document delivery

**Files:** Create `fincoach-backend/tests/fixtures/read_resolution_cases.json` and `fincoach-backend/tests/test_read_resolution_cases.py`; update this plan with actual results at implementation time.

**Interfaces:** Fixture cases contain `id`, `now`, `history`, `query`, and expected `tool_name`, `readiness`, `arguments`, `missing_required`, and `invalid_fields`. Do not store private financial records or provider credentials.

- [ ] Add the deterministic fixture runner:

```python
import json
from datetime import date
from pathlib import Path
import pytest
from app.rag.routing import resolve_read_request

CASES = json.loads((Path(__file__).parent / "fixtures" / "read_resolution_cases.json").read_text(encoding="utf-8"))

@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_read_resolution_contract(case):
    result = resolve_read_request(case["query"], case["history"], now=date.fromisoformat(case["now"]))
    expected = case["expected"]
    assert result.tool_name == expected["tool_name"]
    assert result.readiness.value == expected["readiness"]
    assert result.arguments == expected["arguments"]
    assert list(result.missing_required) == expected["missing_required"]
    assert list(result.invalid_fields) == expected["invalid_fields"]
```

- [ ] Populate cases covering all five original input failures, plain spending defaults, both comparison defaults and explicit month sets, month rollover, mixed English/Malay follow-ups, invalid dates, unknown category handling at the executor seam, explicit topic reset, unsupported reads, educational/casual turns, and unresolved transaction references. Keep service/persistence failure cases in Task 4's tests; a pure fixture cannot prove those behaviours.
- [ ] Run the fixture suite and all previously affected backend suites once. Then run the full backend suite once, plus mobile targeted tests/typecheck/lint if mobile changed. Investigate relevant failures; report any unrelated baseline failures separately rather than claiming a green suite.
- [ ] Review the final diff against each numbered spec rule. Confirm production execution still calls Supabase and no fake financial result entered application code. Report resolver correctness, service blocking, persisted continuation, and device verification separately; do not collapse them into one accuracy percentage.
- [ ] Record changed files, commands/results, live/device limitations, and milestone completion in this plan. Review and commit the fixture and documentation changes. Deployment remains a separate action; when subsequently requested, deploy the compatible backend before the mobile client and verify the contract using non-destructive reads.

## Implementation results (2026-09-22)

All tasks implemented on branch `codex/financial-report-analytics`.

| Task | Status | Commit |
|---|---|---|
| 1 — Stop inheritance / clarification bypass | Done | `0d43bd5` |
| 2 — Period comparison (concurrent work) | Preserved + validated | `0d43bd5` |
| 3 — Shared readiness/parameter contract | Done | `0d43bd5` |
| 4 — Persist + resume pending clarification | Done | `e43b2cb` |
| 5 — Mobile clarification card reuse | Done | `dca7411` |
| 6 — Contract fixtures + full verification | Done | `e4eeb4b` |

**Deviation from plan:** Task 1's `test_food_before_budget_is_extracted` was re-homed from the router to the executor-side resolver (`test_category_resolution.py::test_category_before_budget_with_month_resolves`). A concurrent, user-approved decision (see the `fincoach-category-resolver` memory) moved category resolution into the executor via a shared pure resolver against real category names ("don't add router regex"). Same user-facing behaviour, correct layer.

**Scope call (Task 3):** Only date-range reads (spending/report/search) materialise a concrete default period with provenance `default`. Month-key reads (budget/overview/prediction/plan) keep the executor's own current-month default — forcing a month onto `get_financial_overview` narrowed the broad snapshot and broke two existing tests. Still "defaultable"; the router just does not pin it.

**Commands / results:**
- Backend full suite (`.venv/Scripts/python.exe -m pytest -q`): 558 passed, 5 skipped. Two remaining failures are pre-existing WIP unrelated to this work — `test_grounding_runs_for_combined_route_and_without_retrieved_sources` (grounding fallback wording in `grounding.py`) and `test_savings_prediction ...remains_usable` (prediction reply formatting); both fail identically at the prior commit.
- Read-resolution fixtures (`test_read_resolution_cases.py`): 15/15.
- Mobile: `vitest run` coach-agent/coach-interaction-ui/coach-api 22/22; `tsc --noEmit` clean; `expo lint` clean for touched files (3 pre-existing warnings remain in unrelated test files).

**Changed files:** backend — `app/rag/routing.py`, `app/rag/service.py`, `app/rag/read_clarification.py` (new); tests — `test_accuracy_routing.py`, `test_read_resolution.py`, `test_read_clarification.py`, `test_read_resolution_cases.py` + `fixtures/read_resolution_cases.json`, and service tests in `test_rag_pipeline.py` (left uncommitted per the working-tree entanglement). Preserved concurrent Task 2/category work: `app/agent_tools.py`, `app/category_resolution.py`, `app/rag/follow_ups.py`, `test_category_resolution.py`, `test_accuracy_tools.py`, `test_period_comparison.py`. Mobile — `src/lib/types.ts`, `src/lib/coach-agent.ts`, `src/components/coach/coach-message.tsx`, `src/components/coach/coach-interaction-card.tsx` + tests.

**Live / device limitations:**
- No live-backend claim: unit tests use the repository's controlled fakes; production code still calls real Supabase, and no fabricated financial result entered application code.
- Task 5 not inspected on the Honor 200 or a small emulator (not available in this environment). The card reuses existing responsive styles and `AppText`; on-device verification is still pending.
- `follow_ups.py` needed no change: the existing `complete_turn` gate already suppresses next-step chips whenever `ui_payload.type` is set (a pending `read_clarification` qualifies).
- Deployment remains a separate action; when requested, deploy the compatible backend before the mobile client and verify with non-destructive reads.

## Plan self-review

- Requirements are covered by Tasks 1–5; Task 6 validates the complete contract.
- Contract names, payload discriminants, and reply fields are consistent across backend and mobile tasks.
- Write action enablement is not reused as permission for read clarification.
- No classifier/provider work is required to ship either milestone.
- Saved state has bounded lifetime through turn supersession; tests cover replay, ownership, consent changes, and restarts.
- This document proposes implementation; it does not claim the new behaviours or tests already exist.
