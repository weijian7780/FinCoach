# Financial Report and Analytics Design

Date: 2026-07-16

## Objective

Complete the FinCoach Financial Report and Analytics module with real, user-owned Supabase data while preserving the existing Expo Router, Supabase, Transaction, Budget, Savings, Profile, and FinCoach visual architecture.

## Approved scope

The module will provide:

- real income, expense, and net-balance summaries;
- spending breakdowns by category;
- monthly income and expense trends;
- budget-versus-actual comparisons;
- savings-goal progress in the selected reporting period context;
- current month, previous month, recent-month, and custom date-range filters;
- an optional category filter;
- persisted report-generation records and recent report history;
- loading, refreshing, empty, validation, and retry states.

The module will not use mock financial values. Every displayed value will be calculated from the authenticated user's current Supabase records.

## Thesis and DFD alignment

The current thesis defines the Financial Report and Analytics module as a separate module from AI Financial Coaching. Its Level 1 flow is:

1. Compile Financial Data (7.1) from profile, transactions, budgets, and savings goals using a user-selected period or category.
2. Generate Report and Analytics (7.2) by calculating spending summaries, category breakdowns, and trend analytics, then storing a report record.
3. Display Report Dashboard (7.3) using the generated report and report history.

The survey requirements specifically mention charts, summaries, budget comparisons, and monthly reports. The implementation therefore includes these deterministic analytics and excludes LLM-generated advice.

## Explicit non-goals

- No AI-generated insight, recommendation, prediction, or financial advice.
- No RAG, LLM, FastAPI, or AI Coach integration.
- No CSV/PDF export or backup; those belong to Financial Data Export and Backup Management.
- No bank integration or automatic transaction import.
- No mutation of transaction, budget, savings, or profile records from the Reports screen.
- No new charting dependency; charts use accessible React Native views and text.
- No duplicated reporting snapshot payload outside the current ERD.

## Existing-state findings

- `src/app/reports.tsx` is a static shell with hard-coded `RM 0` content.
- The Home screen already derives a current-month expense total, but it does not provide a reusable report model.
- Real user-owned transactions, categories, monthly budgets, category limits, savings goals, and profiles already exist in the active schema and mobile data clients.
- Transaction amounts are stored as positive values; `categories.type` determines income or expense.
- `public.reports` and the TypeScript `Report` type already exist as ERD-aligned report-generation metadata, but no current migration installs that table reproducibly.
- The working tree contains ongoing changes from previously implemented modules. Report work must avoid overwriting them.

## Architecture decision

Use a hybrid client/report-log architecture:

- Supabase returns only the authenticated user's source records for the selected range.
- Pure TypeScript domain functions calculate the report model on-device.
- The existing `public.reports` table records each explicit report-generation request as metadata.
- The dashboard renders the calculated model and recent report-generation history.

This approach is appropriate for the current student-scale dataset, keeps calculations testable, avoids privileged database functions, and preserves the current ERD. A database reporting RPC or materialized analytics table can be introduced later only if measured data volume makes client aggregation too slow.

## Data architecture

### Existing source data

The report compiler reads:

- `profiles`: user context shown in the report heading where appropriate;
- `transactions` joined with `categories`: amount, date, source, and income/expense classification;
- `monthly_budgets`: overall limits for months intersecting the selected period;
- `category_limits`: category limits for months intersecting the selected period;
- `savings_goals`: current and target amounts for savings progress;
- `reports`: recent report-generation metadata.

Every query includes an explicit `user_id` filter even though RLS also enforces ownership.

### `reports`

The existing ERD-aligned table remains metadata-only:

- `id bigint generated always as identity primary key`;
- `user_id uuid not null references auth.users(id) on delete cascade`;
- `period text not null`;
- `type text not null`;
- `generated_at timestamptz not null default now()`.

`period` stores a canonical selection such as `2026-07`, `2026-05..2026-07`, or `2026-07-01..2026-07-16`. `type` stores exactly one of `monthly`, `monthly_category`, `multi_month`, `multi_month_category`, `custom`, or `custom_category`. This records whether a category filter was used without adding fields outside the current ERD.

The implementation adds an index on `(user_id, generated_at desc)` for history retrieval.

### RLS and Data API access

- RLS remains enabled on `reports`.
- Authenticated users can select and insert only rows where `(select auth.uid()) = user_id`.
- Update and delete operations are not exposed because a generated-report log is immutable.
- Explicit Data API grants expose only `select` and `insert` to `authenticated`.
- The identity sequence grants only the minimum usage needed for inserts.
- Anonymous users receive no access.

This follows current Supabase guidance to enable RLS on exposed tables, use the `TO authenticated` role, apply an ownership predicate, and add explicit user filters to client queries.

## Report domain model

Pure functions in `src/lib/report-domain.ts` will produce a `FinancialReport` containing:

- normalized start and end dates;
- period label and report type;
- total income;
- total expenses;
- net balance (`income - expenses`);
- transaction count;
- category totals, percentages, and transaction counts;
- monthly income, expense, and net trend points;
- overall budget limit, actual expense, remaining amount, and usage percentage;
- category-limit actuals for visible expense categories;
- savings total, target total, remaining amount, and progress percentage.

Money is rounded consistently to two decimal places at report boundaries. Percentages are clamped only for visual progress bars; raw over-budget percentages remain available for labels.

## Filtering rules

- Period filters use Malaysia local calendar dates, not UTC `toISOString()` date truncation.
- The selected range is inclusive at both ends.
- Current month and previous month resolve from the device's local date.
- Recent-month selection covers complete calendar months including the current month.
- Custom ranges require valid `YYYY-MM-DD` start and end dates, with start not after end.
- Category filtering applies to transaction totals and category charts while budget and savings context remain clearly labelled as overall data.
- Income and expense classification comes only from the joined category type.

## Mobile data client

`src/lib/reports.ts` will provide an injected-client boundary consistent with existing module clients:

- `fetchReportSourceData(userId, selection)`;
- `createReportRecord(userId, selection)`;
- `fetchRecentReports(userId, limit)`;

The source query is date-bounded. Related budget queries are bounded to intersecting month keys. The reports-history query is ordered newest first and limited.

If source-data retrieval succeeds but report-log insertion fails, the calculated report remains visible with a clear warning that history was not saved. Financial source records are never modified.

## Reports screen

`src/app/reports.tsx` will replace the static shell with:

- FinCoach page bar and back action;
- period selector and category filter;
- Generate Report action;
- pull-to-refresh support;
- summary cards for Income, Expenses, and Net Balance;
- budget comparison card with used, remaining, and over-budget states;
- category breakdown using proportional horizontal bars and RM labels;
- monthly trend using accessible vertical bars with text summaries;
- savings progress card;
- recent generated-report history;
- loading skeleton/state, first-use empty state, filtered empty state, inline error, and retry action.

Charts will not rely on colour alone. Each value will also have a text label, and zero-data ranges will show an explanatory empty state instead of misleading zero-filled graphics.

## Data flow

1. The signed-in user opens Reports.
2. The screen resolves a current-month default selection and loads available categories and recent report history.
3. The user selects a period and optional category, then taps Generate Report.
4. The client validates the selection and fetches real owner-scoped source data from Supabase.
5. Pure domain functions calculate the report model.
6. The client inserts one immutable `reports` metadata row.
7. The dashboard renders the calculated report and refreshes recent history.
8. Refresh reruns the active report from current source records without creating another history row.

## Error handling

- Missing session: redirect through the existing authentication boundary rather than query anonymously.
- Invalid custom period: show field-level validation and do not query Supabase.
- Source query failure: keep the last successful report visible when available and show Retry.
- Report-history failure: keep the analytics dashboard usable and show history as unavailable.
- Report-log insertion failure: show the real calculated report with a non-blocking history-save warning.
- Empty selected range: show zero summary values with a clear no-transactions state; budget and savings context may still appear if available.
- Partial source failure: do not silently calculate a misleading report from incomplete financial data; report generation fails and identifies the unavailable source area.
- Duplicate taps: disable Generate while the request is in progress.

## Security and privacy

- All financial queries use the signed-in user's Supabase session and explicit owner filters.
- `reports` RLS isolates history by owner.
- No service-role key enters the mobile application.
- No raw financial data is sent to an LLM or FastAPI service.
- Report history stores only period/type metadata, not duplicated financial details.
- UI error messages do not expose SQL, tokens, or internal Supabase responses.

## Testing strategy

Implementation follows red-green-refactor.

### Domain tests

- income, expense, and net calculations;
- category totals, ordering, percentages, and zero totals;
- monthly trend generation across missing months;
- overall and category budget comparisons, including over-budget values;
- savings aggregation and zero-target handling;
- inclusive date filtering and optional category filtering;
- Malaysia-local current/previous month boundaries;
- rounding and empty datasets.

### Data-client tests

- explicit owner and date filters;
- joined category selection;
- bounded budget and savings retrieval;
- report-record insert shape;
- recent-history ordering and limit;
- error propagation and partial-failure prevention.

### UI tests

- loading, populated, empty, filtered-empty, error, and refresh states;
- period/category selection and custom-range validation;
- Generate button duplicate-submit prevention;
- income, expense, net, budget, category, trend, savings, and history sections;
- non-blocking report-history save warning;
- absence of mock values and AI-insight labels.

### Schema verification

- `reports` fields, foreign key, `type` constraint, grants, index, and immutable operation set;
- RLS enabled;
- user A can select and insert only user A report records;
- user A cannot access user B records;
- anonymous access is denied.

### Build and acceptance verification

- focused report tests;
- complete mobile test suite;
- TypeScript typecheck;
- ESLint with pre-existing issues distinguished from new issues;
- Android production JavaScript export;
- Honor 200 acceptance test using real manual and scanned transactions.

## Acceptance criteria

- No static or mock financial amount remains on the Reports screen.
- A signed-in user can generate reports from real Supabase data for supported periods and categories.
- Income, expenses, net balance, category breakdown, trends, budget comparison, and savings progress are mathematically correct.
- Dates respect the Malaysia local calendar.
- An explicit report-generation request creates an owner-scoped report-history record.
- Refresh recalculates the active report without creating duplicate history entries.
- Empty and failed requests are clearly distinguishable.
- Users cannot read or mutate another user's report history.
- Charts remain understandable without relying on colour alone.
- The screen follows the current FinCoach visual direction.
- No AI insight, RAG, LLM, FastAPI, export, or backup behavior is pulled into this module.

## Requirement traceability

| Thesis/DFD requirement | Design evidence |
|---|---|
| User-selected month/category filter | Period selector, custom range, and category filter |
| Compile profile, transaction, budget, and savings data | Owner-scoped source-data client |
| Spending summaries | Income, expense, net, and transaction-count cards |
| Category breakdown | Proportional category bars and totals |
| Trend analytics | Monthly income/expense/net trend model and chart |
| Budget comparison and monthly report | Budget card and calendar-period reporting |
| Store report record in D7 | Immutable `reports` metadata insert |
| Display report dashboard and history | Reports screen plus recent report records |
| AI remains separate | Explicit non-goal and no backend/LLM data flow |
