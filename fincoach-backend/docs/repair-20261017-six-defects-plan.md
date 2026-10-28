# Six-defect repair plan — report protocol, mobile recovery, answer deadline (2026-10-17)

Sources: the 17 Oct handoff (Tasks A–E + answer-deadline section) and the
`stabilize-20261016-plan.md` completion log (historical evidence only).

Working rules: preserve the working tree (no commit/push/deploy/tunnel), keep
`COACH_WRITE_ACTIONS_ENABLED` disabled, add a new corrective migration after
`20261016120000_report_attempt_protocol.sql`, write a failing regression test
before each fix, never weaken tests.

## Task A — atomic claim (owner: backend + SQL)

- [ ] New migration `20261017120000_report_attempt_claim_and_artifact.sql`
- [ ] `claim_coach_report_attempt(user,message,action,attempt) -> {message,attempt}`:
      lock message then attempt; pending/failed start; same id resumes/reacquires;
      different id blocked while unexpired (`action_in_progress` + lease expiry);
      expired attempt replaced (superseded); terminal id reuse refused
      (`attempt_id_reused`); executed returns terminal result; cancelled refuses.
- [ ] `commit_coach_action` reduced to reminders + cancellations (5-arg); report
      transitions must go through claim/complete.
- [ ] Backend `AgentActionService.confirm` uses claim only; removes
      `find_active_report_attempt` lookup from confirmation.
- [ ] Regression tests (unit + SQL race assertions).

## Task B — verify a real PDF before publishing

- [ ] `complete_coach_report_attempt(...)` final transaction rechecks the locked
      action, attempt and matching `storage.objects` identity/version; inserts
      history, completes the attempt, executes the action atomically.
- [ ] Backend `app/report_artifacts.py`: metadata check (exact reserved path,
      owner, nonzero size, PDF mime, bucket limit) + bounded-timeout Storage
      download + PDF signature check; metadata alone never suffices.
- [ ] Extend the offline storage.objects fixture (owner/owner_id/metadata/
      updated_at + unique(bucket,name)); SQL success tests create a valid object
      fixture before completion; metadata-fixture vs real PDF tests distinguished.
- [ ] Cleanup only terminal, unreferenced artifacts; uncertainty preserves files.
- [ ] Regression tests (missing PDF, invalid artifact, atomic rollback).

## Task C — compatibility + conflict responses

- [ ] Report confirm/complete without `attempt_id` → HTTP 426,
      `{code:'update_required', message:'Update FinCoach to generate this report.'}`.
- [ ] Structured codes: `action_in_progress` (+`lease_expires_at`),
      `attempt_expired`, `attempt_id_reused`, `report_artifact_invalid`.
- [ ] Mobile parses structured details, keeps string-detail support, maps the
      codes; owner-scoped 404s unchanged; reminders untouched.

## Task D — mobile recovery

- [ ] Attempt response gains `lease_expires_at` / `server_time` / `lease_valid`
      (server-calculated); DB status enum unchanged.
- [ ] Persist attempt before confirm; reconcile saved attempt first; active ⇒
      atomic confirm with the same id; completed ⇒ show result; cancelled/
      superseded ⇒ refresh; unknown ⇒ retain; competing claim ⇒
      "Report generation is already in progress" (never adopt).
- [ ] Heartbeat before render, 60 s, stop in `finally`; definitive lease loss
      stops upload/completion from that run; transient renewal failures keep the
      reservation; never `complete(false)` for a lost success response; reuse of
      an immutable upload only for the reconciled attempt.

## Task E — render the frozen selection

- [ ] `generateCoachReport(userId, attempt, deps)`: fixed category id/name snap,
      dates, report type, storage path; no name lookup, no relative dates;
      deleted category fails clearly and never widens to all categories.

## Answer deadline (Task F)

- [ ] Centralize: 120 s ceiling, 5 s finalization reserve, 8 s verification,
      initial writer ≥28 s (reserve 8), corrective ≥26 s (18 s max, reserve 8),
      one correction on the original clock, children never extend the parent.
- [ ] Remove hardcoded 5 s verifier stages; pass the work budget through
      writing and recovery (both service call sites); no double reserve.
- [ ] Truncation, relevance, numerical, qualification and verified-partial
      behavior preserved. Regression tests around 28/26.

## Verification

- [ ] Focused regressions per task, then full backend + mobile + tsc.
- [ ] 68-case stress audit (new log, keep history).
- [ ] Offline PostgreSQL harness with the corrective migration, repeated passes.
- [ ] 24 pre-labelled live coaching cases (4× relevance, numerical,
      qualifications, EN/MS equivalence, topic changes, incomplete evidence).
- [ ] New dated evaluation-results directory + release checklist update.
- [ ] Android device checks and disposable-account real Storage checks remain
      external preconditions (no device attached / not authorized).
