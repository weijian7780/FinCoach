# Coaching repair release checklist — 2026-10-16

**Release blocked.** Automated repair checks pass; the bounded live answer-quality gate fails. This supersedes earlier stabilization gate claims.

| Gate | Current result | Evidence under evaluation-results/ |
|---|---|---|
| Full backend | PASS: 1422 passed, 5 opt-in live-judge skips, 0 failures; 2420 subtests | repair-backend-final.log / .xml |
| Mobile | PASS: 449 passed, 3 skipped, 0 failures | repair-mobile-final.json |
| TypeScript | PASS: tsc --noEmit, exit 0 before final mobile suite | Final verification command |
| Stress audit | PASS: 68/68 | repair-stress-final.json / .log |
| Isolated PostgreSQL 17 | PASS: three harness runs; final includes cleanup and Storage-policy assertions, competing confirmation/cancellation races | repair-database-current.log, repair-database-final.log, repair-database-release.log |
| Live answer quality | FAIL: 24 pre-labelled requests retained and manually reviewed | repair-20261016-live24/manifest.json, execution.json, manual-review.md |
| Actual Android app | UNEXECUTED in this repair run; Honor 200 / Pixel 8 verification required | ADB unavailable in checked locations |
| Real Supabase Storage and rendered PDF | UNEXECUTED; SQL Storage metadata fixtures and mocked byte-stream tests do not establish this gate | Disposable-account end-to-end checks pending |
| Hosted migration/build verification | UNEXECUTED; no deployment authorized | Pending release stage |

## Required before release

- Resolve and replay the live relevance/completeness failures without discarding original evidence. See [manual review](../evaluation-results/repair-20261016-live24/manual-review.md).
- Run actual Android send/retry, history, consent, reminders and report generation.
- In an isolated real Storage environment, verify rendered PDFs, lost upload/completion responses, lease expiry, two-device claims, cancellation and late-upload cleanup. Verify manual report and backup/restore behavior.
- Keep COACH_WRITE_ACTIONS_ENABLED disabled during preparation. Cleanup worker also remains disabled under this flag. A later authorized isolated test configuration is required for write-path end-to-end checks.

## Deployment order — only after explicit authorization

1. Apply prerequisite migrations, then 20261016120000_report_attempt_protocol.sql, then **20261017120000_report_claim_and_artifact_verification.sql**. Do not substitute an edited historical migration.
2. Verify claim_coach_report_attempt, complete_coach_report_attempt, renew_report_attempt and list_abandoned_coach_report_artifacts signatures/permissions against the tested migration; deploy matching backend and verify build identity.
3. Release compatible mobile. Missing report attempt IDs receive HTTP 426 / update_required before a new report claim; clients show readable protocol errors.
4. Execute disposable-account checks before enabling production write actions.

No commit, hosted migration, deployment or tunnel change was performed. HEAD remains 4da8020. SQL harness results prove isolated database behavior only.
