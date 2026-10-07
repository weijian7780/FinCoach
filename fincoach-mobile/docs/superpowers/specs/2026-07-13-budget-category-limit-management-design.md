# Budget and Category Limit Management Design

Date: 2026-07-13

## Objective

Complete the FinCoach Budget and Category Limit Management module against functional requirements FRBL-01 through FRBL-05 while preserving the existing Expo, Supabase, and FinCoach UI architecture.

## Approved scope

The module will provide:

- FRBL-01: Create, view, update, and delete user-owned custom expense categories with a selected icon and colour.
- FRBL-02: Set one overall monthly budget and individual monthly limits for selected expense categories.
- FRBL-03: View the overall remaining budget and each category's remaining amount, usage percentage, and progress.
- FRBL-04: Detect and display when recorded spending is within, approaching, at, or above a limit.
- FRBL-05: Update or remove monthly category limits when the user's financial situation changes.

The approved implementation preserves the existing `budgets` table as the per-category monthly-limit table and adds a separate `monthly_budgets` parent record for the overall monthly limit.

## Explicit non-goals

- Transaction entry, receipt capture, and OCR are not part of this module.
- Until Transaction and Receipt Capture is implemented, spending totals are explicitly shown as RM 0 with a `No transactions recorded` state.
- Bank integration is not available. Future progress will use only expense transactions recorded in FinCoach.
- Push notifications and background warning delivery belong to Alert and Reminder Management. This module calculates and displays warning states only.
- Budget recommendations and AI-generated planning belong to AI Financial Coaching.
- Reports, export, and backup functionality will not be pulled into this module.
- Recurring budgets, automatic month rollover, and copying a previous month's limits are not required by FRBL-01 through FRBL-05.

## Existing-state findings

The application currently has:

- a Budget tab containing only a `ComingSoon` placeholder;
- shared default `categories` identified by `bigint` IDs;
- `user_categories` for categories selected during profile setup;
- a `budgets` table containing one amount for each user, category, and month;
- owner-based RLS on `budgets` and basic category read access;
- no Transactions table or transaction client implementation;
- a visual reference showing month navigation, an overall monthly-budget card, category progress cards, an 80% warning, and an Edit Budgets action.

The current `budgets` table represents category limits, not a distinct overall monthly budget. Renaming or replacing it would create unnecessary migration risk, so it will be retained and constrained as the category-limit child data.

## Data architecture

### `monthly_budgets`

A new parent table stores one overall budget per user and calendar month:

- `id uuid primary key default gen_random_uuid()`
- `user_id uuid not null references auth.users(id) on delete cascade`
- `month date not null`
- `limit_amount numeric(12,2) not null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- unique `(user_id, month)`

Constraints require a positive limit and the first day of the month. A composite unique key on `(user_id, month)` supports the relationship from category limits.

### `budgets` as category limits

The existing table remains the category-limit table:

- `id bigint generated always as identity primary key`
- `user_id uuid not null`
- `category_id bigint not null references categories(id) on delete cascade`
- `amount numeric(12,2) not null`
- `month date not null`
- timestamps and unique `(user_id, category_id, month)`

Its amount must be positive and its month must be the first day of that month. A composite foreign key from `(user_id, month)` to `monthly_budgets(user_id, month)` makes each category limit belong to an overall monthly budget and cascades category-limit deletion when the parent month is removed.

For existing category-limit rows, the migration creates one `monthly_budgets` row per user/month using the sum of existing category limits as the initial overall limit. Existing category-limit IDs and records are preserved.

### `categories`

The existing shared lookup is extended instead of replaced:

- `user_id uuid null references auth.users(id) on delete cascade`
- `color text null`
- existing `name`, `type`, and `icon` fields remain

Rows with `user_id is null` are system defaults. Rows with a user ID are custom categories owned by that user. The current global unique-name constraint is replaced by:

- a case-insensitive unique default-category name index;
- a case-insensitive unique `(user_id, name)` index for custom categories.

This permits different users to create categories with the same name while preventing duplicates within one user's list.

System defaults remain readable by every authenticated user but cannot be edited or deleted by the mobile client. Users may select default categories and fully manage only their own custom categories. A custom category stores its selected Material icon name and approved palette colour.

### Limit consistency

The sum of category limits for a month cannot exceed the overall monthly budget. Validation occurs in both places:

- client-side validation gives immediate field-level feedback;
- a database trigger rejects inserts or updates that would exceed the parent monthly limit and rejects lowering the overall limit below the current category-limit sum.

This preserves correctness if a write bypasses the mobile form or two clients write concurrently.

### RLS and Data API access

- Users can select, insert, update, and delete only `monthly_budgets` where `user_id = auth.uid()`.
- Users can select, insert, update, and delete only `budgets` rows where `user_id = auth.uid()`.
- Category-limit writes must reference a category visible to the user: either a system default or a category owned by that user.
- Users can read system-default categories and their own custom categories.
- Users can insert, update, or delete only custom category rows where `user_id = auth.uid()`.
- Update policies use both `USING` and `WITH CHECK`; no policy relies on `TO authenticated` alone.
- Authenticated-role grants expose only the operations required by the mobile client.
- Indexes support `(user_id, month)` budget queries and `(user_id, lower(name))` custom-category lookup.

## Application architecture

### Domain logic

Pure TypeScript functions will provide:

- RM parsing and two-decimal normalization;
- first-day-of-month keys and previous/next month navigation;
- overall and per-category used, remaining, ratio, and percentage values;
- limit-status classification;
- overall-budget, category-limit, and custom-category validation;
- validation that category-limit totals do not exceed the overall monthly limit.

These functions accept expense totals as input. They use zero totals until the Transactions module supplies recorded expenses, so no later redesign is required.

### Status rules

Status is evaluated using uncapped spending divided by the relevant limit:

- `Within Limit`: usage is below 80%.
- `Approaching Limit`: usage is at least 80% but below 100%.
- `Limit Reached`: usage equals 100% after money normalization.
- `Exceeded`: usage is above 100%.

Visual progress bars cap their width at 100%, while percentage text and exceeded amounts remain uncapped so overspending is visible. Remaining amount is zero for normal progress displays once exceeded, and a separate exceeded amount shows the overspend.

### Supabase client layer

Focused client operations will:

- fetch the monthly parent budget and category limits for a user/month;
- create or update an overall monthly budget;
- remove an overall monthly budget and its category limits after confirmation;
- create, update, and remove category limits;
- list system-default and user-owned custom expense categories;
- create, update, and delete custom categories.

All write functions include the authenticated user's ID in their filters as defense in depth in addition to RLS.

### Screens and components

The module uses three screens:

- Budget tab: month selector, overall spending/limit card, zero-transaction notice when applicable, category breakdown cards, and an Edit Budgets action.
- Manage Budget: overall monthly limit, selected category-limit rows, add/remove limit controls, total allocation summary, inline validation, save state, and confirmed deletion of the month's budget.
- Manage Categories: system defaults shown read-only and custom categories with create, edit, icon/colour selection, and confirmed delete actions.

The main screen follows the approved FinCoach UI reference: indigo theme, rounded cards, Hanken Grotesk type, month chevrons, overall progress, category icons, warning badges, and an Edit Budgets primary action. Shared components hold the month selector, money field, status badge, progress bar, and category/icon picker where reuse materially reduces duplication.

The implementation uses React Native and Expo Router only. It will not add native chart, SVG, or date-picker dependencies. Screens use safe-area-aware scrolling, keyboard-safe forms, `AppText`/`AppTextInput`, accessible labels, disabled saving states, and stable list keys.

## Validation and error handling

- Overall and category limits must be valid RM amounts greater than RM 0.
- The overall limit cannot be reduced below the sum of existing category limits.
- A category may have at most one limit in the selected month.
- Combined category limits cannot exceed the overall monthly limit.
- Custom category name is required, trimmed, case-insensitively unique per user, and limited to 50 characters.
- Custom categories must be expense categories and require an approved icon and colour.
- System-default categories cannot be edited or deleted.
- Deleting a custom category requires confirmation and cascades its unused category-limit rows.
- Deleting a monthly budget requires confirmation and removes that month's category limits.
- Failed writes preserve user input and show a retryable message.
- Loading, empty, no-budget, no-transaction, saving, and retryable-error states are explicit.
- Database constraint errors are translated into concise form messages instead of displaying raw PostgreSQL text.

## Data flow

1. The user opens the Budget tab for a selected month.
2. The client reads the `monthly_budgets` parent, category limits, and visible categories.
3. Until Transactions exists, the expense input is an empty list and every used amount is RM 0.
4. Domain functions derive overall and per-category progress, remaining values, and status labels.
5. The user creates or edits the overall budget and category limits; client validation runs before Supabase writes.
6. Database constraints, triggers, and RLS validate ownership and allocation consistency.
7. The client reloads the selected month and updates the Budget tab and Home budget preview.
8. When Transaction Management is later implemented, its recorded expenses will be grouped by month and category and passed into the existing domain calculation boundary.

## Testing strategy

Implementation follows red-green-refactor:

- Unit tests first for money parsing, month keys, remaining values, percentages, uncapped overspending, all four statuses, and allocation validation.
- Client tests for read/write query construction, ordering, user filters, and Supabase error propagation through an injected data-client boundary.
- Structural regression tests ensure the Budget UI does not import removed native SVG or date-picker modules.
- SQL verification covers constraints, composite parent-child relationship, migration of existing rows, cascade behavior, category visibility, owner isolation, and allocation-trigger rejection.
- Fresh `expo install --check`, unit tests, TypeScript typecheck, focused lint, and Android export verification run before completion is claimed.
- Physical-device acceptance checks cover the Honor 200 viewport, keyboard scrolling, month navigation, create, edit, delete, reload persistence, empty states, and warning colours.

## Acceptance criteria

- A signed-in user can create one overall budget for a selected month.
- The user can assign positive limits to one or more visible expense categories.
- The combined category limits cannot exceed the overall monthly budget.
- The Budget tab shows overall and category used/limit/remaining values and progress.
- With no Transactions module, the screen clearly shows RM 0 spending and does not imply that external spending is known.
- All four status rules produce the correct label and colour from supplied spending totals.
- The user can navigate between months without mixing records.
- The user can update or remove a category limit and can remove the selected month's overall budget with confirmation.
- The user can create, edit, and delete a custom expense category with a chosen icon and colour.
- System-default categories cannot be modified or deleted.
- Budget and custom-category records persist after reload and are inaccessible to another user.
- Existing `budgets` rows survive migration and receive a matching overall monthly-budget parent.
- The Home budget preview reads the current month's monthly budget and continues to show zero spending until Transactions is connected.
- No Transaction, Alert, Report, Export, Backup, or AI module is implemented or expanded as part of this work.

## Requirement traceability

| Requirement | Design evidence |
|---|---|
| FRBL-01 | User-owned custom categories with create, read, update, delete, icon, and colour |
| FRBL-02 | `monthly_budgets` overall limit plus per-category rows in `budgets` |
| FRBL-03 | Overall and category progress, usage percentage, and remaining values |
| FRBL-04 | Deterministic Within, Approaching, Reached, and Exceeded status rules |
| FRBL-05 | Manage Budget update/remove flows and confirmed deletion |
