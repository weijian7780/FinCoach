# Budget and Category Limit Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build FRBL-01 through FRBL-05 as a working Expo/Supabase module with custom categories, monthly overall budgets, per-category limits, progress states, update/delete flows, and a transaction-ready zero-spending boundary.

**Architecture:** Preserve `budgets` as the existing category-limit table, add `monthly_budgets` as its monthly parent, and extend `categories` for user-owned custom rows. Keep calculations in pure TypeScript, database access in an injected Supabase client layer, and route/UI code focused on presentation and interaction.

**Tech Stack:** React Native 0.85, Expo SDK 56, Expo Router, TypeScript 6, Supabase/PostgreSQL with RLS, Vitest.

## Global Constraints

- Implement only Budget and Category Limit Management FRBL-01 through FRBL-05.
- Spending is RM 0 with `No transactions recorded` until Transaction Management exists.
- Do not add SVG, native date-picker, chart, OCR, notification, reporting, export, backup, or AI dependencies.
- Preserve existing `budgets.id bigint`, `categories.id bigint`, and all existing rows.
- Use `uuid` only for the new independent `monthly_budgets.id`; relationships use compatible columns.
- Do not commit, branch, push, or create a worktree; the user handles GitHub.

---

### Task 1: Pure budget domain rules

**Files:**
- Create: `src/lib/budget-domain.test.ts`
- Create: `src/lib/budget-domain.ts`

**Interfaces:**
- Produces: `monthKey`, `shiftMonth`, `formatBudgetMonth`, `parseBudgetMoney`, `formatBudgetMoney`, `getLimitMetrics`, `getLimitStatus`, `validateMonthlyBudget`, `validateCategoryAllocation`, and `validateCustomCategory`.
- Consumes: no application services; all functions are pure.

- [ ] Write failing Vitest cases for valid/invalid money, month boundaries, remaining and exceeded values, uncapped percentages, all four status thresholds, combined-allocation validation, and custom-category validation.
- [ ] Run `npm.cmd test -- src/lib/budget-domain.test.ts` and verify failure is caused by the missing implementation module.
- [ ] Implement the smallest pure functions that satisfy the tests, using two-decimal RM normalization and first-of-month ISO keys.
- [ ] Run the focused test, then `npm.cmd test`, and confirm all tests pass.

### Task 2: Supabase schema, RLS, and migration

**Files:**
- Create via Supabase CLI: `supabase/migrations/<timestamp>_complete_budget_category_limit_management.sql`
- Modify: `supabase/schema.sql`
- Modify: `src/lib/types.ts`
- Modify: `scripts/verify-savings-schema.mjs` only if a shared schema verifier is clearly reusable; otherwise create `scripts/verify-budget-schema.mjs`.

**Interfaces:**
- Produces: `MonthlyBudget`, `CategoryLimit`, `BudgetCategory`, and write-input types.
- Database contract: `monthly_budgets(user_id, month, limit_amount)` parent; `budgets(user_id, category_id, month, amount)` child; `categories.user_id/color` custom-category extension.

- [ ] Run `npx.cmd supabase --version`, `npx.cmd supabase migration --help`, and `npx.cmd supabase migration new complete_budget_category_limit_management` rather than inventing a filename.
- [ ] Add a failing structural verifier for required tables/columns, positive and first-day constraints, composite parent-child FK, allocation triggers, grants, RLS, ownership predicates, and default/custom category policies.
- [ ] Run the verifier and confirm it fails on the missing migration.
- [ ] Write idempotent SQL that migrates existing category-limit rows, creates the parent table, extends categories, adds compatible constraints/FK/triggers, and recreates secure policies.
- [ ] Mirror the final schema in `supabase/schema.sql`, add TypeScript row/input types, and rerun the structural verifier.
- [ ] Run `npx.cmd supabase db lint --help`; if the linked/local database is available, run the applicable lint/advisor command without applying destructive changes.

### Task 3: Budget data-client operations

**Files:**
- Create: `src/lib/budget.test.ts`
- Create: `src/lib/budget.ts`

**Interfaces:**
- Produces: `fetchBudgetMonth`, `upsertMonthlyBudget`, `deleteMonthlyBudget`, `upsertCategoryLimit`, `deleteCategoryLimit`, `fetchBudgetCategories`, `createCustomCategory`, `updateCustomCategory`, and `deleteCustomCategory`.
- Consumes: types from `src/lib/types.ts` and the shared Supabase client.

- [ ] Write failing injected-client tests that verify table names, user/month filters, category ordering, upsert conflict keys, update/delete ownership filters, returned-row requirements, and error propagation.
- [ ] Run `npm.cmd test -- src/lib/budget.test.ts` and verify expected missing-export failures.
- [ ] Implement a narrow chainable client boundary following `src/lib/savings.ts`, without exposing service keys or bypassing RLS.
- [ ] Run focused and full tests.

### Task 4: Shared Budget UI components

**Files:**
- Create: `src/components/budget/month-selector.tsx`
- Create: `src/components/budget/budget-progress.tsx`
- Create: `src/components/budget/status-badge.tsx`
- Create: `src/components/budget/money-field.tsx`
- Create: `src/components/budget/category-picker.tsx`
- Create: `src/components/budget/icon-color-picker.tsx`
- Create or modify structural component tests under `src/components/budget/`.

**Interfaces:**
- Components consume typed values/callbacks only; they do not query Supabase.
- Progress width is capped at 100%, while text uses the uncapped percentage.

- [ ] Add failing structural tests proving components avoid `react-native-svg` and `@react-native-community/datetimepicker` and expose accessible labels.
- [ ] Run focused tests and confirm failure.
- [ ] Implement pure React Native components using existing `AppText`, `AppTextInput`, Material icons, theme tokens, and pressed/disabled states.
- [ ] Rerun focused and full tests.

### Task 5: Budget overview tab

**Files:**
- Replace: `src/app/(app)/budget.tsx`

**Interfaces:**
- Consumes `fetchBudgetMonth`, domain metrics/status, `useAuth`, and routes `/budget/manage` and `/budget/categories`.
- Produces the selected-month Budget overview and explicit no-budget/no-transaction/error states.

- [ ] Add a failing route-structure test or extend the structural test to require month navigation, overall card, category cards, and explicit zero-transaction copy.
- [ ] Implement safe-area-aware scrolling, focus refresh, month selector, overall card, category breakdown, warning badges, retry action, and edit/category-management navigation.
- [ ] Verify month changes never mix records and no missing Transactions table is queried.

### Task 6: Manage Budget and Manage Categories screens

**Files:**
- Create: `src/app/budget/manage.tsx`
- Create: `src/app/budget/categories.tsx`
- Modify: `src/app/_layout.tsx`

**Interfaces:**
- Manage Budget consumes domain validation and budget/category client writes.
- Manage Categories permits CRUD only for rows owned by the current user; system defaults remain read-only.

- [ ] Add failing structural tests for route registration, save/delete actions, loading disablement, confirmation alerts, custom-category ownership checks, and inline errors.
- [ ] Implement Manage Budget with overall amount, per-category limits, allocation summary, create/update/delete, input preservation, and error translation.
- [ ] Implement Manage Categories with default/custom sections, name/icon/colour form, edit/delete confirmation, and duplicate-name feedback.
- [ ] Run focused tests, full tests, and TypeScript typecheck.

### Task 7: Home dashboard integration and acceptance documentation

**Files:**
- Modify: `src/app/(app)/index.tsx`
- Modify: `docs/acceptance-tests.md`

**Interfaces:**
- Home reads only the current `monthly_budgets` limit and continues to use RM 0 spent until Transaction Management exists.

- [ ] Add a failing test for current-month parent-budget selection and zero-spending remaining calculation.
- [ ] Replace the profile allowance placeholder as the budget source, link View Details to the Budget tab, and keep Add Expense as Coming Soon.
- [ ] Add FRBL-01–05 acceptance checks for CRUD, month isolation, status thresholds, RLS isolation, reload persistence, and Honor 200 layout.
- [ ] Run focused and full tests.

### Task 8: Complete verification

**Files:**
- Verify all changed files; do not commit.

- [ ] Run `npx.cmd expo install --check`.
- [ ] Run `npm.cmd test` and confirm zero failures.
- [ ] Run `npm.cmd run typecheck` and confirm exit 0.
- [ ] Run focused lint on all Budget files and touched integration files with caching disabled.
- [ ] Run `node scripts/verify-budget-schema.mjs` and confirm every schema/RLS assertion passes.
- [ ] Run `npx.cmd expo export --platform android` to a temporary output directory and confirm the Android bundle succeeds.
- [ ] Review `git diff --check` and `git status --short`, preserving unrelated user changes.
- [ ] Report any validation that requires the user's live Supabase SQL editor or physical Honor 200 separately; do not claim those checks ran locally.
