# Partial repair implementation and verification — 2026-10-16

## Implemented

| Reviewed defect | Corrected behavior |
|---|---|
| Success without PDF | Backend reads bounded PDF bytes and verifies metadata/signature/size. Atomic SQL completion rechecks the exact Storage identity/version/updated timestamp, ownership, MIME and size before history insertion. Missing or changed objects cannot publish. Byte checks are not a full PDF parser or native rendering proof. |
| Competing devices share attempt | Row-locked claim returns the exact attempt in the same transaction; another device cannot adopt an unexpired claim. Cancellation and terminal replay remain atomic. |
| Old client starts generation | Missing attempt ID produces update_required (426) before claiming. Mobile supports structured protocol errors and existing string errors. |
| Incorrect timing | One 120-second ceiling, five-second finalization reserve, eight-second verification allocations, 28/26-second writer thresholds and at most one correction. |
| Expired saved attempt loops | Mobile parses server leases, reconfirms saved attempts, reacquires expired claims safely, and blocks unknown outcomes or another device's claim. Minute heartbeat stops in finally; definitive lease loss blocks upload/completion. |
| Category differs from history | Rendering uses server-issued category ID, snapshot name, dates, report type and immutable path. Coaching no longer resolves a category by name. |

Additional final-review fixes bound the caller's artifact-download wait and retry cleanup of terminal unreferenced artifacts, including uploads arriving after cancellation. Cleanup paths come from a service-only SQL query; reserved report history cannot acquire new client references.

The [corrective migration](../../fincoach-mobile/supabase/migrations/20261017120000_report_claim_and_artifact_verification.sql) is prepared locally. Existing OpenCode changes and unrelated working-tree changes were preserved.

## Fresh evidence

- Backend: **1422 passed / 5 skipped / 0 failed**, plus 2420 subtests. Final full suite ran in an offline Linux container after Windows collection stalled; no tests were excluded to bypass that problem.
- Mobile: **449 passed / 3 skipped / 0 failed**; TypeScript passed immediately before the final run.
- Stress: **68/68**.
- Real isolated PostgreSQL 17: three successful harness runs, including missing/changed artifacts, owner checks, expired claims, cancellation, rollback, terminal replay, manual-report policy compatibility and concurrent races.
- New regressions cover interrupted upload then retry after lease expiry, frozen selection, competing claims, lease loss, old clients, verifier timeout and timing boundaries. Relevant regressions were observed failing before fixes.

Evidence paths and remaining release gates are in [the release checklist](stabilize-20261016-release-checklist.md). Source SHA-256 hashes are saved in evaluation-results/repair-source-manifest.json.

## Live gate failed; failures retained

All 24 pre-labelled requests completed, with no private financial reads or persisted coaching messages in the probe. Manual relevance: 13 pass, 9 partial, 2 fail. Completeness: 13 pass, 3 partial, 8 fail. Citation support was assessed separately; supported facts can still be irrelevant.

Remaining observed problems include an example follow-up routed as casual conversation, missing concrete examples/calculation results, irrelevant personal-record diversions, English fallback text in Malay conversations, unnecessary incomplete notices, and unrelated PIDM material answering an unknown bank-rate question. Several source-unavailable responses were safe but incomplete. These findings remain unresolved; passing repair regressions does not establish normal live coaching quality.

See [all 24 manual assessments](../evaluation-results/repair-20261016-live24/manual-review.md) and the adjacent original transcripts, manifest and execution log. No failed case was removed or replaced with a successful rerun.

Android, real Storage/PDF and hosted deployment checks remain unexecuted. Write actions remain disabled. Nothing was committed, deployed, applied to hosted Supabase or tunnelled.
