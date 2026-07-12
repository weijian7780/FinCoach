# Savings Goal Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver FinCoach Savings Goal Management requirements FRSG-01 through FRSG-05 with normalized contribution history, secure Supabase persistence, a reference-aligned Android UI, and verified behavior.

**Architecture:** `savings_goals` remains the parent and cached goal balance, while `savings_contributions` becomes the normalized history. A private database trigger maintains the cached balance atomically. Pure TypeScript domain functions own validation, metrics, status, and deterministic suggestions; focused Supabase functions provide persistence; Expo Router screens provide list, create/edit, detail, and contribution flows.

**Tech Stack:** Expo SDK 56.0.11, React Native 0.85.3, React 19.2.3, TypeScript 6.0.3, Expo Router 56.2.10, Supabase JS 2.108.1, PostgreSQL/RLS, Vitest 4.1.10, `react-native-svg` 15.15.4, `@react-native-community/datetimepicker` 9.1.0.

## Global Constraints

- Implement only FRSG-01 through FRSG-05; do not add action-plan tasks, reminders, AI calls, bank integration, transactions, budgets, reports, export, or backup behavior.
- Preserve the approved FinCoach indigo UI and the visual reference at `G:\My Drive\FYP 1 & 2\FinCoach UI\screens_extra.jsx`.
- Use `useSafeAreaInsets()` and scrollable form/detail content; do not use fixed status-bar offsets.
- Render text through `AppText` and `AppTextInput`.
- Normal users must access only their own goals and contribution history through RLS.
- `current_amount` is database-derived from contribution rows and is never edited directly by the mobile client.
- Saving suggestions are deterministic and must not be labelled as AI advice.
- Existing user changes to the root and mobile `AGENTS.md` files must remain untouched.
- Implement with red-green-refactor: every new domain or persistence behavior starts with a failing test.
- Use inline execution in this session because the workspace rules do not authorize subagent delegation.

---

## File Map

- Create `src/lib/savings-domain.ts`: validation, money parsing, progress, status, deadline, and suggestion rules.
- Create `src/lib/savings-domain.test.ts`: unit tests for every domain behavior.
- Create `src/lib/savings.ts`: Supabase CRUD for goals and contributions.
- Create `src/lib/savings.test.ts`: persistence-query contract and error-propagation tests using an injected fake client.
- Modify `src/lib/types.ts`: normalized savings goal/contribution types.
- Modify `src/lib/finance.ts`: remove savings functions after callers move to `src/lib/savings.ts`.
- Modify `supabase/schema.sql`: constraints, contribution table, backfill, trigger, grants, indexes, and RLS.
- Create `supabase/migrations/*_complete_savings_goal_management.sql`: deployable schema migration whose timestamped filename is emitted by the CLI.
- Create `scripts/verify-savings-schema.mjs`: structural guard for required SQL objects and policies.
- Create `src/components/savings/progress-ring.tsx`: SVG progress ring.
- Create `src/components/savings/goal-card.tsx`: reference-aligned goal summary card.
- Create `src/components/savings/date-field.tsx`: Android/iOS deadline/contribution date picker field.
- Delete `src/app/savings.tsx` after route replacement.
- Create `src/app/savings/index.tsx`: goal list and empty/error states.
- Create `src/app/savings/manage.tsx`: create/edit form.
- Create `src/app/savings/[goalId].tsx`: details, suggestion, contribution history, add/delete contribution, edit/delete goal.
- Modify `src/app/(app)/index.tsx`: refreshed dashboard preview using the new savings client and metrics.
- Modify `src/app/_layout.tsx`: explicitly register `savings/index`, `savings/manage`, and `savings/[goalId]`.
- Modify `docs/acceptance-tests.md`: add FRSG-01 through FRSG-05 acceptance checks and remove no Savings scope.
- Modify `package.json` and `package-lock.json`: pinned test/UI dependencies and test scripts.

---

### Task 1: Install pinned dependencies and establish the domain test harness

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `vitest.config.ts`
- Create: `src/lib/savings-domain.test.ts`
- Create: `src/lib/savings-domain.ts`

**Interfaces:**
- Produces: `parseMoney`, `formatMoney`, `validateGoalInput`, `validateContributionInput`, `getSavingsMetrics`, `getGoalStatus`, `getSavingsSuggestion`, `todayIsoDate`.
- Consumes: no application state or Supabase client.

- [ ] **Step 1: Install exact dependencies through Expo/npm and preserve the lockfile**

Run:

```powershell
npx.cmd expo install react-native-svg@15.15.4 @react-native-community/datetimepicker@9.1.0
npm.cmd install --save-dev --save-exact vitest@4.1.10 supabase@2.109.1
```

Expected: `package.json` contains exact versions, `package-lock.json` changes, and no peer-dependency errors remain.

- [ ] **Step 2: Add test configuration and scripts**

Add to `package.json`:

```json
"test": "vitest run",
"test:watch": "vitest"
```

Create `vitest.config.ts`:

```ts
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: { environment: 'node', clearMocks: true },
});
```

- [ ] **Step 3: Write failing domain tests**

Create `src/lib/savings-domain.test.ts` with focused cases:

```ts
import { describe, expect, test } from 'vitest';
import {
  getGoalStatus,
  getSavingsMetrics,
  getSavingsSuggestion,
  parseMoney,
  validateContributionInput,
  validateGoalInput,
} from '@/lib/savings-domain';

const today = '2026-07-12';

describe('parseMoney', () => {
  test('normalizes valid RM input to two decimals', () => expect(parseMoney(' 12.345 ')).toBe(12.35));
  test('rejects empty, negative, and malformed amounts', () => {
    expect(parseMoney('')).toBeNull();
    expect(parseMoney('-1')).toBeNull();
    expect(parseMoney('1.2.3')).toBeNull();
  });
});

test('goal validation requires purpose, positive target, and non-past deadline', () => {
  expect(validateGoalInput({ name: '', targetAmount: '0', deadline: '2026-07-11' }, { today, currentAmount: 0 })).toEqual({
    name: 'Enter a goal purpose.',
    targetAmount: 'Enter a target amount greater than RM 0.',
    deadline: 'Choose today or a future date.',
  });
});

test('goal target cannot be reduced below contributions', () => {
  expect(validateGoalInput({ name: 'Laptop', targetAmount: '400', deadline: '2026-12-01' }, { today, currentAmount: 500 }).targetAmount)
    .toBe('Target cannot be lower than the RM 500.00 already saved.');
});

test('contribution validation rejects future dates and amounts above remaining target', () => {
  expect(validateContributionInput({ amount: '501', contributedOn: '2026-07-13', note: '' }, { today, remainingAmount: 500 })).toEqual({
    amount: 'Contribution cannot exceed the RM 500.00 remaining.',
    contributedOn: 'Contribution date cannot be in the future.',
  });
});

test('metrics cap display progress and never return negative remaining amount', () => {
  expect(getSavingsMetrics(1200, 1000)).toEqual({ currentAmount: 1200, targetAmount: 1000, remainingAmount: 0, ratio: 1, percentage: 100 });
});

test('overdue incomplete goals need attention before percentage thresholds apply', () => {
  expect(getGoalStatus({ currentAmount: 900, targetAmount: 1000, createdAt: '2026-01-01T00:00:00Z', deadline: '2026-07-11' }, today).label)
    .toBe('Needs Attention');
});

test('future deadlines produce a practical weekly suggestion', () => {
  expect(getSavingsSuggestion({ currentAmount: 500, targetAmount: 1000, deadline: '2026-08-09' }, today))
    .toContain('RM 125.00 per week');
});
```

- [ ] **Step 4: Run the domain test and verify RED**

Run: `npm.cmd test -- src/lib/savings-domain.test.ts`

Expected: FAIL because `@/lib/savings-domain` does not exist.

- [ ] **Step 5: Implement the complete pure domain API**

Create `src/lib/savings-domain.ts` with these exact exports and rules:

```ts
export type GoalInput = { name: string; targetAmount: string; deadline: string };
export type ContributionInput = { amount: string; contributedOn: string; note: string };
export type FieldErrors<T> = Partial<Record<keyof T, string>>;
export type GoalStatus = { label: 'Goal reached!' | 'Almost there!' | 'On Track' | 'Needs Attention'; color: string };

export function parseMoney(value: string): number | null;
export function formatMoney(value: number): string;
export function todayIsoDate(now?: Date): string;
export function validateGoalInput(input: GoalInput, context: { today: string; currentAmount: number }): FieldErrors<GoalInput>;
export function validateContributionInput(input: ContributionInput, context: { today: string; remainingAmount: number }): FieldErrors<ContributionInput>;
export function getSavingsMetrics(currentAmount: number, targetAmount: number): {
  currentAmount: number; targetAmount: number; remainingAmount: number; ratio: number; percentage: number;
};
export function getGoalStatus(goal: { currentAmount: number; targetAmount: number; createdAt: string; deadline: string | null }, today: string): GoalStatus;
export function getSavingsSuggestion(goal: { currentAmount: number; targetAmount: number; deadline: string | null }, today: string): string;
```

Use UTC date-only arithmetic, two-decimal rounding, the ordered status rules in the approved specification, a 100-character goal-name limit, and a 200-character note limit.

- [ ] **Step 6: Run tests and verify GREEN**

Run: `npm.cmd test -- src/lib/savings-domain.test.ts`

Expected: all domain tests PASS with no warnings.

- [ ] **Step 7: Commit Task 1**

```powershell
git add package.json package-lock.json vitest.config.ts src/lib/savings-domain.ts src/lib/savings-domain.test.ts
git commit -m "test: define savings goal domain behavior"
```

---

### Task 2: Add normalized Supabase schema, balance trigger, and owner-only RLS

**Files:**
- Modify: `supabase/schema.sql`
- Create: `supabase/migrations/*_complete_savings_goal_management.sql` using the filename emitted by `supabase migration new`
- Create: `scripts/verify-savings-schema.mjs`

**Interfaces:**
- Produces: `public.savings_contributions` and trigger-maintained `public.savings_goals.current_amount`.
- Consumes: existing `public.savings_goals` and Supabase `auth.uid()`.

- [ ] **Step 1: Initialize the CLI workspace and discover commands**

Run:

```powershell
npx.cmd supabase --help
npx.cmd supabase migration --help
npx.cmd supabase migration new --help
```

The current repository has no `supabase/config.toml`. Run `npx.cmd supabase init` once, then run:

```powershell
npx.cmd supabase migration new complete_savings_goal_management
```

Expected: one CLI-generated migration file under `supabase/migrations/`.

- [ ] **Step 2: Write the failing SQL structural verifier**

Create `scripts/verify-savings-schema.mjs` that reads both `supabase/schema.sql` and the generated migration and asserts the presence of:

```js
const required = [
  'create table if not exists public.savings_contributions',
  'check (amount > 0)',
  'references public.savings_goals (id) on delete cascade',
  'enable row level security',
  'create trigger refresh_savings_goal_amount',
  'private.refresh_savings_goal_amount',
  'to authenticated',
  'select auth.uid()',
];
```

Exit non-zero and print each missing fragment.

- [ ] **Step 3: Run the verifier and verify RED**

Run: `node scripts/verify-savings-schema.mjs`

Expected: FAIL listing the missing contribution table, trigger, and policies.

- [ ] **Step 4: Implement idempotent DDL in the generated migration and mirror it into `schema.sql`**

The SQL must:

```sql
alter table public.savings_goals drop constraint if exists savings_goals_name_not_blank;
alter table public.savings_goals drop constraint if exists savings_goals_target_positive;
alter table public.savings_goals drop constraint if exists savings_goals_current_nonnegative;
alter table public.savings_goals drop constraint if exists savings_goals_target_covers_current;
alter table public.savings_goals
  add constraint savings_goals_name_not_blank check (char_length(btrim(name)) between 1 and 100),
  add constraint savings_goals_target_positive check (target_amount > 0),
  add constraint savings_goals_current_nonnegative check (current_amount >= 0),
  add constraint savings_goals_target_covers_current check (target_amount >= current_amount);

create table if not exists public.savings_contributions (
  id bigint generated always as identity primary key,
  goal_id bigint not null references public.savings_goals (id) on delete cascade,
  amount numeric(12, 2) not null check (amount > 0),
  contributed_on date not null default current_date check (contributed_on <= current_date),
  note text check (note is null or char_length(note) <= 200),
  created_at timestamptz not null default now()
);
```

Backfill one `Opening balance` row only for goals with a positive cached balance and no contribution rows. Add a private `security definer` trigger function with `set search_path = ''`, an `auth.uid()` ownership guard when a JWT exists, explicit qualification of all objects, and `revoke all on function ... from public, anon, authenticated`. The function rejects a contribution sum above the goal target and recalculates the parent sum after contribution INSERT or DELETE. Revoke broad goal UPDATE access and grant authenticated users UPDATE only on `name`, `target_amount`, `deadline`, and `updated_at`; replace the current all-operation goal policy with separate SELECT/INSERT/UPDATE/DELETE policies, with both `USING` and `WITH CHECK` on UPDATE. Grant contribution SELECT/INSERT/DELETE to `authenticated`, revoke access from `anon`, enable RLS, and define separate SELECT/INSERT/DELETE policies using `exists` against an owned goal. Add the history index.

- [ ] **Step 5: Run the verifier and verify GREEN**

Run: `node scripts/verify-savings-schema.mjs`

Expected: PASS for both canonical schema and migration.

- [ ] **Step 6: Validate or apply the database change**

Run `npx.cmd supabase db --help` and use the available authenticated path:

- local Docker available: `npx.cmd supabase start`, `npx.cmd supabase db reset`, then SQL assertions for insert/delete sum and cross-user RLS;
- linked project available: run advisors, review the migration list, apply with the documented `db push` command, then query the created objects;
- neither available: retain the verified migration and record live database application as the only external gate; do not claim runtime persistence verified.

- [ ] **Step 7: Commit Task 2**

```powershell
git add supabase/schema.sql supabase/config.toml supabase/migrations scripts/verify-savings-schema.mjs
git commit -m "feat: add normalized savings contributions schema"
```

---

### Task 3: Implement typed Savings persistence with tests

**Files:**
- Modify: `src/lib/types.ts`
- Create: `src/lib/savings.test.ts`
- Create: `src/lib/savings.ts`
- Modify: `src/lib/finance.ts`

**Interfaces:**
- Consumes: Supabase tables from Task 2 and domain amount/date values from Task 1.
- Produces: `fetchSavingsGoals`, `fetchSavingsGoal`, `createSavingsGoal`, `updateSavingsGoal`, `deleteSavingsGoal`, `fetchSavingsContributions`, `addSavingsContribution`, `deleteSavingsContribution`.

- [ ] **Step 1: Add the normalized TypeScript types**

Add:

```ts
export type SavingsGoal = {
  id: number;
  user_id: string;
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null;
  created_at: string;
  updated_at: string;
};

export type SavingsContribution = {
  id: number;
  goal_id: number;
  amount: number;
  contributed_on: string;
  note: string | null;
  created_at: string;
};
```

- [ ] **Step 2: Write failing persistence tests around an injected fake client**

Tests must prove:

```ts
test('lists goals newest deadline first for the signed-in owner');
test('fetches one goal by id and owner id');
test('creates goals without accepting current_amount from the caller');
test('updates only name, target_amount, deadline, and updated_at');
test('lists contributions newest date and creation first');
test('adds positive contribution fields without user_id duplication');
test('propagates Supabase errors instead of returning empty success');
```

- [ ] **Step 3: Run persistence tests and verify RED**

Run: `npm.cmd test -- src/lib/savings.test.ts`

Expected: FAIL because `src/lib/savings.ts` does not exist.

- [ ] **Step 4: Implement minimal persistence functions**

Use a small structural client type:

```ts
type SavingsDataClient = Pick<typeof supabase, 'from'>;
```

Each exported function accepts `client: SavingsDataClient = supabase` as its final parameter for real-code tests. Every owner-specific goal update/delete adds both `.eq('id', goalId)` and `.eq('user_id', userId)`. Contribution history orders `contributed_on` descending and then `created_at` descending. Remove the old savings exports from `finance.ts` after all callers are migrated.

- [ ] **Step 5: Run persistence and domain tests and verify GREEN**

Run: `npm.cmd test -- src/lib/savings.test.ts src/lib/savings-domain.test.ts`

Expected: all tests PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/lib/types.ts src/lib/savings.ts src/lib/savings.test.ts src/lib/finance.ts
git commit -m "feat: add savings goal persistence client"
```

---

### Task 4: Build reusable Savings UI and the goal list/create/edit flow

**Files:**
- Create: `src/components/savings/progress-ring.tsx`
- Create: `src/components/savings/goal-card.tsx`
- Create: `src/components/savings/date-field.tsx`
- Delete: `src/app/savings.tsx`
- Create: `src/app/savings/index.tsx`
- Create: `src/app/savings/manage.tsx`

**Interfaces:**
- Consumes: Task 1 metrics/status/validation and Task 3 goal CRUD.
- Produces: navigable list and create/edit route.

- [ ] **Step 1: Extend domain tests for card/form view-state edge cases**

Add failing cases for zero progress, 80% progress, reached goals, invalid money precision, name/note length, no deadline suggestion, and past deadline suggestion. Run them and confirm expected failures before extending domain code.

- [ ] **Step 2: Build the progress ring and goal card**

`ProgressRing` uses `Svg` and two `Circle` elements with:

```ts
const radius = (size - strokeWidth) / 2;
const circumference = 2 * Math.PI * radius;
const dashOffset = circumference * (1 - Math.min(1, Math.max(0, progress)));
```

`GoalCard` renders purpose, percentage, RM saved/target, remaining amount, formatted deadline, and ordered status. The entire card is an accessible `Pressable` that opens `/savings/[goalId]`.

- [ ] **Step 3: Build the date field**

Use `DateTimePickerAndroid.open` on Android and an inline/modal `DateTimePicker` on iOS. Store values as local calendar `YYYY-MM-DD` strings without UTC day shifting. Set `minimumDate` for new goal deadlines and `maximumDate` for contribution dates.

- [ ] **Step 4: Replace the list screen**

`src/app/savings/index.tsx` must include:

- safe-area top padding;
- subtitle `Track your progress to financial freedom.`;
- loading, empty, retryable error, and populated states;
- reference-aligned cards;
- floating add button above the bottom inset;
- `useFocusEffect` reload so returning from create/detail refreshes data.

- [ ] **Step 5: Build create/edit form route**

`src/app/savings/manage.tsx` reads optional `goalId`, loads an existing owned goal for edit, validates on save, preserves values after errors, and submits only `{ name, target_amount, deadline }`. Use the native date field, decimal keypad, inline field errors, loading state, and a disabled duplicate-submit state.

- [ ] **Step 6: Run automated checks**

Run:

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
```

Expected: PASS with no React Hooks or TypeScript errors.

- [ ] **Step 7: Commit Task 4**

```powershell
git add src/components/savings src/app/savings src/app/savings.tsx package.json package-lock.json
git commit -m "feat: build savings goal list and forms"
```

---

### Task 5: Build goal details, suggestions, and contribution history

**Files:**
- Create: `src/app/savings/[goalId].tsx`
- Modify: `src/app/savings/index.tsx`
- Modify: `src/components/savings/goal-card.tsx`

**Interfaces:**
- Consumes: Task 1 domain functions and Task 3 contribution CRUD.
- Produces: FRSG-02, FRSG-03, FRSG-04, and FRSG-05 interaction flows.

- [ ] **Step 1: Add failing tests for contribution and suggestion boundaries**

Cover exact-target contribution, over-target rejection, deadline today, reached goal, deleted contribution balance expectation, and overdue 90% goal precedence. Run and confirm failures for any missing rule.

- [ ] **Step 2: Implement the detail summary and suggestion card**

Show the progress ring, saved/target, remaining amount, deadline, status, and `FinCoach saving suggestion`. Provide Edit and Delete actions; Delete uses `Alert.alert` confirmation and returns to the list only after success.

- [ ] **Step 3: Implement add-contribution form**

The form captures amount, contribution date, and optional note. It validates against the currently remaining amount and today, disables repeat submission, calls `addSavingsContribution`, then reloads goal plus history so the database-triggered total is displayed.

- [ ] **Step 4: Implement contribution history and correction**

Render newest first with stable contribution IDs, formatted RM/date/note, empty history state, and a confirmed delete action. On deletion, reload both parent and history to display the recalculated balance.

- [ ] **Step 5: Run automated checks**

Run `npm.cmd test`, `npm.cmd run typecheck`, and `npm.cmd run lint`.

Expected: all PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/app/savings src/components/savings src/lib/savings-domain.ts src/lib/savings-domain.test.ts
git commit -m "feat: add savings contributions and progress details"
```

---

### Task 6: Refresh dashboard integration and document acceptance coverage

**Files:**
- Modify: `src/app/(app)/index.tsx`
- Modify: `src/app/_layout.tsx`
- Modify: `docs/acceptance-tests.md`

**Interfaces:**
- Consumes: `fetchSavingsGoals` and `getSavingsMetrics`.
- Produces: fresh home preview and traceable FRSG acceptance checklist.

- [ ] **Step 1: Update the dashboard import and refresh behavior**

Replace the old finance savings import with `@/lib/savings`, compute remaining/percentage using `getSavingsMetrics`, and load through `useFocusEffect` so edits made in Savings appear when returning Home.

- [ ] **Step 2: Register and verify Savings routes**

Add Stack entries only if Expo Router type generation/navigation requires them. Verify `/savings`, `/savings/manage`, and `/savings/[goalId]` resolve without duplicate-route warnings.

- [ ] **Step 3: Add requirement-specific acceptance tests**

Document checks under `## Savings Goal Management` for:

```markdown
- FRSG-01: Create and reload a goal with purpose, target and deadline.
- FRSG-02: Add dated contributions with optional notes.
- FRSG-03: Verify progress, remaining amount and newest-first history.
- FRSG-04: Verify future, today, overdue, no-deadline and reached suggestions.
- FRSG-05: Edit a goal, reject target below saved amount, delete a contribution and delete a goal.
- RLS: User A cannot read or mutate User B's goals or contributions.
```

- [ ] **Step 4: Run automated checks**

Run `npm.cmd test`, `npm.cmd run typecheck`, and `npm.cmd run lint`.

Expected: all PASS.

- [ ] **Step 5: Commit Task 6**

```powershell
git add 'src/app/(app)/index.tsx' src/app/_layout.tsx docs/acceptance-tests.md
git commit -m "feat: integrate savings goals with dashboard"
```

---

### Task 7: Completion audit and runtime verification

**Files:**
- Review: all files changed in Tasks 1-6
- Modify only if a verification failure requires a focused fix with a failing regression test first.

**Interfaces:**
- Consumes: complete module.
- Produces: evidence for each acceptance criterion and no unsupported completion claim.

- [ ] **Step 1: Run the full clean verification suite**

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
node scripts/verify-savings-schema.mjs
npx.cmd expo export --platform web --output-dir .tmp-savings-web
```

Expected: all commands exit 0. Remove `.tmp-savings-web` only after confirming the export result and resolved target path.

- [ ] **Step 2: Run Supabase verification**

Prove contribution insert/delete recalculates the parent balance, goal delete cascades history, invalid amounts fail constraints, and two authenticated test users are isolated by RLS. If remote/local database access is unavailable, explicitly keep the goal incomplete and request only the missing database action.

- [ ] **Step 3: Run responsive UI verification**

Verify at a small Android viewport and Honor 200 dimensions:

- list empty/populated/error states;
- create with date picker and keyboard visible;
- detail progress/suggestion/history;
- contribution add/delete;
- goal edit/delete;
- navigation back to a refreshed list and dashboard;
- no clipped content at top, bottom, or keyboard boundary.

- [ ] **Step 4: Review React and Supabase security checklists**

Confirm hook dependencies, stable keys, accessible Pressables, no duplicate server-state mirrors, owner predicates in every RLS policy, update `USING` plus `WITH CHECK`, no public executable security-definer function, and no service-role key in mobile files.

- [ ] **Step 5: Audit FRSG-01 through FRSG-05 against authoritative evidence**

Record one source/test/runtime proof per requirement. Treat missing live persistence or UI evidence as incomplete rather than inferred success.

- [ ] **Step 6: Commit verification fixes, if any**

Stage only Savings-related files and use a focused commit message such as:

```powershell
git commit -m "fix: close savings goal verification gaps"
```
