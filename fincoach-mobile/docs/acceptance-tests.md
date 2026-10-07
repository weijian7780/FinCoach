# FinCoach User Management Acceptance Tests

Use this checklist after the Supabase `FinCoach` project exists and `.env` is filled.

## Auth

- New email signup creates an auth user.
- If Supabase returns a session after signup, the app continues to profile setup.
- If Supabase returns no session after signup, the app shows the check-email screen.
- Existing email/password user can log in.
- Google OAuth opens the provider flow and returns to FinCoach through `/auth/callback`.
- Forgot password sends a reset email.
- Reset-password link opens `/auth/reset-password` and updates the password.
- Logout clears the Supabase session and returns to login.

## Profile And Consent

- New user can save basic profile details.
- Consent can be set to `unset`, `granted`, `denied`, or `withdrawn`.
- Profile updates persist after app reload.
- User can view their email, profile status, onboarding status, and consent status.

## RLS

- User A can read and update only their own row in `public.profiles`.
- User A cannot read User B's `public.profiles` row.
- User A cannot update User B's `public.profiles` row.

# Savings Goal Management Acceptance Tests

Run the Savings migration before using this checklist:
`supabase/migrations/20260712150713_complete_savings_goal_management.sql`.

## FRSG-01 — Goals And Deadlines

- Authenticated user can create a goal with a purpose, positive target amount, and future deadline.
- Empty purpose, zero/negative target, missing deadline, and today/past deadline are rejected.
- Newly created goal appears on the Savings list and dashboard summary.

## FRSG-02 — Contributions And History

- User can add a positive contribution dated today or earlier with an optional note.
- Contribution appears in newest-first history after saving.
- Future-dated, zero/negative, and over-target contributions are rejected.
- Deleting a contribution removes it from history and recalculates the goal total.

## FRSG-03 — Progress And Remaining Amount

- Goal card and detail screen show saved amount, target amount, progress percentage, and remaining amount.
- Progress updates immediately after adding or deleting a contribution.
- Reached, overdue, almost-there, on-track, and needs-attention statuses display correctly.

## FRSG-04 — Saving Suggestions

- Active goal shows a deterministic weekly saving suggestion based on remaining amount and days left.
- Reached goal shows a completion message.
- Overdue goal advises extending the deadline or updating the target.

## FRSG-05 — Update And Delete

- User can update purpose, target amount, and deadline.
- Target cannot be reduced below the saved amount.
- User can delete a goal only after confirming the destructive action.
- Deleting a goal also deletes its contribution history.

## Savings RLS And Integrity

- User A can read, create, update, and delete only User A's goals.
- User A can read, add, and delete contributions only for User A's goals.
- Direct client updates to `current_amount` are rejected.
- Database trigger keeps `current_amount` equal to the contribution sum.
- Concurrent contributions cannot make the saved amount exceed the target.

# Budget And Category Limit Management Acceptance Tests

Run `supabase/migrations/20260713060910_complete_budget_category_limit_management.sql` before using this checklist.

## FRBL-01 — Custom Expense Categories

- User can create a custom expense category with a unique name, icon, and colour.
- User can update and delete only their own custom categories.
- System categories remain readable but cannot be edited or deleted.
- Two users may use the same custom-category name, while one user cannot create duplicate names with different letter casing.

## FRBL-02 — Monthly And Category Limits

- User can create one positive overall budget for a selected calendar month.
- User can add one positive limit per selected expense category.
- Combined category limits cannot exceed the overall monthly budget.
- Existing legacy category limits receive a compatible monthly parent without changing their bigint IDs.

## FRBL-03 — Remaining Budget And Progress

- Budget tab shows overall and category limit, used amount, remaining amount, percentage, and progress.
- Used amount reflects persisted expense transactions in the selected month and category. When none exist, the screen states `No transactions recorded`.
- Navigating between months never mixes parent budgets or category limits.
- Current-month Home preview reads `monthly_budgets`, not the Financial Profile monthly allowance.

## FRBL-04 — Limit Detection

- Usage below 80% displays `Within Limit`.
- Usage from 80% through 99.99% displays `Approaching Limit`.
- Usage equal to the limit displays `Limit Reached`.
- Usage above the limit displays `Exceeded`, keeps the percentage uncapped, and shows the exceeded amount.

## FRBL-05 — Update And Delete

- User can update the overall budget and each category limit.
- Overall budget cannot be reduced below currently allocated category limits.
- Removing a category limit persists after reload.
- Deleting a monthly budget requires confirmation and cascades its category limits.

## Budget RLS, Device, And Persistence

- User A cannot read or modify User B's monthly budgets, category limits, or custom categories.
- Category-limit writes cannot reference another user's custom category.
- Budget and custom-category changes persist after app reload.
- Overview, forms, icon picker, error messages, and destructive confirmations remain readable and scrollable on the Honor 200.

# Alert and Reminder Management Acceptance Tests

Run `supabase/migrations/20260715033911_complete_alert_reminder_management.sql` and follow `docs/alert-reminder-deployment.md` first.

## FRAR-01 — Spending Check-ins

- User can enable or disable spending reminders separately from all other types.
- Daily and weekly frequency, weekly day, and reminder time persist across devices.
- A due period creates one alert only when no transaction exists in that period.
- The same period never creates a duplicate alert after Cron retry.

## FRAR-02 — Budget Alerts

- Expense crossing 80% creates one approaching-limit alert for the overall budget and applicable category limit.
- Direct jump from below 80% to at least 100% creates the exceeded alert, not both alerts.
- Editing a transaction correctly evaluates its old and new month/category buckets.
- Income transactions do not create budget alerts.
- Disabling Budget alerts suppresses new budget alerts only.

## FRAR-03 — Savings And Bill Reminders

- Contributions create one synchronized milestone alert at 25%, 50%, 75%, and 100% when newly crossed.
- Savings deadline uses configured lead days, time, and timezone, with one deduplicated occurrence.
- User can create, retrieve, update, enable/disable, and delete a bill reminder.
- Weekly, monthly, and yearly bills advance from the saved recurrence anchor without duplicate occurrences.
- A one-time bill is disabled after its occurrence is claimed.

## FRAR-04 — Separate Settings

- Budget, Savings, Spending, and Bills each have an independent enabled switch.
- Savings lead time, time, and milestones persist.
- Spending frequency/day/time persists.
- Bill default lead time and time prefill a new reminder.
- Settings from Device A appear on Device B after refresh without using AsyncStorage as the source of truth.

## Inbox And Cross-device State

- All, Insights, and Alerts filters show the correct alert kind.
- Alerts group into Today, Yesterday, and Earlier.
- Opening one alert marks it read; Mark all read updates all unread alerts.
- Swipe dismissal removes the alert and synchronizes dismissal across devices.
- Supabase Realtime refreshes the open inbox when an alert changes.
- Permission-denied state keeps the inbox usable and links to system notification settings.

## Cloud Push And Security

- Rebuilt Honor 200 APK registers one active Expo push token after login and permission grant.
- Foreground, background, and fully closed app each receive the expected push.
- One alert produces no more than one push attempt per active device.
- DeviceNotRegistered deactivates the stale token.
- Logout deactivates the current device token.
- User A cannot read or modify User B's preferences, reminders, alerts, or device rows.
- Service-only claim functions cannot be executed by `anon` or `authenticated` roles.

# Financial Report and Analytics Acceptance Tests

Apply `supabase/migrations/20260716025356_complete_financial_report_analytics.sql` only after reconciling the project's local and remote migration history. Do not use `supabase db push` while that history remains mismatched.

## Real Financial Data

- Reports opens with a current-month preview calculated from the signed-in user's real Supabase transactions.
- No static or mock financial amount appears in summary cards, charts, or empty states.
- One income and two expenses produce the correct Income, Expenses, Net Balance, and transaction count.
- Manual and receipt-derived transactions contribute identically according to their category type.
- Category filtering changes summary, category, and trend values without changing the clearly overall Budget vs Actual calculation.
- An empty period displays `No transactions in this period` while keeping saved budget and savings context visible.

## Period And Date Handling

- This month, Last month, and 3 months use Malaysia-local calendar boundaries.
- A custom `YYYY-MM-DD` range includes transactions on both start and end dates.
- Invalid dates and a start date after the end date prevent generation with a field-level message.
- Testing between 00:00 and 07:59 Malaysia time does not shift the report to the previous UTC date.
- A multi-month report inserts zero-valued trend columns for months without transactions.

## Budget, Savings, And Charts

- Budget vs Actual sums monthly budget limits intersecting the selected period.
- Spending below the budget shows the correct amount and percentage remaining.
- Spending above the budget shows the true uncapped percentage and exceeded amount while capping only the visual bar.
- Savings Progress totals current and target amounts from the user's savings goals.
- Category and monthly charts include readable RM and percentage labels and remain understandable without relying on colour.
- All sections remain readable and scrollable on the Honor 200 at the default display size.

## Report History And Failure States

- Tapping Generate Report creates one owner-scoped `reports` metadata row with the selected period and report type.
- Pull-to-refresh recalculates current values without inserting a duplicate history row.
- If history insertion fails, the calculated report remains visible with a non-blocking history warning.
- If any financial source query fails, the app does not calculate a misleading partial report and shows Retry.
- A failed refresh keeps the last successful report visible.
- User A cannot read or insert report-history rows for User B; anonymous access is denied.
- Recent Reports is ordered newest first and limited to 10 rows in the screen.

## Module Boundaries

- No AI-generated insight, RAG request, LLM call, or FastAPI request is made by Reports.
- No CSV/PDF export or backup behavior is included in Reports.
- Report generation does not modify transactions, budgets, category limits, savings goals, or profile records.

# Financial Data Export and Backup Acceptance Tests

Apply `supabase/migrations/20260716131958_complete_financial_data_export_backup.sql` after reconciling the project's local and remote migration history.

## Export Files

- CSV export uses the signed-in user's real data and correctly escapes commas, quotes, line breaks, and Unicode text.
- Selecting Transactions, Budgets, Savings, and Reports produces four normalized `export_contents` rows and includes only those selected sections.
- Start and end dates are inclusive; invalid or reversed dates prevent generation.
- PDF generation creates a readable formatted report with escaped user-entered HTML.
- Android native sharing can save or share both `text/csv` and `application/pdf`.
- Repeat CSV export, PDF export, native share, and save on the Honor 200 physical device.

## Private Cloud Backup

- Back up now creates one manual metadata row, exact schema-version-1 JSON, SHA-256 checksum, byte size, and private Storage object.
- Automatic backup runs after authenticated bootstrap or foreground activation only when enabled and no completed automatic backup exists within 24 hours.
- Concurrent foreground triggers create no more than one in-flight automatic backup per user.
- Automatic retention keeps the latest five completed automatic backups.
- Manual and failed backups are never deleted by automatic retention.
- Deleting a backup removes the private Storage object before its metadata row.
- User A cannot list, download, update, or delete User B's backup metadata or Storage objects.

## Restore Integrity And Atomicity

- A size mismatch, corrupt checksum, malformed JSON, unsupported schema version, or cross-user document is blocked before restore.
- The restore warning clearly states that current financial data will be replaced and requires destructive confirmation.
- A valid full-data round trip restores profile data, custom categories, transactions, budgets, category limits, savings goals and contributions, reports, notification preferences, reminders, and alerts.
- Restore is atomic: an insertion failure leaves the user's current financial data unchanged.
- Restore leaves authentication, default categories, receipt objects, device tokens, `auto_backup_enabled`, export history, and backup history unchanged.
- The latest restore status and completion time are recorded on the selected backup.
- Repeat manual backup, delete, corruption rejection, and successful restore on the Honor 200 physical device.

# AI Financial Coaching Acceptance Tests

Deploy `supabase/migrations/20260717021519_complete_ai_financial_coaching.sql`, ingest the
approved finance corpus, configure the FastAPI server, and set
`EXPO_PUBLIC_FINCOACH_API_URL` before running this section.

## Physical Device And Connectivity

- On the Honor 200, a LAN URL using the PC IPv4 address reaches `/health`; `localhost` is not used.
- The same flows work against the deployed HTTPS API when the production URL replaces the LAN URL.
- The Coach tab opens the real chat UI, stays readable above the Android keyboard, and scrolls to the latest message.
- The production Android bundle contains no Supabase service-role key, LLM key, provider key, or backend `.env` value.

## Authentication And Isolation

- Signed-out, missing-token, malformed-token, anonymous, and expired-token calls are rejected without spending an LLM request.
- A mobile `401` triggers one Supabase refresh and one retry; another `401` shows the sign-in message without looping.
- User A cannot list, rename, delete, or read User B's conversations, messages, or retrieval evidence.
- Starting, renaming, selecting, and deleting multiple conversations persists correctly after app restart.

## Grounded Coaching

- BGE-M3 retrieval returns only references above the configured similarity threshold and shows available source labels.
- The LLM response references the signed-in user's recorded allowance, expenses, category limits, budgets, and savings goals correctly.
- Missing financial records are stated as unavailable; no bank balance, transaction, budget, or goal is invented.
- A malicious instruction placed inside a knowledge document is treated as untrusted reference data and is not followed.
- Advice ends with an educational-not-financial-advice reminder and remains bounded by the configured output limit.

## Reliability And Safeguards

### Preferences Income Entry (2026-10-02)

- Preferences calls the amount Expected Monthly Allowance / Income. Updating it alone creates no financial transaction.
- Record monthly income saves unsaved Preferences only after Save & continue, then opens an editable Income draft; cancel creates nothing.
- All six source types are supported; Mixed/Other require an actual income source. No available income category means the user must select one, never an expense category.
- Confirm RM2,000 through the shortcut and add RM500 manually in the same report period: income RM2,500. With RM300 expenses, net balance RM2,200.
- Edit the RM2,000 entry to RM1,900: income RM2,400. Delete it: income RM500. A changed expected amount leaves those totals unchanged.
- Similar income entries show a review warning. Two genuine equal installments are allowed after Record another payment. A failed similarity check offers Retry check/Cancel before writing.
- Double taps, a lost save response, and a retry use the same draft UUID. Changed values cannot overwrite an already-saved payment. Receipt images and stored IDs survive transaction edits.
- Verify keyboard, scrolling, safe-area padding, and every action on Honor 200 and a small Android screen.
- Evidence status: automated domain/persistence/report tests and Android bundle export verified locally. Live authenticated Supabase writes and updated-screen device interaction remain unverified; no test account was supplied, and the connected phone has an existing standalone release rather than the updated source build.


- Sending the same client message ID twice returns the existing completed reply or a safe `409`; it never creates two assistant replies.
- Airplane mode or an unreachable API shows a retry state without deleting previously loaded messages.
- Provider failure returns safe `502` copy; provider timeout returns safe `504` copy; neither exposes provider/database exception text.
- Missing LLM configuration never echoes the constructed prompt or private financial context.
- Per-minute and daily usage limits return `429`, persist across backend restarts, and do not rely on mobile state.
- Every backend response contains a bounded `X-Request-ID`; logs contain route, status, and latency but no token, prompt, message body, or financial context.
