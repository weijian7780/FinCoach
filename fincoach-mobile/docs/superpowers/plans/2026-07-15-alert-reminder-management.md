# Alert and Reminder Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement FRAR-01 through FRAR-04 as a prototype-aligned Alerts inbox, separately configurable notification types, synchronized bill reminders, and automatic cloud push delivery to registered Android devices even when FinCoach is closed.

**Architecture:** Supabase PostgreSQL is the source of truth for notification preferences, reminders, alert history, and device registrations. The Expo app owns the prototype UI, user CRUD, permission flow, push-token registration, deep links, and immediate budget/savings event detection. Supabase Edge Functions own trusted device reassignment, due processing, Expo Push Service delivery, receipt checking, retry, and stale-token deactivation. A database alert-insert webhook and Supabase Cron connect immediate and scheduled alert creation to one idempotent delivery path.

**Tech Stack:** Expo SDK 56, React Native 0.85, Expo Router, `expo-notifications ~56.0.20`, TypeScript, Vitest, Supabase PostgreSQL/RLS/Realtime, Supabase Edge Functions on Deno 2, Supabase Cron/`pg_net`/Vault, Expo Push Service, Android FCM v1.

## Global Constraints

- Work only in the canonical source repository: `C:\Users\User\Desktop\School\UMS SEM 6\FYP Develop\fincoach-mobile`.
- Treat `C:\fcb` only as a disposable short-path Android build copy; synchronize canonical changes into it after source verification.
- Follow only the root prototype files in `G:\My Drive\FYP 1 & 2\FinCoach UI`; ignore nested folders and preserve the existing Hanken Grotesk/indigo visual direction.
- Keep every notification type independently configurable: Budget, Savings, Spending, and Bills.
- Use cloud push through Expo Push Service/FCM. Do not create duplicate local notification schedules on individual devices.
- Keep the in-app inbox usable when Android notification permission is denied.
- Never place a Supabase service-role key, Expo access token, Cron secret, or webhook secret in the mobile bundle.
- Keep alert update permissions column-scoped to `read_at` and `dismissed_at`; delivery state is server-owned.
- Use synchronized soft dismissal for alerts; do not hard-delete alert history from the mobile app.
- Do not add AI, FastAPI, bank integration, report/export behavior, or unrelated modules.
- Do not update the ERD or thesis data dictionary in this implementation; that documentation work is explicitly deferred.
- Do not add `react-native-svg`, `@react-native-community/datetimepicker`, or another native date picker.
- Remote push must be tested in a rebuilt development/release APK on the Honor 200, not Expo Go.
- Do not create branches, commits, worktrees, or push changes; the user handles GitHub.

---

### Task 1: Create the normalized notification schema, RLS, webhook hook, and verifier

**Files:**
- Create with Supabase CLI: `supabase/migrations/*_complete_alert_reminder_management.sql`
- Create: `scripts/verify-alert-schema.mjs`
- Modify: `supabase/schema.sql`

**Interfaces:**
- Produces `public.notification_preferences`, `public.reminders`, `public.alerts`, and `public.user_devices`.
- Produces one default preference row per user on first upsert rather than relying on client-only defaults.
- Produces the unique alert identity `(user_id, dedupe_key)`.
- Produces an alert-insert trigger that queues an authenticated `send-alert` request only when Vault runtime values are configured.
- Keeps `alerts.delivery_status`, retry metadata, and per-device Expo ticket/receipt metadata server-controlled.

- [ ] Run `npx.cmd supabase --version`; stop and fix the local CLI only if the command fails.
- [ ] Create `scripts/verify-alert-schema.mjs` first. Make it discover exactly one `*_complete_alert_reminder_management.sql` migration and assert four tables, foreign-key types, constraints, indexes, grants, RLS enablement, owner policies, column-level alert updates, unique dedupe, updated-at triggers, and the alert-insert delivery hook.
- [ ] Run `node scripts/verify-alert-schema.mjs`; expect failure because the module migration does not exist.
- [ ] Run `npx.cmd supabase migration new complete_alert_reminder_management` so the CLI, not the plan, creates the timestamped migration filename.
- [ ] Implement `notification_preferences` with one UUID owner row, type-specific enable flags, lead days/times, daily-or-weekly spending settings, weekday, IANA timezone, timestamps, and bounded check constraints.
- [ ] Implement `reminders` with UUID owner, bill-only type, trimmed title, optional positive amount, `due_at`, `lead_days`, `recurrence`, `enabled`, `next_trigger_at`, `last_triggered_at`, and timestamps. Constrain recurrence to `none|weekly|monthly|yearly`.
- [ ] Implement `alerts` with type/kind/title/message, nullable source IDs using the real existing UUID/bigint types, dedupe key, schedule/read/dismiss timestamps, server delivery status, aggregate error/retry fields, and JSONB per-device ticket/receipt state that stores device IDs rather than push-token copies.
- [ ] Implement `user_devices` with owner UUID, globally unique Expo push token, Android platform, optional device name, active/last-seen/error state, and timestamps.
- [ ] Add indexes for owner/time inbox reads, unread alerts, due reminders, due delivery retries, savings/budget source navigation, and active device lookup.
- [ ] Enable RLS on all four tables. Add owner-only preference reads/inserts/updates, reminder CRUD, alert reads/inserts, alert read/dismiss updates, and no direct token-table enumeration or writes from the mobile Data API.
- [ ] Revoke broad alert updates and grant only `UPDATE(read_at, dismissed_at)` to `authenticated`; grant only safe insert columns so a client cannot set delivery state.
- [ ] Add an `AFTER INSERT` alert trigger using `pg_net` and Vault values `alert_webhook_url` and `alert_webhook_secret`. If either value is missing, preserve the alert row and emit no secret or transaction-breaking exception.
- [ ] Mirror the final migration in `supabase/schema.sql` without weakening existing module grants or policies.
- [ ] Run `node scripts/verify-alert-schema.mjs`; expect all assertions to pass.

### Task 2: Implement notification types and pure domain rules with TDD

**Files:**
- Create: `src/lib/alerts-domain.test.ts`
- Create: `src/lib/alerts-domain.ts`
- Modify: `src/lib/types.ts`

**Interfaces:**
- Produces `NotificationPreferences`, `NotificationType`, `AlertKind`, `AlertRecord`, `BillReminder`, `ReminderRecurrence`, `AlertFilter`, and write-input types.
- Produces `getCrossedBudgetThreshold(previousUsed, currentUsed, limit)`.
- Produces `getCrossedSavingsMilestones(previousAmount, currentAmount, targetAmount)`.
- Produces `buildBudgetDedupeKey`, `buildSavingsDedupeKey`, `buildSpendingPeriodKey`, and `buildBillDedupeKey`.
- Produces `advanceRecurringDate`, `calculateNextBillTrigger`, `calculateSavingsReminderAt`, `validateBillReminderInput`, `groupAlertsByDate`, `filterAlerts`, and `routeForAlert`.

- [ ] Write failing tests for budget boundaries below/at/above 80% and 100%, direct jumps to exceeded, non-positive limits, decreases, and no repeated crossing.
- [ ] Write failing tests for newly crossed savings milestones at 25/50/75/100%, multiple milestones in one contribution, completion, decreases, and invalid targets.
- [ ] Write failing tests for stable dedupe keys across budget month/category, savings goal/milestone/date, daily/weekly spending periods, and bill occurrence timestamps.
- [ ] Write failing recurrence tests for weekly, month-end clamping, leap year, yearly leap-day clamping, and no recurrence drift from a previously clamped month.
- [ ] Write failing validation tests for blank/overlong title, invalid RM amount, expired due date, lead-day bounds, invalid recurrence, and timezone-safe trigger calculation.
- [ ] Write failing inbox tests for All/Insights/Alerts filters, Today/Yesterday/Earlier grouping, unread status, and source-route mapping with safe `/alerts` fallback.
- [ ] Run `npm.cmd test -- src/lib/alerts-domain.test.ts`; expect missing-module failure.
- [ ] Add the notification/reminder/alert types and implement the smallest pure functions that satisfy every test. Use integer cents for threshold comparisons and ISO timestamps at persistence boundaries.
- [ ] Run `npm.cmd test -- src/lib/alerts-domain.test.ts`; expect pass.

### Task 3: Build the injected Supabase client boundary for preferences, reminders, alerts, and registration

**Files:**
- Create: `src/lib/alerts.test.ts`
- Create: `src/lib/alerts.ts`
- Modify: `src/lib/types.ts`

**Interfaces:**
- Produces `fetchNotificationPreferences`, `saveNotificationPreferences`, and `ensureNotificationPreferences`.
- Produces `fetchReminders`, `fetchReminder`, `createReminder`, `updateReminder`, `setReminderEnabled`, and `deleteReminder`.
- Produces `fetchAlerts`, `fetchUnreadAlertCount`, `markAlertRead`, `markAllAlertsRead`, `dismissAlert`, and `createIdempotentAlert`.
- Produces `registerDevice`, `refreshDeviceRegistration`, and `deactivateDevice`, all through the authenticated `register-device` Edge Function.
- Accepts an injectable Supabase-like client following existing `budget.ts`, `savings.ts`, and `transactions.ts` test patterns.

- [ ] Write failing fake-client tests for default preference upsert, independent partial preference updates, owner filtering, and backend error propagation.
- [ ] Write failing tests for ordered reminder reads, CRUD, enable/disable, recalculated `next_trigger_at`, and confirmed delete behavior.
- [ ] Write failing tests for alert paging/order, unread count excluding dismissed rows, read state, mark-all, soft dismissal, safe insert columns, and duplicate-key success handling.
- [ ] Write failing function-invocation tests for authenticated register/refresh/deactivate actions without direct `user_devices` table writes.
- [ ] Run `npm.cmd test -- src/lib/alerts.test.ts`; expect missing-module failure.
- [ ] Implement the client boundary, using the active authenticated user ID and explicit selected columns. Translate Supabase errors into concise retryable messages without claiming unsaved changes succeeded.
- [ ] Run `npm.cmd test -- src/lib/alerts.test.ts src/lib/alerts-domain.test.ts`; expect pass.

### Task 4: Add the Expo Notifications native adapter and app bootstrap

**Files:**
- Create: `src/lib/notification-platform.test.ts`
- Create: `src/lib/notification-platform.ts`
- Create: `src/components/notifications/notification-bootstrap.tsx`
- Modify: `package.json`
- Modify: `package-lock.json`
- Modify: `app.json`
- Modify: `src/app/_layout.tsx`
- Modify: `src/lib/auth-context.tsx`

**Interfaces:**
- Produces a native-module-free test seam for `configureAndroidChannels`, `getPermissionState`, `requestPermission`, `getExpoPushToken`, `openAndroidNotificationSettings`, and listener registration.
- Registers the `general`, `budget`, `savings`, `spending`, and `bills` Android channels before requesting Android 13+ permission.
- Uses `extra.eas.projectId` when obtaining the Expo push token.
- Registers/refreshes the token after login and foreground return, and deactivates it before logout when possible.

- [ ] Write failing adapter tests with a mocked Notifications SDK for channel creation order, denied permission, granted token acquisition, project-ID validation, listener cleanup, and alert-data-to-route mapping.
- [ ] Run `npm.cmd test -- src/lib/notification-platform.test.ts`; expect missing-module failure.
- [ ] Run `npx.cmd expo install expo-notifications`; confirm Expo selects the SDK 56-compatible package and updates both lockfiles.
- [ ] Add the `expo-notifications` config plugin to `app.json` with `assets/images/android-icon-monochrome.png` and the FinCoach indigo notification color. Preserve the existing Android package and EAS project ID.
- [ ] Implement the adapter so tests do not import `expo-notifications` at module initialization. Configure a foreground handler that displays cloud notifications.
- [ ] Implement `NotificationBootstrap` under the authenticated app root. Register on login/foreground, subscribe to foreground refresh and notification-response deep links, and remove listeners on teardown.
- [ ] Update logout to deactivate the current installation before destroying the session, while still allowing logout to complete if deactivation is offline.
- [ ] Run `npm.cmd test -- src/lib/notification-platform.test.ts src/lib/alerts.test.ts`; expect pass.
- [ ] Run `npx.cmd expo install --check`; expect no incompatible Expo package version.

### Task 5: Implement authenticated device registration and safe account reassignment

**Files:**
- Create: `supabase/functions/_shared/http.ts`
- Create: `supabase/functions/_shared/supabase.ts`
- Create: `supabase/functions/register-device/index.ts`
- Create: `scripts/verify-alert-functions.mjs`
- Modify: `supabase/config.toml`

**Interfaces:**
- Accepts authenticated actions `register`, `refresh`, and `deactivate`.
- Derives the user from the bearer JWT; never trusts a request-body `user_id`.
- Reassigns the same globally unique token by deactivating its old owner before upserting it for the current owner.
- Returns `{ active, lastSeenAt }` without exposing other users or tokens.

- [ ] Write `scripts/verify-alert-functions.mjs` first and assert function presence, JWT-derived identity, no client service-role references, CORS/JSON handling, allowed actions, server-only environment variables, and no token logging.
- [ ] Run `node scripts/verify-alert-functions.mjs`; expect failure because the functions do not exist.
- [ ] Add shared JSON/CORS/error utilities and two Supabase client constructors: caller-scoped for authentication and service-role only inside Edge Functions.
- [ ] Implement `register-device`: validate Expo token format/platform/action, identify the user from JWT, atomically deactivate conflicting ownership, upsert current ownership, and clear stale errors.
- [ ] Implement `refresh` to update only the authenticated user's matching installation and `deactivate` to disable it on logout.
- [ ] Keep JWT verification enabled for `register-device` in `supabase/config.toml`.
- [ ] Run `node scripts/verify-alert-functions.mjs`; expect the registration assertions to pass and later-function assertions to remain clearly reported as pending failures.

### Task 6: Implement one idempotent Expo push delivery function

**Files:**
- Create: `supabase/functions/_shared/push-domain.test.ts`
- Create: `supabase/functions/_shared/push-domain.ts`
- Create: `supabase/functions/_shared/deliver-alerts.ts`
- Create: `supabase/functions/send-alert/index.ts`
- Modify: `scripts/verify-alert-functions.mjs`
- Modify: `supabase/config.toml`

**Interfaces:**
- Accepts `{ alertId }` only with the configured `x-fincoach-webhook-secret`.
- Atomically claims an alert from `pending|retryable` into `sending`; duplicate or active claims return success without sending again.
- Sends one minimal Expo message per active user device with source route data.
- Persists ticket IDs per device, aggregate status, attempt count, next retry, and sanitized error information.

- [ ] Write failing pure tests for Expo request chunking, minimum financial payloads, device-ID-to-ticket mapping, permanent versus retryable ticket errors, exponential retry delays, and aggregate delivery status.
- [ ] Run `npm.cmd test -- supabase/functions/_shared/push-domain.test.ts`; expect missing-module failure.
- [ ] Implement pure push helpers without Deno globals so Vitest can execute them.
- [ ] Implement one shared server-side delivery routine, then make `send-alert` call it using server-only `SUPABASE_SERVICE_ROLE_KEY`, optional `EXPO_ACCESS_TOKEN`, and `ALERT_WEBHOOK_SECRET`. Validate the custom secret with constant-time comparison and never log message contents or tokens.
- [ ] Load the authoritative alert and active devices from Supabase; if no active token exists, retain the inbox alert and record a non-retryable `no_active_device` state.
- [ ] Claim with a conditional update, send in Expo-supported batches, persist ticket IDs keyed by device UUID, deactivate immediate `DeviceNotRegistered` failures, and schedule only temporary failures for retry.
- [ ] Configure `send-alert` with gateway JWT verification disabled because it uses the private custom webhook secret; keep application-level secret verification mandatory.
- [ ] Extend the function verifier to assert secret validation, conditional claim, device filtering, Expo endpoint, ticket persistence, token deactivation, and sanitized errors.
- [ ] Run the pure push tests and `node scripts/verify-alert-functions.mjs`; expect pass for registration and send delivery.

### Task 7: Implement scheduled spending, savings, bill, retry, and receipt processing

**Files:**
- Create: `supabase/functions/_shared/due-domain.test.ts`
- Create: `supabase/functions/_shared/due-domain.ts`
- Create: `supabase/functions/process-alerts/index.ts`
- Modify: `scripts/verify-alert-functions.mjs`
- Modify: `supabase/config.toml`

**Interfaces:**
- Accepts a Cron request only with `x-fincoach-cron-secret`.
- Claims due occurrences and inserts deduplicated inbox alerts; it never sends pushes directly.
- Processes bill occurrences, savings deadlines, daily/weekly spending consistency, retryable alert deliveries, and outstanding Expo receipts.
- Advances a recurring bill only after the current occurrence is successfully claimed.

- [ ] Write failing pure tests for Malaysia/IANA timezone period windows, daily/weekly spending suppression when a transaction exists, savings lead-time calculation, completed-goal suppression, bill occurrence keys, recurrence advancement, retry eligibility, and receipt aggregation.
- [ ] Run `npm.cmd test -- supabase/functions/_shared/due-domain.test.ts`; expect missing-module failure.
- [ ] Implement dependency-free due helpers and deterministic occurrence keys.
- [ ] Implement bill processing with conditional claims on `next_trigger_at`, one-time completion, recurrence advancement from the original due-day anchor, and one alert insert per occurrence.
- [ ] Implement savings processing from existing `savings_goals`/`savings_contributions`, the user's lead days/time/timezone, and suppression for completed or deleted goals.
- [ ] Implement spending processing from existing `transactions`: daily/weekly period, configured weekday/time, and suppression when at least one transaction exists in that local period.
- [ ] Implement retry processing by calling the shared delivery routine directly inside `process-alerts`; do not make Edge-Function-to-Edge-Function HTTP calls or nested fan-out.
- [ ] Implement Expo receipt checks in bounded batches. Deactivate devices on permanent receipt errors, retain temporary failures for retry, and finalize aggregate alert delivery state.
- [ ] Configure `process-alerts` with gateway JWT verification disabled and mandatory custom Cron-secret verification.
- [ ] Extend the function verifier for all processors, existing-table column names/types, dedupe inserts, atomic reminder updates, bounded batches, and secret checks.
- [ ] Run due/push/domain tests and `node scripts/verify-alert-functions.mjs`; expect all assertions to pass.

### Task 8: Build the prototype-matched synchronized Alerts inbox

**Files:**
- Create: `src/components/notifications/alert-card.tsx`
- Create: `src/components/notifications/alert-filter-chips.tsx`
- Create: `src/app/alerts/index.tsx`
- Create: `src/lib/alert-ui.test.ts`
- Modify: `src/app/_layout.tsx`
- Modify: `src/app/(app)/index.tsx`
- Modify: `src/app/(app)/profile.tsx`

**Interfaces:**
- Produces `/alerts` with All, Insights, and Alerts filters and Today/Yesterday/Earlier groups.
- Produces unread count/dot, mark-all-read, read-on-open, synchronized swipe dismissal, and safe source deep links.
- Produces a settings action to `/alerts/settings` and dashboard/profile bell navigation.

- [ ] Write a failing structural UI test asserting the prototype page bar `Alerts`, three filter labels, date groups, icon/title/message/time, unread dot, swipe/fallback dismissal, Mark all as read, settings action, and loading/error/empty/permission-disabled states.
- [ ] Write failing routing assertions for the root stack and dashboard/profile bell navigation.
- [ ] Run `npm.cmd test -- src/lib/alert-ui.test.ts`; expect failure because the routes/components do not exist.
- [ ] Implement the prototype-aligned inbox using existing FinCoach typography, colors, spacing, and card shapes. Do not substitute a generic settings-list design.
- [ ] Load synchronized alerts on focus and pull-to-refresh. Subscribe to the signed-in user's alert changes while active, and clean up the Realtime channel on unmount/user change.
- [ ] Mark cards read before deep linking, dismiss through `dismissed_at`, expose an accessible Dismiss action in addition to swipe, and use `/alerts` when a source was deleted.
- [ ] Connect the existing dashboard/profile notification actions and render a real unread indicator.
- [ ] Run the focused UI, alerts client, and domain tests; expect pass.

### Task 9: Build separately configurable notification settings

**Files:**
- Create: `src/components/notifications/settings-card.tsx`
- Create: `src/components/notifications/time-field.tsx`
- Create: `src/app/alerts/settings.tsx`
- Modify: `src/lib/alert-ui.test.ts`

**Interfaces:**
- Produces independent Budget, Savings, Spending, and Bills cards.
- Produces Android permission status/open-settings behavior.
- Persists each control to `notification_preferences` and rolls back failed optimistic updates.

- [ ] Extend the failing UI test for the permission card, Budget enable plus fixed 80%/100% explanation, Savings enable/lead days/time/milestones, Spending enable/daily-weekly/weekday/time, Bills enable/default lead days/default time, and Manage reminders action.
- [ ] Run `npm.cmd test -- src/lib/alert-ui.test.ts`; expect failure for the settings route.
- [ ] Implement a pure React Native time field/modal and weekday/frequency chips; do not add a native picker package.
- [ ] Implement preference loading/default creation, independent controls, optimistic save with exact rollback, visible retryable errors, and disabled child controls when their notification type is off.
- [ ] Display permission denial without disabling the synchronized in-app inbox and link to Android application settings through the platform adapter.
- [ ] Run UI, adapter, client, and domain tests; expect pass.

### Task 10: Build synchronized manual bill-reminder CRUD

**Files:**
- Create: `src/components/notifications/reminder-card.tsx`
- Create: `src/app/alerts/reminders.tsx`
- Create: `src/app/alerts/reminders/manage.tsx`
- Modify: `src/app/_layout.tsx`
- Modify: `src/lib/alert-ui.test.ts`

**Interfaces:**
- Produces Upcoming, Disabled, and Completed reminder states.
- Produces create/edit form fields for title, optional RM amount, due date/time, lead days, and recurrence.
- Produces enable/disable and confirmed delete actions synchronized through Supabase.

- [ ] Extend the failing UI test for reminder groups/cards, Add reminder, amount/due/recurrence summaries, empty/error/offline states, edit, enable/disable, confirmed delete, and create/edit route registration.
- [ ] Extend it for title, optional amount, date, time, lead days, recurrence, validation, saving state, and preserved input after failure.
- [ ] Run `npm.cmd test -- src/lib/alert-ui.test.ts`; expect failure for reminder routes.
- [ ] Implement the list using prototype cards and status grouping. Refresh on focus so Device B sees Device A changes.
- [ ] Implement the form by reusing `src/components/savings/date-field.tsx` and the pure React Native `time-field.tsx`; calculate `next_trigger_at` from the selected timezone and preference defaults.
- [ ] Confirm destructive delete, handle stale/expired dates explicitly, and keep form data after offline/backend errors.
- [ ] Run UI, alerts client, and reminder-domain tests; expect pass.

### Task 11: Connect automatic budget and savings alert creation to existing writes

**Files:**
- Create: `src/lib/alert-events.test.ts`
- Create: `src/lib/alert-events.ts`
- Modify: `src/app/transactions/manage.tsx`
- Modify: `src/app/transactions/review.tsx`
- Modify: `src/app/savings/[goalId].tsx`

**Interfaces:**
- Produces `emitBudgetAlertsAfterTransactionChange` and `emitSavingsMilestonesAfterContribution`.
- Inserts only newly crossed, preference-enabled, idempotent alert rows.
- Creates Budget navigation data for overall/category sources and Savings navigation data for the goal.
- Never rolls back a successfully saved transaction/contribution because push/inbox alert creation failed; instead surfaces a non-blocking synchronization warning and permits retry.

- [ ] Write failing event tests for disabled preferences, expense-only budget evaluation, overall/category 80% and 100% crossings, direct 100% jump precedence, transaction edit category/month changes, and dedupe-conflict success.
- [ ] Write failing savings tests for disabled savings/milestones, multiple newly crossed milestones, 100% completion, and no duplicates after refetch/retry.
- [ ] Run `npm.cmd test -- src/lib/alert-events.test.ts`; expect missing-module failure.
- [ ] Implement focused event orchestration over existing `budget.ts`, `transactions.ts`, `savings.ts`, and `alerts.ts` boundaries; keep the crossing math in `alerts-domain.ts`.
- [ ] Invoke budget evaluation after successful manual and receipt transaction create/update paths using the prior and current transaction snapshots.
- [ ] Invoke savings milestone evaluation after a successful contribution using pre/post goal amounts.
- [ ] Keep deadline/spending/bill alerts exclusively in `process-alerts` so the mobile app does not create duplicate schedules.
- [ ] Run event, transaction, budget, savings, alerts, and domain tests; expect pass.

### Task 12: Configure runtime deployment and verify the complete module

**Files:**
- Create: `docs/alert-reminder-deployment.md`
- Modify: `.env.example`
- Modify: `docs/acceptance-tests.md`
- Modify: `design-qa.md`

**Interfaces:**
- Documents exact FCM v1, Expo, Supabase secrets, Vault, alert webhook, Cron, Edge Function deployment, APK rebuild, and Honor 200 validation steps.
- Leaves no service credentials in tracked source files.

- [ ] Add deployment instructions for Android FCM v1 credentials, the existing EAS project, `EXPO_ACCESS_TOKEN`, `ALERT_WEBHOOK_SECRET`, `ALERT_CRON_SECRET`, Vault `alert_webhook_url`/`alert_webhook_secret`, function deployment, and a short-interval Cron request to `process-alerts`.
- [ ] Include exact verification queries for four-table existence, RLS enabled, policies, active device registration, Cron job state, alert dedupe, delivery status, and no cross-user reads. Secret values must be supplied interactively or through environment variables, never written into the guide.
- [ ] Apply the migration to the intended Supabase project only after confirming the linked project reference; run `node scripts/verify-alert-schema.mjs` before and after.
- [ ] Deploy `register-device`, `send-alert`, and `process-alerts` with their intended JWT configuration; run `node scripts/verify-alert-functions.mjs`.
- [ ] Configure the database alert-insert webhook/Vault path and Cron invocation, then create one server-side test alert and verify exactly one push attempt per active device.
- [ ] Run `npm.cmd test`; expect the complete mobile/shared test suite to pass.
- [ ] Run `npm.cmd run typecheck`, focused/full ESLint, `npx.cmd expo install --check`, `node scripts/verify-alert-schema.mjs`, and `node scripts/verify-alert-functions.mjs`; expect pass.
- [ ] Run `npx.cmd expo export --platform android` to a temporary output directory; expect a successful bundle.
- [ ] Synchronize canonical source into `C:\fcb` while excluding `node_modules`, `.expo`, build output, and Git metadata; rebuild the Android development/release APK because the native notification plugin changed.
- [ ] On the Honor 200, verify permission grant/denial, foreground/background/closed push delivery, tap routes, Budget 80%/100%, Savings 25/50/75/100% and deadline, daily/weekly spending suppression, one-time/recurring bills, read/dismiss synchronization, disabled type suppression, and stale-token logout behavior.
- [ ] Test a second previously registered device: cloud push must arrive while FinCoach is closed, and preference/reminder/read/dismiss changes must match after refresh.
- [ ] Record prototype comparison and physical-device results in `design-qa.md` and `docs/acceptance-tests.md`. Do not mark the module complete if closed-app push, deduplication, or RLS isolation is unverified.

## Plan self-review

- FRAR-01 maps to spending consistency scheduling; FRAR-02 maps to 80%/100% budget alerts; FRAR-03 maps to savings deadline and bill reminders; FRAR-04 maps to separate time/type/frequency settings.
- Every approved automatic rule, cross-device requirement, cloud-push path, prototype screen, error state, security boundary, and Honor 200 acceptance case maps to an explicit task.
- The database keeps four approved entities. Per-device Expo ticket/receipt state remains server-controlled JSONB on `alerts`, avoiding an unapproved fifth entity while supporting receipt checks.
- One alert-insert path owns push delivery. Cron and client hooks create deduplicated alert rows but do not send separately.
- Webhook and Cron processing reuse a shared delivery routine in-process; they do not create nested Edge Function call chains that are subject to the 2026 per-trace rate limit.
- Registration, webhook, and Cron authorization are distinct: caller JWT for device registration; private custom secrets for server-to-server delivery and processing.
- Client, domain, Edge Function, migration, UI, and device interfaces use consistent route/table/function names across tasks.
- The plan contains no implementation placeholders and no deferred behavior required for module acceptance; only the user-approved ERD/thesis update remains deferred.
- Later AI, reports, export, and backup modules remain out of scope.
