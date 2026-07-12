# Savings Goal Management Design

Date: 2026-07-12

## Objective

Complete the FinCoach Savings Goal Management module against the thesis functional requirements FRSG-01 through FRSG-05 while preserving the existing Expo, Supabase, and FinCoach UI architecture.

## Approved scope

The module will provide:

- FRSG-01: Create a savings goal with a purpose/name, target amount, and deadline.
- FRSG-02: Record one or more monetary contributions against a goal.
- FRSG-03: Show percentage progress, amount saved, remaining target, deadline, status, and contribution history.
- FRSG-04: Show a practical deterministic saving suggestion based on progress, remaining amount, and deadline.
- FRSG-05: Update or delete goals.

The approved implementation uses a normalized `savings_goals` plus `savings_contributions` model.

## Explicit non-goals

- Saving-related action-plan tasks are outside FRSG-01 through FRSG-05 and will not be added.
- Savings reminders and notification scheduling belong to Alert and Reminder Management.
- AI-generated saving advice belongs to AI Financial Coaching. This module uses transparent deterministic suggestions and does not call an LLM.
- Bank-account integration and automatic verification of real savings balances are not available. Progress is based only on contributions recorded in FinCoach.
- Transaction, Budget, Report, Export, and Backup functionality will not be pulled into this module.

## Existing-state findings

The current application already has a `savings_goals` table, owner-based Row-Level Security (RLS), basic CRUD client functions, a simple editable list screen, and a dashboard preview. It does not yet satisfy the complete requirements because it lacks a usable deadline flow, contribution records/history, remaining-target display, practical suggestions, goal-detail flow, and complete validation.

## Data architecture

### `savings_goals`

The existing table remains the parent record:

- `id bigint primary key`
- `user_id uuid not null`
- `name text not null`
- `target_amount numeric(12,2) not null`
- `current_amount numeric(12,2) not null default 0`
- `deadline date null`
- `created_at timestamptz`
- `updated_at timestamptz`

Constraints will require a non-blank goal name, a positive target, and a non-negative current amount.

`current_amount` remains because it is part of the thesis SAVINGS GOAL entity and supports efficient dashboard/report reads. It is a derived balance, not a freely edited value after contribution tracking is enabled.

### `savings_contributions`

A normalized child table will hold the required history:

- `id bigint primary key`
- `goal_id bigint not null references savings_goals(id) on delete cascade`
- `amount numeric(12,2) not null check (amount > 0)`
- `contributed_on date not null default current_date`
- `note text null`
- `created_at timestamptz not null default now()`

Contribution ownership is derived through its parent goal instead of duplicating `user_id`.

### Balance consistency

A private PostgreSQL trigger function will recalculate `savings_goals.current_amount` as the sum of its contributions after contribution insert, update, or delete. This avoids client-side race conditions and makes the database authoritative.

For existing goals with `current_amount > 0` and no history, the migration will create one opening-balance contribution so existing saved amounts are preserved and become auditable.

### RLS and Data API access

- Users can select, insert, update, and delete only goals where `user_id = auth.uid()`.
- Users can access a contribution only when its parent goal belongs to `auth.uid()`.
- Contribution insert and update policies verify ownership of the target parent goal.
- The authenticated role receives only the table privileges needed by the mobile client.
- An index on `(goal_id, contributed_on desc, created_at desc)` supports history queries.

## Application architecture

### Domain logic

Pure functions will calculate and validate:

- normalized RM amounts with two-decimal precision;
- progress ratio and percentage, capped visually at 100%;
- remaining target, never below zero;
- goal status;
- deadline state and days remaining;
- progress-based saving suggestions;
- goal and contribution form validation.

Keeping these rules outside React components makes them deterministic and directly testable.

### Supabase client layer

The finance client will expose focused operations:

- list and fetch a user's goals;
- create and update goal metadata;
- delete a goal;
- list a goal's contributions;
- add a contribution;
- delete a contribution.

The client will not manually update `current_amount`; it will read the database balance maintained by the trigger.

### Screens and components

The `/savings` route becomes a small route group:

- Goal list: reference-aligned cards with a progress ring, saved/target amounts, remaining amount, deadline, and status. The floating add button opens goal creation.
- Goal form: create or edit purpose/name, target amount, and deadline with inline validation.
- Goal details: progress summary, practical suggestion, contribution history, add-contribution form, edit action, and guarded delete action.

Shared Savings components will contain the progress ring, status badge, and form fields where reuse materially reduces duplication.

All screens will use `useSafeAreaInsets()`, scrollable content, `AppText`/`AppTextInput`, stable list keys, accessible labels, disabled loading states, and the existing indigo FinCoach tokens. No fixed status-bar offsets will remain.

## Status and suggestion rules

Status labels preserve the approved visual reference:

- `Goal reached!`: current amount is at least the target.
- `Needs Attention`: the deadline has passed and a balance remains.
- `Almost there!`: progress is at least 80% but below 100% and the deadline has not passed.
- `On Track`: for a future deadline, actual progress is no more than 10 percentage points behind the expected linear progress from `created_at` to `deadline`; without a deadline, progress is at least 40%.
- `Needs Attention`: all other incomplete cases.

Rules are evaluated in the order above, so an overdue incomplete goal is never shown as on track merely because its percentage is high.

Suggestion rules are deterministic:

- Reached goal: acknowledge completion and advise keeping the saved funds allocated to the goal.
- Future deadline: calculate a practical weekly amount as `remaining / weeks remaining`.
- Deadline today: show the remaining amount needed today.
- Past deadline: state the remaining amount and recommend updating the deadline or contribution plan.
- No deadline: state the remaining amount and recommend setting a target date.

The UI will describe these as FinCoach saving suggestions, not AI advice.

## Validation and error handling

- Goal purpose/name is required and length-limited.
- Target amount must be a valid positive RM amount.
- Deadline is required by FRSG-01 and cannot be earlier than the current date when creating a new goal.
- A goal target cannot be reduced below the already contributed amount.
- Contribution amount must be positive and cannot exceed the remaining target. This prevents accidental overfunding and keeps completion at exactly the target.
- Contribution date cannot be in the future.
- Optional notes are length-limited.
- Destructive actions require confirmation.
- Loading, empty, retryable-error, saving, and disabled states are shown explicitly.
- Failed writes remain on the current screen with user-entered values preserved.

## Data flow

1. User creates a goal; the mobile client inserts goal metadata into Supabase.
2. The list/detail screen reads the goal balance and renders progress.
3. User records a contribution; Supabase inserts the contribution.
4. The database trigger recalculates the parent goal balance atomically.
5. The client reloads the goal and history and derives status, remaining amount, and suggestion.
6. Deleting a contribution recalculates the balance; deleting a goal cascades to its contribution history.

## Testing strategy

Implementation will follow red-green-refactor:

- Unit tests first for amount parsing, validation, progress, remaining amount, status, and suggestion calculations.
- Client tests for contribution ordering and database-operation error propagation where a small injected test boundary is practical.
- SQL checks for table constraints, cascade behavior, balance-trigger recalculation, and owner isolation.
- TypeScript typecheck and Expo lint.
- Focused Android UI verification on a small-screen viewport and the Honor 200 dimensions, including keyboard/form scrolling, empty state, create, contribution, edit, delete, and reload persistence.

## Acceptance criteria

- A signed-in user can create a goal with purpose, target, and deadline.
- The created goal persists after reload and is inaccessible to another user.
- The user can add contributions with date and optional note.
- Contribution history is displayed newest first and persists after reload.
- The goal balance equals the contribution sum after insert or delete.
- Progress percentage, saved amount, remaining amount, deadline, status, and suggestion are accurate.
- The user can update the goal without reducing the target below its saved amount.
- The user can delete a contribution and delete a goal with confirmation.
- Deleting a goal removes its contribution records.
- The Savings list and dashboard preview refresh after changes.
- No other FinCoach module is implemented or expanded as part of this work.
- Typecheck, lint, unit tests, SQL verification, and responsive UI verification pass.

## Requirement traceability

| Requirement | Design evidence |
|---|---|
| FRSG-01 | Goal form and `savings_goals` metadata |
| FRSG-02 | `savings_contributions` table and add-contribution flow |
| FRSG-03 | Progress ring, saved/remaining values, contribution history, status |
| FRSG-04 | Deterministic deadline/progress-based suggestion rules |
| FRSG-05 | Goal edit and confirmed deletion flows |
