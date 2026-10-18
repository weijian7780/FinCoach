# Financial integrity fixes — 15 October 2026

Implemented the six stages selected by the user. Existing unrelated workspace changes were preserved.

| Stage | Change | Verified evidence |
|---|---|---|
| Receipt integrity | A receipt draft retains one transaction ID; recovery reads by owner and ID; uncertain commits retain the image; overlapping saves are blocked; all items and modifiers use structured JSON and appear on transaction details. Conflicting edited retries open the existing transaction. | Lost insert/upload responses, failed recovery followed by retry, duplicate saves, and changed-payload conflicts pass unit tests. PostgreSQL snapshot/restore preserves 30 long items and modifiers; old backups without items still restore. Storage behavior is mocked in unit tests. |
| Atomic financial saves | `save_budget_month` commits the overall budget and category allocations together; decreases precede increases. `replace_tracked_categories` commits the full selection together. Both RPCs verify ownership and retain RLS enforcement. | Real PostgreSQL RM50/RM50 to RM60/RM40 reallocation succeeds. An injected late failure rolls back both earlier category changes and parent changes. Invalid tracked selections preserve the old selection. Cross-owner writes are rejected. |
| Complete reads | Transaction history, report source data, and exports share count-checked pagination with deterministic ordering, actual returned-page offsets, duplicate detection, and fail-closed completeness checks. Dashboard and alert callers already consume `fetchTransactions`. | 1,251 records under a 200-row server cap produce the expected count and independently calculated sum. Missing counts, duplicate rows, changed counts, premature empty pages, and page errors are rejected. |
| Reminder dates | Recurrence advances local calendar dates using notification-preference timezone, preserving wall time and the day anchor. Malaysia is the default. | Midnight, 07:59, month/year boundaries, January 31, February clamping, leap years, and a weekly daylight-saving boundary pass. |
| Interrupted AI requests | Atomic server-only processing claims expire after 15 minutes. Token checks prevent abandoned workers from finishing or failing a replacement request. Completed replies are reused. | Real SQL verifies active-claim exclusion, expiry/reclaim, old-worker fencing, and exactly one reply. Eight simultaneous PostgreSQL clients acquire exactly one claim. Repository and service unit tests pass. |
| Admin consistency | Page requests use a generation guard across searches, pagination, refresh, tab changes, and authentication changes. Old-token errors cannot revoke a newer session. Profile names backfill and synchronize to account access; later sign-ins preserve the canonical profile name. | Reversed-response and invalidation tests pass; SQL verifies profile-name propagation, persistence across sign-in, and unchanged role/status. |

## Verification

- Mobile: `npm.cmd test -- src supabase/functions --reporter=dot` — **52 files, 401 tests passed**. `TEMP` and `TMP` pointed at the workspace `.test-tmp` directory.
- Mobile and admin: `node_modules/.bin/tsc.cmd --noEmit` — passed.
- Admin: `node --test tests/request-gate.test.ts` — **2 tests passed**.
- Backend, from `fincoach-backend`: `.venv/Scripts/python.exe -m pytest tests/test_coaching_history.py tests/test_rag_pipeline.py -q -k 'not lifespan'` — **106 tests and 74 subtests passed**, one unrelated lifespan/startup test excluded after hanging in this Windows execution environment.
- Database: `fincoach-backend/tests/run_financial_integrity_database.ps1` — passed against a fresh offline `pgvector/pgvector:pg17` container, including both SQL assertion files and eight concurrent claims. The harness removes its own container and temporary SQL file. All manually created test containers were also removed.
- `git diff --check` for edited tracked implementation files — passed.

## Rollout order and remaining verification

1. Apply `20261015091221_repair_financial_integrity_and_admin_sync.sql` and then `20261015092100_recover_coaching_processing_leases.sql` after the existing migrations. The reference `schema.sql` is not a replacement for the migration history.
2. Deploy the updated FastAPI backend and `process-alerts` Edge Function.
3. Build/deploy the admin and mobile clients. New mobile writes depend on the new RPCs and receipt column.
4. Verify receipt save/retry/detail rendering and reminder delivery on the phone, and admin interactions in the deployed UI.

No hosted database was changed and no updated application or service was deployed. No browser or phone UI tests were performed. SQL tests use local stand-ins for Supabase infrastructure; they do not prove hosted Auth, Storage, scheduled delivery, or public connectivity. Docker Desktop was started for the local tests and remains running.
