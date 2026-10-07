# Alert and Reminder Management Design

Date: 2026-07-15

## Objective

Complete the FinCoach Alert and Reminder Management module against functional requirements FRAR-01 through FRAR-04 while preserving the existing Expo, Supabase, Budget, Savings, Transaction, and root FinCoach UI architecture.

## Approved scope

The module will provide:

- FRAR-01: configurable daily or weekly reminders to record spending;
- FRAR-02: one pre-limit budget warning at 80% usage and one post-limit notification at 100% or above;
- FRAR-03: savings deadline reminders, savings milestone notifications, and manually managed bill due-date reminders;
- FRAR-04: separate settings for Budget, Savings, Spending, and Bill notification types, including the relevant time, frequency, lead time, and enabled state;
- real Android cloud push delivery when FinCoach is closed;
- synchronized notification preferences, reminder records, alert history, read state, and dismissal state across a user's devices;
- create, retrieve, update, enable/disable, and delete operations for manual bill reminders;
- a prototype-matched Alerts inbox with All, Insights, and Alerts filters.

The approved delivery architecture uses `expo-notifications`, Expo Push Service, Supabase PostgreSQL, Supabase Cron, and focused Supabase Edge Functions. Supabase is the cross-device source of truth. Each registered installation stores an Expo push token so the server can deliver an alert even when the application is closed.

## UI source of truth

The root files in `G:\My Drive\FYP 1 & 2\FinCoach UI` are the visual authority. Nested folders are not used.

The implementation follows:

- the `Notifications` screen in `screens_extra.jsx`;
- `NOTIFICATIONS` sample grouping and alert treatments in `lib.jsx`;
- the dashboard notification bell and unread indicator from `lib.jsx` and `screens_app.jsx`;
- the existing FinCoach profile-row, card, chip, toggle, form, and page-header patterns.

The visual system remains Hanken Grotesk, FinCoach indigo, warm off-white surfaces, rounded white cards, tonal icons, compact filter chips, prototype spacing, grouped date sections, unread indicators, and swipe-to-dismiss behavior.

Necessary additions remain within the same visual system:

- an unread count and Mark all as read action;
- a notification-settings entry from the Alerts screen;
- Android permission status and recovery guidance;
- separate settings cards for Budget, Savings, Spending, and Bills;
- a bill-reminder list and add/edit form;
- loading, empty, disabled, permission-denied, offline, retry, and validation states.

## Explicit non-goals

- No AI-generated notification text or financial advice. Alert messages are deterministic and auditable.
- No FastAPI dependency. The existing FastAPI service remains responsible for PaddleOCR and later AI/RAG work.
- No bank integration, bill-provider integration, or automatic bill inference from transaction history.
- No SMS, email, WhatsApp, or marketing notifications.
- No notification advertising or unrelated engagement messaging.
- No update to the draw.io ERD in this implementation cycle. The working Supabase schema is documented here and the ERD will be revised separately later.
- No duplicate local Android schedule for a server-delivered cloud notification. This prevents the same reminder appearing twice.

## Existing-state findings

The current application has:

- a non-interactive dashboard notification icon;
- no Alerts or Reminder routes, client service, domain model, tests, or database migration;
- no `expo-notifications` dependency or config plugin;
- no push-token registration or notification response handler;
- no Supabase Edge Function or Cron job for reminder delivery;
- Budget, Savings, and Transaction modules that already expose the source data needed for alert rules;
- a prototype Alerts inbox with All, Insights, and Alerts filters, Today/Earlier groups, unread treatment, and dismissal;
- a thesis ALERT entity that does not yet cover preferences, schedules, recurrence, or device tokens.

## Module boundaries

Alert and Reminder Management owns:

- notification preferences;
- manual bill reminder CRUD;
- alert creation, history, read state, and dismissal;
- device push-token registration and deactivation;
- message templates and deduplication keys;
- due-reminder processing;
- Expo push delivery and receipt handling;
- notification-tap routing.

The Budget module continues to calculate budget usage and reports a threshold-crossing event. The Savings module continues to calculate goal progress and reports milestone changes. The Transaction module continues to store user transactions. These modules do not own delivery settings, push tokens, notification history, or notification UI.

## Data architecture

The schema below is the approved working implementation model. It is intentionally separated into four entities so preferences, scheduled work, delivered history, and device registrations do not become one nullable mixed-purpose table.

### `notification_preferences`

One row per user stores independently configurable notification behavior:

- `user_id uuid primary key references auth.users(id) on delete cascade`;
- `budget_enabled boolean not null default true`;
- `savings_enabled boolean not null default true`;
- `savings_lead_days smallint not null default 7`;
- `savings_reminder_time time not null default '09:00'`;
- `savings_milestones_enabled boolean not null default true`;
- `spending_enabled boolean not null default true`;
- `spending_frequency text not null default 'weekly'`;
- `spending_weekday smallint null`;
- `spending_reminder_time time not null default '20:00'`;
- `bills_enabled boolean not null default true`;
- `default_bill_lead_days smallint not null default 3`;
- `default_bill_reminder_time time not null default '09:00'`;
- `timezone text not null default 'Asia/Kuala_Lumpur'`;
- `created_at timestamptz not null default now()`;
- `updated_at timestamptz not null default now()`.

Constraints limit lead days, weekdays, allowed frequencies, and timezone length. Budget thresholds remain fixed at 80% and 100% so historical alert meaning is consistent.

### `reminders`

Manual bill reminders are user-owned scheduled records:

- `id uuid primary key default gen_random_uuid()`;
- `user_id uuid not null references auth.users(id) on delete cascade`;
- `type text not null default 'bill'`;
- `title text not null`;
- `amount numeric(12,2) null`;
- `due_at timestamptz not null`;
- `lead_days smallint not null`;
- `recurrence text not null default 'none'`;
- `enabled boolean not null default true`;
- `next_trigger_at timestamptz null`;
- `last_triggered_at timestamptz null`;
- `created_at timestamptz not null default now()`;
- `updated_at timestamptz not null default now()`.

Initial recurrence values are `none`, `weekly`, `monthly`, and `yearly`. Pure date logic advances recurring dates without drifting when months have different lengths. Disabling a reminder clears it from due processing without deleting its history.

### `alerts`

One table stores the synchronized in-app inbox and delivery record:

- `id uuid primary key default gen_random_uuid()`;
- `user_id uuid not null references auth.users(id) on delete cascade`;
- `type text not null`;
- `kind text not null` with `alert` or `insight`;
- `title text not null`;
- `message text not null`;
- optional source references for a budget, savings goal, or reminder;
- `dedupe_key text not null`;
- `scheduled_for timestamptz null`;
- `delivered_at timestamptz null`;
- `read_at timestamptz null`;
- `dismissed_at timestamptz null`;
- `delivery_status text not null default 'pending'`;
- `delivery_error text null`;
- `created_at timestamptz not null default now()`.

A unique `(user_id, dedupe_key)` constraint prevents duplicate threshold, milestone, daily/weekly, and due-date alerts. Dismissal is a synchronized soft state so notification history remains auditable and delivery retries cannot recreate a dismissed card.

### `user_devices`

One row per application installation stores push delivery information:

- `id uuid primary key default gen_random_uuid()`;
- `user_id uuid not null references auth.users(id) on delete cascade`;
- `expo_push_token text not null unique`;
- `platform text not null`;
- `device_name text null`;
- `active boolean not null default true`;
- `last_seen_at timestamptz not null default now()`;
- `last_error text null`;
- `created_at timestamptz not null default now()`;
- `updated_at timestamptz not null default now()`.

Token refresh uses authenticated registration through a focused Edge Function. The function verifies the caller's Supabase JWT, deactivates the same installation token under any previous account, and upserts it for the current user. This prevents a shared device from continuing to receive the previous user's financial alerts. Logout deactivates the installation for the current account. Invalid or unregistered-device responses deactivate stale tokens rather than repeatedly retrying them.

### RLS and Data API access

- RLS is enabled on all four public tables.
- Authenticated users can select and manage only rows where `user_id = auth.uid()`.
- Update policies use both `USING` and `WITH CHECK`.
- Preferences use owner-only select, insert, and update.
- Reminder CRUD is owner-only.
- Alert dismissal is the module's synchronized logical-delete operation: owners may select their alerts and update only `read_at` and `dismissed_at`. Delivery fields remain server-controlled, and the normal mobile client is not granted arbitrary alert-row updates.
- Device-token registration goes through an authenticated Edge Function so a token can be safely reassigned after an account change; token enumeration across users is forbidden.
- The mobile app contains no Supabase service-role key and no Expo access token.
- Server secrets are stored only as Supabase Edge Function secrets or in Supabase Vault where required by Cron invocation.

## Notification rules

### Spending consistency

- Users choose daily or weekly frequency and a preferred time.
- The due processor creates at most one alert for each configured period.
- The reminder is suppressed when the user has already recorded a transaction during that period.

### Budget thresholds

- `Approaching limit` fires once when uncapped usage crosses from below 80% to at least 80% but below 100%.
- `Limit exceeded` fires once when usage reaches or exceeds 100%.
- Overall and category budget sources use separate deduplication keys.
- Editing or deleting a transaction does not repeatedly regenerate a threshold alert already recorded for the same budget period.

### Savings deadlines and milestones

- Deadline reminders use the user's configured lead days and reminder time.
- Milestones fire once at 25%, 50%, 75%, and 100% progress.
- Updating a goal deadline changes future due processing without rewriting historical alerts.
- Deleting a savings goal prevents new reminders while preserving already delivered history unless the user deletes that history.

### Bill reminders

- Users create a bill title, optional amount, due date/time, lead days, and recurrence.
- One-time reminders become completed after delivery.
- Recurring reminders advance their next due and trigger timestamps only after the current occurrence is successfully claimed.
- Update, disable, and delete operations immediately affect subsequent Cron processing.

## Cloud delivery architecture

### Device registration

After authenticated login, the mobile application:

1. creates Android notification channels;
2. checks and requests notification permission after explaining its purpose;
3. obtains the Expo push token using the configured EAS project ID;
4. invokes the authenticated device-registration Edge Function, which safely upserts the token into `user_devices`;
5. refreshes `last_seen_at` when the application returns to the foreground.

Permission denial does not block the in-app inbox. The settings screen explains that cloud delivery is disabled and provides a route to Android application settings.

### Immediate alert delivery

Budget and savings integration hooks create an `alerts` row using an idempotent dedupe key. An insert webhook invokes the push Edge Function. The function loads the user's active device tokens and sends one Expo push message to each active installation.

### Scheduled delivery

Supabase Cron invokes the due-reminder Edge Function on a short recurring interval. The function:

1. finds due bill, savings, and spending reminders in Malaysia-aware user timezones;
2. claims each occurrence atomically;
3. inserts a deduplicated alert row;
4. advances recurrence or marks a one-time occurrence complete.

The alert insert then follows the same webhook-to-push path as an immediate alert. Atomic due-occurrence claiming and the alert unique constraint prevent concurrent Cron runs from creating the same occurrence twice. The push Edge Function separately claims the alert's delivery state before sending, preventing webhook retries from delivering it twice. A scheduled retry worker processes only retryable failed rows through the same claimed delivery path.

### Push response handling

- Tapping a budget alert opens the relevant Budget view.
- Tapping a savings alert opens the related savings goal.
- Tapping a bill reminder opens the reminder detail/edit screen.
- Tapping a spending reminder opens Add Transaction.
- Foreground notifications remain visible through the configured notification handler.
- Push receipts are checked server-side; invalid tokens are deactivated and temporary errors remain retryable.

## Mobile application architecture

### Routes

- `src/app/alerts/index.tsx`: prototype-matched alert inbox.
- `src/app/alerts/settings.tsx`: separate notification-type settings.
- `src/app/alerts/reminders.tsx`: manual bill-reminder list.
- `src/app/alerts/reminders/manage.tsx`: create/edit bill reminder.

The root stack registers these routes with hidden native headers. The dashboard bell opens `/alerts` and displays an unread dot derived from synchronized alert state.

### Domain and client layers

Focused pure domain functions provide:

- budget threshold crossing and dedupe-key creation;
- savings milestone crossing and deadline calculations;
- daily and weekly period keys;
- recurrence advancement;
- bill-reminder validation;
- grouped alert sections and filter classification;
- timezone-safe display formatting.

The Supabase client layer provides:

- preference retrieval and upsert;
- reminder list, create, update, enable/disable, and delete;
- alert list, unread count, mark read, mark all read, dismiss, and delete;
- device-token registration, refresh, and deactivation;
- idempotent alert creation for approved integration hooks.

Notification SDK calls remain in a focused platform adapter so domain logic and UI tests do not import native modules.

### Alerts inbox

- prototype page bar titled `Alerts`;
- All, Insights, and Alerts filter chips;
- Today, Yesterday, and Earlier groups;
- icon, title, message, time, and unread treatment;
- tap-to-read and source deep link;
- swipe-to-dismiss with accessible fallback action;
- Mark all as read;
- settings action;
- loading, retry, permission-disabled, filtered-empty, and no-alert states.

### Notification settings

- Android permission status card;
- Budget card with independent enable switch and fixed 80%/100% explanation;
- Savings card with enable switch, lead days, reminder time, and milestone switch;
- Spending card with enable switch, daily/weekly frequency, optional weekday, and time;
- Bills card with enable switch, default lead days, default time, and Manage reminders action;
- optimistic controls with rollback and visible error when persistence fails.

### Bill reminders

- Upcoming, disabled, and completed states;
- title, optional amount, next due date, and recurrence summary;
- create, edit, enable/disable, and confirmed delete actions;
- form validation for title, amount, due date/time, lead days, and recurrence;
- save-progress, offline, retry, and expired-date states.

## End-to-end data flows

### Budget warning

1. A transaction write completes.
2. Budget domain logic calculates previous and current usage.
3. Alert integration detects a new 80% or 100% crossing.
4. The client inserts an idempotent `alerts` row.
5. The database webhook invokes the push Edge Function.
6. Expo Push Service delivers to all active registered devices.
7. The alert appears in the synchronized inbox.

### Scheduled bill reminder

1. User creates or updates a bill reminder.
2. Supabase stores the synchronized reminder and next trigger.
3. Cron invokes the due-reminder function.
4. The function atomically claims the occurrence and creates the alert.
5. The alert-insert webhook invokes the push Edge Function.
6. Expo Push Service delivers to all active devices even when FinCoach is closed.
7. Tapping the notification opens the reminder screen.

### Cross-device state

1. Device A changes a preference, reminder, read state, or dismissal state.
2. Supabase persists the change under the authenticated user.
3. Device B retrieves the same state on focus/refresh and may receive live updates while active.
4. Cloud push delivery does not require Device B to open FinCoach first, provided its active push token was registered previously.

## Error handling and recovery

- Notification permission denial leaves all in-app features usable and shows Android Settings guidance.
- Push-token acquisition failure is retried on the next login or foreground transition.
- Offline writes show a retryable error and do not falsely claim synchronization.
- Invalid tokens are deactivated using Expo delivery receipts.
- Temporary push failures retain `pending` or `failed` status for retry without creating a second alert.
- Cron and webhook retries remain idempotent through dedupe keys.
- Edge Functions return structured errors without exposing secrets or raw service responses.
- Missing or deleted source records fall back to the Alerts inbox rather than breaking notification navigation.
- Timezone and daylight-offset calculations use the stored timezone instead of the Edge Function server clock.

## Security and privacy

- Push messages contain only the minimum financial detail needed for the user. Sensitive transaction descriptions are not included by default.
- Expo push tokens are treated as sensitive device identifiers.
- Every public table has owner-based RLS.
- The service-role key and Expo access token remain server-only.
- Edge Functions validate the expected webhook or Cron authorization path.
- No `user_metadata` field is used for authorization.
- No public table policy grants cross-user token or alert access.
- Deleting an account cascades preferences, reminders, alerts, and device registrations.

## Testing strategy

### Pure unit tests

- 80% and 100% budget boundary crossings;
- no duplicate budget warnings;
- 25%, 50%, 75%, and 100% savings milestones;
- savings lead-date calculations;
- daily and weekly spending period keys;
- month-end, leap-year, weekly, monthly, and yearly recurrence;
- bill-reminder validation;
- alert grouping, filtering, and dedupe keys.

### Client and UI tests

- preference CRUD and independent type settings;
- reminder CRUD and enable/disable behavior;
- alert read, mark-all-read, dismissal, and unread count;
- dashboard bell routing and unread indicator;
- prototype labels, filter chips, grouped sections, settings cards, and reminder form structure;
- permission-denied, offline, loading, empty, and retry states;
- notification tap route mapping.

### Schema and server verification

- migration verifier checks tables, constraints, indexes, grants, and RLS policies;
- owner A cannot read or mutate owner B data;
- alert dedupe uniqueness survives concurrent attempts;
- Cron claiming processes one occurrence once;
- Edge Function handles multiple active devices, invalid tokens, and temporary failures;
- webhook invocation cannot expose server secrets.

### Physical Honor 200 acceptance test

- install a rebuilt development or release APK containing `expo-notifications`;
- grant Android notification permission;
- register the Honor 200 push token;
- send a test alert while FinCoach is foregrounded, backgrounded, and closed;
- verify notification tap routing;
- verify a second registered device receives the same server alert;
- confirm read/dismiss state synchronizes after refresh;
- confirm disabled notification types no longer create new alerts.

## Acceptance criteria

- FRAR-01 through FRAR-04 are implemented and traceable to tests.
- Every notification type can be configured separately.
- Manual bill reminders support create, retrieve, update, enable/disable, and delete.
- Budget warning, budget exceeded, savings deadline, savings milestone, spending, and bill notifications are deduplicated.
- Cloud push reaches previously registered devices while FinCoach is closed.
- Alert history and user settings synchronize through Supabase.
- The Alerts inbox and settings screens follow the root prototype visual direction.
- Users cannot access another user's preferences, reminders, alerts, or device tokens.
- No AI, FastAPI, bank integration, or unrelated module is pulled into this implementation.

## Deployment requirements

- Install the Expo SDK 56-compatible `expo-notifications` package and config plugin.
- Configure Android notification icon, color, channels, FCM v1 credentials, and the EAS project ID.
- Rebuild the native Honor 200 APK after adding the notification plugin.
- Apply the Supabase migration and verify RLS before using the mobile screens.
- Deploy the Supabase Edge Functions and configure secrets.
- Configure the alert-insert database webhook and scheduled Cron invocation.
- Run a real-device push test before treating the module as complete.

## Deferred documentation work

After the module and migration are verified, update the FinCoach ERD and thesis data dictionary to distinguish `ALERT`, `REMINDER`, `NOTIFICATION_PREFERENCE`, and `USER_DEVICE`. This documentation step is deferred by user request and does not block implementation of the approved database-backed module.
