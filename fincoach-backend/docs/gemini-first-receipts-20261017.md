# Gemini-first receipt extraction — 17 October 2026

## Implementation and compatibility

The active source pipeline now sends the selected upright image and matching PaddleOCR rows to Gemini for structured extraction. The successful Gemini path never calls the rule parser or the secondary category classifier. OCR failure permits image-only interpretation. The old parser and category classifier remain the explicitly marked provider-failure fallback.

`POST /receipts/extract` retains its core fields and adds optional `extractionSource` (`gemini` or `ocr_fallback`), `currency`, `fieldEvidence`, `fieldStatus`, `summaryBreakdown` and `extractionMetadata`. Missing critical fields remain empty strings for old clients. No fabricated per-line verification records are returned. `verificationStatus` is retained for compatibility; it describes image extraction status, not independent proof of model accuracy. Critical-field numerical confidence is null.

The contract separates the final charge, printed summary components and items. Decimal reconciliation warns without replacing the printed charge. Included components stay in modifiers; unpriced standalone entries are omitted from saveable items with a warning. Non-MYR/unknown currency and ambiguous multiple receipts cannot silently populate an RM transaction. Gemini-generated evidence is an audit aid, not independent verification.

One provider request plus at most one repair shares the existing 30-second deadline. Requests below the existing ten-second minimum are not sent. The configured model rejected the fully constrained Pydantic schema with HTTP 400. A simpler provider schema succeeded; all size, enum, date and money checks remain enforced locally by Pydantic. The receipt model and OCR model were not upgraded.

The review screen requires explicit acknowledgement for fallback results. Existing form validation, manual correction, stable draft IDs and retry recovery remain. Older APKs can read the response and warnings but do not have the new acknowledgement checkbox: distribute the updated APK for that behaviour.

## Verification

- Backend: 119 focused tests and 23 subtests passed; two existing Supabase deprecation warnings.
- Mobile: 15 tests across six receipt suites passed, including actual review-screen acknowledgement, corrected input, failed save/retry, no-line-item saves, duplicate-save protection and crop/rotation coverage.
- TypeScript check and targeted ESLint passed.
- Hosted schema prerequisite: authenticated server-credential, zero-row read of `transactions.receipt_items` returned HTTP 200 and `[]`. No data or permissions were changed. This is not proof of a successful authenticated mobile save.

Live tests used an isolated Python process in Docker with candidate code under `/tmp`, not the running application's code mount. Only the explicitly supplied Old Legend screenshot was sent to Gemini. All three variants returned the correct merchant, date 2026-10-10, total RM14.80, category Food and one priced item.

| Input | Pipeline seconds | Gemini attempts | Prompt/output/total tokens | Warnings |
|---|---:|---:|---|---|
| Supplied screenshot | 11.91 | 1 | 3420 / 314 / 3734 | None |
| Same image rotated 90 degrees | 13.19 | 1 | 3367 / 329 / 3696 | None |
| Same image, simulated OCR failure | 2.54 | 1 | 1591 / 326 / 1917 | Supporting OCR unavailable |

These are three variants of one receipt, not a general accuracy benchmark. The initial failed schema request and diagnostic requests are not included in the successful-run token counts. Monetary cost was not calculated.

Raw local evidence: `evaluation-results/gemini-first-old-legend-20261017.json` and `evaluation-results/gemini-first-variants-20261017.json`.

Ayam Gepuk, McDonald's and Dojo have contract fixtures and historical parser tests, but were not re-tested live: their original clipboard images are no longer available. Reattach the original images to complete that gate. No Android device was attached to ADB, so native visual/touch and actual scan-to-save checks remain pending. Public endpoint delivery and a new APK were not tested or deployed.

## Prepared candidate and rollout

Running services were not restarted, recreated or redeployed. The current container remains healthy.

- Current container: `025163b299ddcdaf5f13f41a8324bd4294aa4f51164f5f8419a8cdb677b7756f`.
- Current image: `sha256:a348a9caffe2c9d20bf2e997ec9e93d36f61afda0669627084910fdf2a7cb8bc`.
- Current application bind mount: workspace `.deploy-stage/llm-interpretation-20261017/app`.
- Candidate application directory: workspace `.deploy-stage/receipt-gemini-first-20261017/app`.
- Candidate `manifest.json` records source hashes and previous hashes. The candidate copies the active staged application and overlays only the three receipt Python modules, preserving other staged backend behaviour.

After explicit deployment approval and review of pending tests:

1. Recheck that the active image/mount and candidate hashes still match this report. Preserve the existing Compose override and mount contents before making changes.
2. Change only the application bind mount in the desktop candidate Compose override to the prepared candidate. Recreate only the backend using the existing base and desktop override; retain environment and model caches.
3. Verify `/health`, `/ready`, the app-facing receipt endpoint and an authorized known receipt. Do not expose or reconnect tunnels as part of this task.
4. Build the canonical mobile project's EAS `preview` APK and install it. Verify normal extraction, forced fallback acknowledgement, editable fields, failed-save retry and actual receipt/image persistence on a test account.
5. Roll back by restoring the previous Compose override, exact image and previous application bind mount, then recreate the backend and repeat health/readiness checks. Image-only rollback is insufficient because application code is bind-mounted. No schema rollback is needed for this extraction change.

Deployment remains pending approval. No new migration, financial transaction, APK upload or public configuration change was performed.

## Deployment update — approved and completed 17 October 2026

This update supersedes the pending-deployment status above. The user explicitly authorized deployment to Windows Docker Desktop. Verified all candidate hashes and unchanged unrelated modules against the previous active mount, saved the previous Compose override to .deploy-stage/receipt-gemini-first-20261017/docker-compose.desktop-candidate.before.yml, changed only the application mount and recreated only the backend with --no-build --no-deps. The image and model caches were retained.

New container: 0254a7008339beb1b242b5213749af5af9c0021ed1a32338b03007e5db5d5799. Docker reports healthy. All three receipt-module hashes match the candidate manifest. Localhost and https://api.chisquaredv10.dpdns.org both returned HTTP 200 for /health and /ready, with OCR and embeddings ready. No tunnel configuration was changed.

The Android UI acknowledgement still requires the updated APK. No authenticated phone scan/save was performed during deployment. The previous image and original staged application directory remain available for rollback.
