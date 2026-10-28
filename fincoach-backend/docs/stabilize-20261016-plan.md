> Historical stabilization record: current repair results and live failures supersede earlier green claims. See [current verification](repair-20261016-verification.md) and [release checklist](stabilize-20261016-release-checklist.md).

# Stabilize FinCoach AI Coaching — working plan

## Stage 1 — Reconcile failing tests (81 failures + 4 import errors)
- [x] Classification matrix: each failure → active defect vs superseded contract (see completion log)
- [x] Fix active defects (answer_eval misapplied verdict, timing config)
- [x] Implement §2 behaviors on active entrypoints (verify relevance, notices, truncation, one correction)
- [x] Move safety scenarios onto current entrypoints (replacement tests)
- [x] Archive superseded tests with documented replacements + excluded from collection
- [x] Full backend suite: collects, passes, zero unexplained exclusions (0 failed / 0 errors; see run log)
- [x] Mobile suite + tsc pass (443 passed / 3 skipped / 0 failed; `tsc --noEmit` clean — verified 2026-10-16 17:42)
- [x] 68 stress cases stay green (`coach-stress-audit-2026-09-28.json`: 68/68, exit 0 — re-verified 2026-10-16 17:11)

## Stage 2 — Answer relevance and recovery
- [x] Verification call receives requested-part IDs per claim
- [x] Reject unrelated advice even when facts are in a source
- [x] Missing-information notices from validated unresolved parts (compound-interest follow-up)
- [x] Keep independently verified content when another part fails
- [x] Token-truncated output counts as incomplete
- [x] At most one corrective generation on the original deadline
- [x] Timing: 120s ceiling, 5s finalization reserve, 8s/verification, writer >=28s, correction >=26s

## Stage 3 — Report generation safe across devices
- [x] report_attempts migration: owner, action, attempt_id, fixed selection, storage path, lease (5 min, renew 1 min) — real pg17 harness, 4 consecutive passes
- [x] Extend report confirm/complete RPCs with attempt_id; owner-scoped status + renewal endpoints (backend tests + SQL assertions)
- [x] Mobile persists attempt id before send; immutable PDF path; no overwrite (`report-attempt.ts`, `coach-actions.ts`, `reports.ts` `upsert:false`; 443/3 mobile tests, tsc clean)
- [x] Report-history insertion inside backend executed transaction (SQL: 'completion links the attempt to its history row')
- [x] Cancellation invalidates attempt; late completion cannot publish cancelled report (SQL assertions + pgbench race both outcomes)
- [x] Reconcile uncertain responses before retry/cleanup; delete only unreferenced artifacts (mobile reconciliation + backend guarded cleanup; unknown state blocks retry, keeps reservation)
- [x] Preserve manual report + backup/restore behavior (SQL: manual + restored files stay writable/editable/deletable) — mobile: manual report and backup/restore paths untouched

## Stage 4 — Verification gates / release prep
- [x] Automated gates: full backend/mobile/TS + 68 stress (all green — see release checklist)
- [x] Answer logic replay incl. compound interest EN/MS topic switches (2026-10-16 live replay: 3 public conversations / 6 requests; see completion log)
- [x] Failure recovery: provider timeout, truncation, restart, deadline, retries (208 offline tests green + one live provider-timeout recovery observed)
- [x] Database/Storage gates (real pg17 harness: 4 consecutive passes incl. report-attempt races)
- [x] Release boundary checklist — `docs/stabilize-20261016-release-checklist.md` (drafted; disposable-account end-to-end + on-device checks remain explicit pre-release preconditions, not performed here)

---

# Completion log — 2026-10-16 reconciliation pass

Baseline artifact: `evaluation-results/stabilize-20261016/failures-list.txt`
(81 failed / 1340 passed / 4 import errors). Current maintained suite: 0 failed,
0 collection errors, no unexplained exclusions.

Run log (`evaluation-results/stabilize-20261016/`):
- `current-run3.txt`: **1372 passed, 5 skipped, 0 failed, 0 collection errors**
  (60.8s), includes the report-protocol backend changes. The 5 skips are the
  pre-existing conditional skips (no unexplained exclusions).
- `current-run4.txt`: **1372 passed, 5 skipped, 0 failed** (65.8s) — re-run on
  the frozen backend after the report-protocol work; report/action subset
  also green (`59 passed, 5 subtests`) and the research recovery/answer set
  green (`208 passed`). The 5 skips are the opt-in live LLM-judge matrix
  (`tests/test_llm_judge_adversarial.py`, `RUN_LLM_JUDGE=1`) — intentional,
  identical in the baseline XML.
- Stress audit re-run 2026-10-16 17:11: `{"checks": 68, "passed": 68, "failed": 0}`,
  exit code 0, evidence `evaluation-results/coach-stress-audit-2026-09-28.json`.
  (A PowerShell `2>&1 | Select-Object` pipeline misreported exit 1; direct
  redirection confirmed `EXIT=0`.)

## Archived (superseded engine) — `tests/archive/pre-rollback-engine-20261016/`
Whole files: `test_evidence_groups`, `test_research_blocks`,
`test_research_fact_bindings`, `test_llm_provider_session`,
`test_research_gap_batch`, `test_catalogue_coverage_recovery`,
`test_answer_completion_probe`, `test_research_completion_salvage`,
`test_research_qualification`. Individual tests extracted:
`test_gemini_bound_schema_avoids_rejected_nested_limit_without_relaxing_local_checks`
(removed `_BoundEvidenceProposal`), `test_pilot_uses_complete_fixed_public_units`
(broken `assessment_binding_pilot.py`), `test_ranked_long_list_preserves_known_incomplete_structural_read`
(removed `source_spans`). The archive README maps every file to its replacement
coverage; `tests/conftest.py` excludes the directory from collection.

## Superseded expectations updated in place (behavior ruling recorded)
- `test_research_recovery.py::test_public_search_uses_general_country_and_restricts_known_official_host`:
  the controlled live comparison in
  `docs/superpowers/plans/2026-10-06-coach-definition-progress.md` ruled country
  boost applies only to open discovery; restricted official-host searches carry
  no `country`. The test now asserts both halves instead of country+restrict.
- `test_research_windows.py::test_captured_str_faq_application_window_includes_channels`:
  dropped the rolled-back span-marker and neighbour-exclusion assertions; keeps
  the channel checks and the live 1800-char window bound.

## Stage 3 evidence (mobile, 2026-10-16 17:42)

- New `src/lib/report-attempt.ts` (+13 tests): persisted reservation keyed by
  owner/message/action, strict server-payload validation, reconciliation
  (`active`/`completed`/`missing`/`unknown` — only definitive answers clear),
  60s heartbeat with single in-flight guard, transient-error tolerance and
  404-stop.
- `coach-actions.ts` renders only the server-issued attempt path (duplicate
  uploads accepted only while the server still reports the attempt as
  publishable); `reports.ts` uploads `upsert:false` with a conflict classifier;
  legacy `fetchReportStoragePath` kept; `saveReportRecord`/`fetchReportByKey`
  removed.
- `coach-screen.tsx`: reconcile-before-retry (unknown blocks a new attempt),
  persist-before-send, adopt a server-replaced id, completed attempts render
  the executed card without regenerating, heartbeat starts before render and
  stops in `finally`, failed generation recorded with `complete(false)` before
  the reservation is discarded, lost completion kept for retry.
- Verified by the main session: `npx vitest run` → **443 passed / 3 skipped**
  (54 files, +25 tests), `tsc --noEmit` → clean.
- Known limitations (recorded, not blockers): a suspended app (>5 min) lets a
  lease lapse and the retry surfaces an error; 404/409 map to the pre-existing
  generic copy; on-device verification still pending hardware.

## Bounded live coaching set (answer-logic replay) — 2026-10-16

Opt-in public probes only (`scripts/coach_follow_up_probe.py --live`): real
corpus RPCs/providers/web, ephemeral history, private tools forbidden, artifacts
retained under `evaluation-results/stabilize-20261016/`. Six Coach requests
total (bounded; no large sweep).

1. `live-compound-en-20261016.json` — "What is compound interest?" (complete,
   20.1s, web-free) then "Can you give a simple example?" (43.7s, 84s left).
   The 16 Oct defect (unrelated comparison-table gap + product-disclosure
   advice accepted as verified) **does not reproduce**: the verifier flagged
   the unrelated/numeric claims (`unsupported_number`, `unrelated_notice`),
   one corrective generation ran on the original deadline, and the delivered
   answer kept the relevant, arithmetically correct example with an honest
   incomplete notice from the validated unresolved part.
2. `live-compound-ms-20261016.json` — "Apa itu faedah kompaun?" (complete,
   22.0s; KWSP attribution matches the corpus source) then "Boleh berikan
   contoh mudah?" (46.4s, 83.5s left; correct RM17,908.48 and RM500/month
   examples, honest notices, no unrelated advice).
3. `live-topic-switch-ms-en-20261016.json` — MS definition then an explicit
   switch to English PIDM coverage. `read_context_inherited: false` (no
   compound-interest carry-over); during the corrective generation the fallback
   model timed out (`APITimeoutError`, 18s) → `recovery_generation_unavailable`
   → the service shipped only the four verified PIDM claims (limit figure
   removed) plus the incomplete notice. This is the required degraded path:
   verified content kept, rejected numeric claim never shown, 47.1s of the
   120s deadline used.

## Stage 3 evidence (backend + SQL, 2026-10-16 17:20-17:40)

- Migration `20261016120000_report_attempt_protocol.sql` applied by the real
  offline harness (`tests/run_financial_integrity_database.ps1`, Docker
  pg17/pgvector, no network): **4 consecutive full passes**
  (`evaluation-results/stabilize-20261016/database-run2.txt`, `-run3.txt`,
  `-run4.txt`; run1 unsaved) — all four assertion files plus all pgbench races,
  final line `All database checks passed.`
- Race fixes this pass: the race helper no longer stores debug rows
  (`public.test_race_log` removed); the post-race assertion now accepts the
  legitimate cancelled outcome (attempt rows all superseded/cancelled, no
  active/completed attempt and no linked history row) instead of demanding
  zero attempt rows.
- `tests/report_attempt_assertions.sql` now covers: leased approval, resume,
  supersede/winner, immutable per-attempt path, fresh-id substitution for a
  reused/reserved path, expired-lease block, failure release + retry on a new
  attempt, cancellation invalidation, late completion refusal, category scope,
  metadata shape checks, heartbeat renewal + owner/message binding, RLS and
  storage/reports policy changes, manual + restored file writeability, and
  DB-level path/unique constraints.
- Backend route contract: confirm/complete accept `attempt_id`; owner-scoped
  `GET /messages/{id}/actions/report-attempt/{attempt_id}` and
  `POST .../renew` exist; completing without an attempt id is an explicit
  `AgentActionConflict` (409) "The report attempt is required to finish this
  action." — the signal older report clients need to be told to update.
- Targeted backend tests after the SQL changes:
  `tests/test_agent_actions.py tests/test_agent_action_boundaries.py
  tests/test_coach_routes.py` → **59 passed, 5 subtests passed**.

## Active defects fixed during reconciliation


- `definitional_corpus_hit` now applies only to plans without part tracking, so
  part-tracked definitions still get the applicability-checked assessment
  (unrelated corpus still triggers recovery; sufficient corpus stays web-free).
- Corpus-only sufficient decisions with no bindable approved quotations ship the
  generated explanation through the regular corpus-grounded path instead of the
  web citation contract ("nothing left FinCoach" case).
- An unavailable definition hides candidate source cards and the snapshot;
  procedural unavailable answers keep their actionable URL snapshot.
- Unchanged bounded extraction rechecks the restriction once (bounded by the
  shared assessment-call ceiling) before the next discovery slot.
- Replacement for the archived incompleteness tests:
  `tests/test_research_answer.py::test_dangling_document_list_introduction_is_never_displayable`
  pins the live `incomplete_statement` backstop.
