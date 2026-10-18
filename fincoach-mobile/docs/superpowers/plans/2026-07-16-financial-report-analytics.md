# Financial Report and Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static Reports route with a tested, real-data dashboard that compiles owner-scoped Supabase financial records, calculates deterministic analytics, and records report-generation history.

**Architecture:** Date and analytics rules live in pure TypeScript domain functions. A focused Supabase data client loads bounded transactions, budgets, savings, and report history with explicit owner filters. The Expo screen orchestrates generation and renders small accessible report components; the existing ERD `reports` table stores immutable generation metadata.

**Tech Stack:** React Native 0.85, Expo SDK 56, Expo Router, TypeScript 6, Supabase JS 2.108, PostgreSQL/RLS, Vitest 4.

## Global Constraints

- Use real Supabase records only; no static or mock financial values in production UI.
- Keep AI insight, RAG, LLM, FastAPI, export, and backup outside this module.
- Use Malaysia-local calendar dates; do not derive report dates with UTC `toISOString()` truncation.
- Keep `public.reports` metadata-only and aligned with the existing ERD.
- Add no charting or native date-picker dependency.
- Preserve all unrelated dirty-worktree changes and stage only report-module files if committing.
- Apply owner-scoped RLS with `TO authenticated` and `(select auth.uid()) = user_id`.

## File map

- Create `src/lib/report-domain.ts`: date selections, validation, aggregation, formatting, and report model.
- Create `src/lib/report-domain.test.ts`: pure date and analytics behavior.
- Create `src/lib/reports.ts`: owner-scoped Supabase report source/history client.
- Create `src/lib/reports.test.ts`: query construction, ownership, and errors.
- Create `src/lib/report-ui.test.ts`: structural route/component regression checks.
- Create `src/components/reports/report-components.tsx`: summary, budget, category, trend, savings, filters, and history views.
- Modify `src/lib/types.ts`: report source, selection, analytics, and constrained report types.
- Replace `src/app/reports.tsx`: real report orchestration and states.
- Modify `supabase/schema.sql`: harden the existing reports table definition, constraint, index, grants, and RLS.
- Create a CLI-generated `supabase/migrations/*_complete_financial_report_analytics.sql`: reproducible reports-table deployment.
- Create `scripts/verify-report-schema.mjs`: schema/RLS verifier.
- Modify `docs/acceptance-tests.md`: physical-device and real-data report checks.

---

### Task 1: Pure report dates and analytics

**Files:**
- Create: `src/lib/report-domain.test.ts`
- Create: `src/lib/report-domain.ts`
- Modify: `src/lib/types.ts`

**Interfaces:**
- Consumes: existing `TransactionWithCategory`, `MonthlyBudget`, `CategoryLimit`, and `SavingsGoal` types.
- Produces: `ReportSelection`, `ReportSourceData`, `FinancialReport`, `createPresetSelection()`, `validateReportSelection()`, `monthKeysForRange()`, `compileFinancialReport()`, `formatReportMoney()`, and `formatReportPeriod()`.

- [ ] **Step 1: Write failing date-selection tests**

```ts
import { describe, expect, test } from 'vitest';
import {
  createPresetSelection,
  monthKeysForRange,
  validateReportSelection,
} from './report-domain';

describe('report selections', () => {
  test('uses Malaysia-local dates around a UTC day boundary', () => {
    const now = new Date(2026, 6, 16, 0, 30);
    expect(createPresetSelection('current_month', now)).toMatchObject({
      startDate: '2026-07-01',
      endDate: '2026-07-31',
      reportType: 'monthly',
    });
  });

  test('resolves previous and recent months across year boundaries', () => {
    const now = new Date(2026, 0, 4, 12);
    expect(createPresetSelection('previous_month', now)).toMatchObject({
      startDate: '2025-12-01',
      endDate: '2025-12-31',
    });
    expect(monthKeysForRange('2025-11-10', '2026-01-04')).toEqual([
      '2025-11-01',
      '2025-12-01',
      '2026-01-01',
    ]);
  });

  test('rejects malformed or reversed custom ranges', () => {
    expect(validateReportSelection({
      preset: 'custom', startDate: '2026-07-31', endDate: '2026-07-01',
      categoryId: null, reportType: 'custom',
    })).toBe('Start date must be on or before end date.');
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- src/lib/report-domain.test.ts`

Expected: FAIL because `report-domain.ts` does not exist.

- [ ] **Step 3: Add the exact report types**

Append to `src/lib/types.ts`:

```ts
export type ReportPreset = 'current_month' | 'previous_month' | 'last_3_months' | 'custom';
export type ReportType =
  | 'monthly'
  | 'monthly_category'
  | 'multi_month'
  | 'multi_month_category'
  | 'custom'
  | 'custom_category';

export type ReportSelection = {
  preset: ReportPreset;
  startDate: string;
  endDate: string;
  categoryId: number | null;
  reportType: ReportType;
};

export type ReportSourceData = {
  transactions: TransactionWithCategory[];
  monthlyBudgets: MonthlyBudget[];
  categoryLimits: CategoryLimit[];
  savingsGoals: SavingsGoal[];
};

export type ReportCategoryTotal = {
  categoryId: number;
  name: string;
  color: string | null;
  amount: number;
  percentage: number;
  transactionCount: number;
};

export type ReportTrendPoint = {
  month: string;
  income: number;
  expenses: number;
  net: number;
};

export type FinancialReport = {
  selection: ReportSelection;
  totalIncome: number;
  totalExpenses: number;
  netBalance: number;
  transactionCount: number;
  categoryTotals: ReportCategoryTotal[];
  trend: ReportTrendPoint[];
  budget: {
    limit: number;
    spent: number;
    remaining: number;
    exceeded: number;
    percentage: number;
    progressPercentage: number;
  };
  savings: {
    current: number;
    target: number;
    remaining: number;
    percentage: number;
    progressPercentage: number;
  };
};
```

Also change the existing `Report.type` from `string` to `ReportType`.

- [ ] **Step 4: Implement local-date selection helpers**

Create `src/lib/report-domain.ts` with local date construction (`new Date(year, month, day)`), `YYYY-MM-DD` formatting from local getters, strict round-trip date validation, inclusive month enumeration, and preset construction. `validateReportSelection()` must return exactly `null`, `Enter valid start and end dates.`, or `Start date must be on or before end date.`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `npm test -- src/lib/report-domain.test.ts`

Expected: PASS for the three selection tests.

- [ ] **Step 6: Add failing analytics tests**

Add fixtures with one income transaction, two expense categories, two monthly budgets, one category limit, one savings goal, and a category-filtered selection. Assert:

```ts
expect(compileFinancialReport(source, selection)).toMatchObject({
  totalIncome: 1500,
  totalExpenses: 350,
  netBalance: 1150,
  transactionCount: 3,
  budget: {
    limit: 2000,
    spent: 350,
    remaining: 1650,
    exceeded: 0,
    percentage: 17.5,
    progressPercentage: 17.5,
  },
  savings: {
    current: 500,
    target: 1000,
    remaining: 500,
    percentage: 50,
    progressPercentage: 50,
  },
});
expect(report.categoryTotals.map((item) => [item.name, item.amount])).toEqual([
  ['Food', 250],
  ['Transport', 100],
]);
expect(report.trend).toEqual([
  { month: '2026-06-01', income: 0, expenses: 100, net: -100 },
  { month: '2026-07-01', income: 1500, expenses: 250, net: 1250 },
]);
```

Add separate tests for zero data, over-budget values, missing trend months, two-decimal rounding, and category filtering while overall budget spending remains unfiltered.

- [ ] **Step 7: Run analytics tests and verify RED**

Run: `npm test -- src/lib/report-domain.test.ts`

Expected: FAIL because `compileFinancialReport` is not exported.

- [ ] **Step 8: Implement the minimal analytics compiler**

Implement `compileFinancialReport()` as a single pass over in-range transactions plus small reductions for categories, months, budgets, and savings. Use a private `roundMoney(value)` helper (`Math.round((value + Number.EPSILON) * 100) / 100`). Summary and trend respect `selection.categoryId`; budget spending uses all in-range expense transactions and is labelled overall. Sort categories by descending amount then name.

- [ ] **Step 9: Run focused tests and typecheck**

Run: `npm test -- src/lib/report-domain.test.ts && npm run typecheck`

Expected: report-domain tests PASS and TypeScript exits 0.

---

### Task 2: Owner-scoped Supabase report data client

**Files:**
- Create: `src/lib/reports.test.ts`
- Create: `src/lib/reports.ts`

**Interfaces:**
- Consumes: `ReportSelection`, `ReportSourceData`, and `Report`.
- Produces: `ReportDataClient`, `fetchReportSourceData(userId, selection, client?)`, `createReportRecord(userId, selection, client?)`, and `fetchRecentReports(userId, limit?, client?)`.

- [ ] **Step 1: Write failing query-construction tests**

Build one chainable fake per table and assert:

```ts
await fetchReportSourceData('user-1', selection, client);
expect(builders.get('transactions')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
expect(builders.get('transactions')?.gte).toHaveBeenCalledWith('transaction_date', '2026-05-01');
expect(builders.get('transactions')?.lte).toHaveBeenCalledWith('transaction_date', '2026-07-31');
expect(builders.get('monthly_budgets')?.gte).toHaveBeenCalledWith('month', '2026-05-01');
expect(builders.get('monthly_budgets')?.lte).toHaveBeenCalledWith('month', '2026-07-01');
expect(builders.get('savings_goals')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
```

Assert `createReportRecord()` inserts `{ user_id, period, type }`, selects the inserted row, and `fetchRecentReports()` applies owner filter, descending `generated_at`, and limit 10. Add one test that any source query error rejects the complete request.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- src/lib/reports.test.ts`

Expected: FAIL because `reports.ts` does not exist.

- [ ] **Step 3: Implement the data client**

Create a chainable `ReportQuery` interface with `select`, `eq`, `gte`, `lte`, `order`, `limit`, `insert`, and `single`. Implement four parallel, explicitly owner-filtered source queries and reject the whole source result if any query reports an error. Use `monthKeysForRange()` to bound budget tables. Format report periods through `formatReportPeriod(selection)`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `npm test -- src/lib/reports.test.ts`

Expected: all report data-client tests PASS.

---

### Task 3: Reproducible `reports` schema and RLS

**Files:**
- Modify: `supabase/schema.sql`
- Create with Supabase CLI: `supabase/migrations/*_complete_financial_report_analytics.sql`
- Create: `scripts/verify-report-schema.mjs`

**Interfaces:**
- Consumes: authenticated Supabase Data API access.
- Produces: immutable owner-scoped `public.reports` metadata storage.

- [ ] **Step 1: Create the migration through the installed CLI**

Run: `npx supabase migration new complete_financial_report_analytics`

Expected: the CLI prints the exact newly created migration path. Use that generated file; do not rename or invent a timestamp.

- [ ] **Step 2: Write the failing schema verifier**

Create `scripts/verify-report-schema.mjs` to read the generated migration and assert it contains:

```js
const required = [
  'create table if not exists public.reports',
  'reports_type_check',
  'reports_user_generated_idx',
  'alter table public.reports enable row level security',
  'for select to authenticated',
  'for insert to authenticated',
  '(select auth.uid()) = user_id',
  'revoke update, delete on table public.reports from authenticated',
];
```

Run: `node scripts/verify-report-schema.mjs`

Expected: FAIL before the migration SQL is added.

- [ ] **Step 3: Implement idempotent schema SQL**

The migration and canonical schema must:

```sql
create table if not exists public.reports (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  period text not null check (char_length(btrim(period)) between 7 and 50),
  type text not null,
  generated_at timestamptz not null default now()
);

alter table public.reports drop constraint if exists reports_type_check;
alter table public.reports add constraint reports_type_check check (type in (
  'monthly', 'monthly_category', 'multi_month',
  'multi_month_category', 'custom', 'custom_category'
));
create index if not exists reports_user_generated_idx
  on public.reports (user_id, generated_at desc);
alter table public.reports enable row level security;
revoke all on table public.reports from anon;
grant select, insert on table public.reports to authenticated;
revoke update, delete on table public.reports from authenticated;
grant usage, select on sequence public.reports_id_seq to authenticated;
drop policy if exists "Users can read own reports" on public.reports;
create policy "Users can read own reports" on public.reports
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can create own reports" on public.reports;
create policy "Users can create own reports" on public.reports
  for insert to authenticated with check ((select auth.uid()) = user_id);
```

Drop the old broad `Users manage own reports` policy.

- [ ] **Step 4: Verify the schema files**

Run: `node scripts/verify-report-schema.mjs`

Expected: `REPORT_SCHEMA_VERIFIED` and exit 0.

Do not run `supabase db push`; the existing migration-history mismatch must be reconciled first.

---

### Task 4: Accessible real-data report UI

**Files:**
- Create: `src/components/reports/report-components.tsx`
- Create: `src/lib/report-ui.test.ts`
- Replace: `src/app/reports.tsx`

**Interfaces:**
- Consumes: `FinancialReport`, `ReportSelection`, `Report`, `fetchTransactionCategories`, `fetchReportSourceData`, `createReportRecord`, and `fetchRecentReports`.
- Produces: a real Reports route with filters, generation, refresh, dashboard, and history states.

- [ ] **Step 1: Write failing structural UI tests**

Read the route and component source files and assert the route contains:

```ts
expect(route).toContain('fetchReportSourceData');
expect(route).toContain('compileFinancialReport');
expect(route).toContain('createReportRecord');
expect(route).toContain('fetchRecentReports');
expect(route).toContain('RefreshControl');
expect(route).toContain('Generate Report');
expect(route).not.toContain('RM 0');
expect(route).not.toContain('AI insight');
```

Assert components contain `Income`, `Expenses`, `Net Balance`, `Budget vs Actual`, `Spending by Category`, `Monthly Trend`, `Savings Progress`, `Recent Reports`, accessibility labels, percentage bars, and text fallbacks.

- [ ] **Step 2: Run the UI test and verify RED**

Run: `npm test -- src/lib/report-ui.test.ts`

Expected: FAIL because report components do not exist and the route remains static.

- [ ] **Step 3: Implement focused report components**

Export these components from `report-components.tsx`:

```ts
export function ReportFilters(props: {
  selection: ReportSelection;
  categories: Category[];
  onPresetChange: (preset: ReportPreset) => void;
  onCategoryChange: (categoryId: number | null) => void;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
  onGenerate: () => void;
  generating: boolean;
  validationError: string | null;
}): React.JSX.Element;

export function ReportDashboard(props: { report: FinancialReport }): React.JSX.Element;
export function ReportHistory(props: { reports: Report[]; unavailable: boolean }): React.JSX.Element;
```

Use existing `authColors`, `authFont`, `AppText`, `MaterialIcons`, `Pressable`, `View`, and horizontal/vertical React Native views. Every chart value also receives a text label. Use `TextInput` for custom `YYYY-MM-DD` values without a new native dependency.

- [ ] **Step 4: Replace the Reports screen orchestration**

The screen must:

```ts
const [selection, setSelection] = useState(() => createPresetSelection('current_month'));
const [report, setReport] = useState<FinancialReport | null>(null);
const [reports, setReports] = useState<Report[]>([]);
const [categories, setCategories] = useState<Category[]>([]);
const [loading, setLoading] = useState(true);
const [generating, setGenerating] = useState(false);
const [refreshing, setRefreshing] = useState(false);
const [error, setError] = useState<string | null>(null);
const [historyWarning, setHistoryWarning] = useState<string | null>(null);
```

On focus, load categories, recent history, and a current-month real-data preview without inserting history. `Generate Report` validates, loads source data, compiles, renders, then attempts an immutable history insert. Refresh reloads the active report without a second insert. Use `Promise.allSettled` only where a history failure may be safely isolated; never compile from partial financial sources.

- [ ] **Step 5: Run UI, domain, and client tests**

Run: `npm test -- src/lib/report-domain.test.ts src/lib/reports.test.ts src/lib/report-ui.test.ts`

Expected: all focused report tests PASS.

- [ ] **Step 6: Run TypeScript and focused lint**

Run: `npm run typecheck`

Expected: exit 0.

Run: `npx eslint src/app/reports.tsx src/components/reports/report-components.tsx src/lib/report-domain.ts src/lib/reports.ts`

Expected: exit 0 with no report-module errors.

---

### Task 5: Acceptance documentation and complete verification

**Files:**
- Modify: `docs/acceptance-tests.md`

**Interfaces:**
- Consumes: completed report implementation.
- Produces: reproducible automated and Honor 200 acceptance evidence.

- [ ] **Step 1: Add Financial Report and Analytics acceptance cases**

Add checks for real current/previous/custom periods; category filtering; income/expense/net math; empty ranges; budget under/over states; savings progress; missing trend months; report history insertion; refresh without duplicate history; owner isolation; offline retry; and readable charts on Honor 200. State explicitly that AI insights and export/backup are absent.

- [ ] **Step 2: Run the complete test suite**

Run: `npm test`

Expected: all tests PASS with zero failures.

- [ ] **Step 3: Run static verification**

Run: `npm run typecheck`

Expected: exit 0.

Run: `npm run lint`

Expected: no new report-module errors; any pre-existing repository issue must be reported exactly rather than hidden.

Run: `node scripts/verify-report-schema.mjs`

Expected: `REPORT_SCHEMA_VERIFIED`.

- [ ] **Step 4: Build the production JavaScript bundle**

Run: `npx expo export --platform android --output-dir .expo-report-export`

Expected: Android bundle export exits 0.

- [ ] **Step 5: Inspect the final diff**

Run: `git status --short` and `git diff --check`

Expected: only intended report files plus preserved pre-existing user changes; no whitespace errors.

- [ ] **Step 6: Perform physical Honor 200 acceptance**

Use real test records containing at least one income, two expense categories across two months, one budget, and one savings goal. Verify calculations, filters, charts, history insertion, refresh deduplication, offline retry, and cross-device history visibility. This physical-device step remains explicitly unverified until performed on the Honor 200.
