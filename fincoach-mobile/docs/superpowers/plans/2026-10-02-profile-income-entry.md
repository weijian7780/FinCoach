# Preferences Income Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user requested a plan first; do not start implementation until instructed.

**Goal:** Let users turn their expected monthly income from Preferences into a confirmed income transaction that contributes to Reports alongside manually entered income.

**Architecture:** Reuse the existing manual transaction screen, with a profile-income prefill mode. Save one ordinary transaction per confirmed payment; Reports continues to total saved transactions. Add reusable draft recovery and advisory duplicate detection using the existing transaction table.

**Tech Stack:** Existing TypeScript, React Native, Expo SDK 56, Expo Router, Supabase, and Vitest; no additional dependencies.

**Spec:** `docs/superpowers/specs/2026-10-02-profile-income-entry-design.md`.

## Global Constraints

- Preferences stores the expected monthly amount. Saving or changing this value does not create transactions or rewrite historical income.
- The route passes only `prefill=profile_income`; read the saved profile for the current authenticated user inside the transaction screen. Do not place financial amounts in route parameters.
- Similar-entry detection is advisory. Separate legitimate payments, including two equal installments, are allowed. Do not enforce one income transaction per month.
- Use the existing schema, owner filters, and Row Level Security. No database migration, backend deployment, dependency change, or automatic recurring income is required for this scope.
- Preserve FinCoach's existing UI, use AppText/AppTextInput, safe-area insets, and scrollable forms. Verify the changed screens on Honor 200 and a small Android screen.
- Implementation is native in the current chat unless the user explicitly requests delegation. Preserve existing workspace changes and stage only intended changes if committing is later requested.

## Review Focus

- Unsaved Preferences: record from the values the user explicitly saves; partial profile-save failures keep the user on Preferences.
- Mixed, Other, missing income categories, and invalid amounts: require accurate user entry and retain Income mode.
- Repeated taps and an uncertain network result: one draft ID, owner-scoped read recovery, and no automatic repeated writes.
- Equal installments, manual matches, query overflow, and check failure: advisory review permits actual extra payments without silently losing duplicate warnings.
- Reopening/editing forms, profile changes during a draft, and report filters: preserve typed input and count only matching saved transactions.

## File responsibilities

| File | Responsibility |
|---|---|
| `src/lib/transaction-domain.ts` | Pure profile-income defaults, money/source matching, and draft-payload equality |
| `src/lib/transactions.ts` | Owner-scoped similar-income queries and create recovery |
| `src/app/profile/edit.tsx` | Record action, expected-income wording, save-before-navigation flow |
| `src/app/profile/setup.tsx` | Consistent expected-income wording |
| `src/app/transactions/manage.tsx` | One-time prefill, explicit confirmation, duplicate review, and stable save draft |
| `src/lib/transaction-domain.test.ts` | Defaults and matching rules |
| `src/lib/transactions.test.ts` | Actual query filters, recovery behavior, and errors using existing client injection |
| `src/lib/report-domain.test.ts` | Combined manual and profile-prefilled income totals and filters |
| `docs/acceptance-tests.md` | Device and real-record acceptance checklist |

## Task 1: Define income draft and matching rules

**Files:** Modify `src/lib/transaction-domain.ts`; test `src/lib/transaction-domain.test.ts`.

**Interfaces:**
- Consumes existing `Profile`, `Category`, `TransactionWithCategory`, `TransactionWriteInput`, and `TransactionFormInput` types; use `parseMoney` and the supplied Malaysia-local date.
- Produces `buildProfileIncomeDraft(profile: Pick<Profile, 'monthly_allowance' | 'income_source'>, categories: Category[], today: string): TransactionFormInput | null`.
- Produces `findSimilarIncomeEntries(entries: TransactionWithCategory[], draft: TransactionFormInput): TransactionWithCategory[]` and `transactionMatchesInput(transaction: TransactionWithCategory, input: TransactionWriteInput): boolean`.

- [ ] Add behavioral tests: RM2,000 yields Income, amount `2000`, supplied date, editable defaults, and a source-matching income category or generic Income category. Mixed/Other leave source empty. Invalid/empty/nonpositive income returns null. Missing eligible category yields `categoryId: null`, never an expense default.
- [ ] Add matching tests: same category/amount/month plus trimmed, case-insensitive source matches; a different amount/category/month/source does not. Equal installments remain separate candidate rows. Payload equality compares actual persisted fields, including receipt path, without rewriting them.
- [ ] Run `npm test -- src/lib/transaction-domain.test.ts` and confirm new tests fail before implementing the helpers.
- [ ] Implement those signatures alongside existing transaction validation; validate again at submission. Use amount parsing to compare monetary values rather than raw strings.
- [ ] Rerun the targeted command; all domain tests must pass.

## Task 2: Add bounded duplicate queries and safe create recovery

**Files:** Modify `src/lib/transactions.ts`; test `src/lib/transactions.test.ts`.

**Interfaces:**
- Consumes the existing client-injected transaction CRUD functions and `transactionMatchesInput` from Task 1.
- Produces `fetchIncomeCandidates(userId: string, input: Pick<TransactionWriteInput, 'category_id' | 'amount' | 'transaction_date'>, client?: TransactionDataClient): Promise<{ entries: TransactionWithCategory[]; truncated: boolean }>`.
- Produces `createTransactionWithRecovery(userId: string, input: TransactionWriteInput, client?: TransactionDataClient): Promise<TransactionWithCategory>` and `TransactionDraftConflictError`, carrying the existing owner-visible row.

- [ ] Add query tests asserting `transactions`, owner ID, category, amount, first/last date of the chosen month, category detail selection, and a 51-row limit. Return at most 50 display rows and `truncated: true` if the sentinel is present. Cover December/January boundaries and propagate errors.
- [ ] Add recovery tests: a first save inserts one row; a thrown insert with an owner-visible matching ID returns that existing row after a recovery read; missing recovery row preserves the save error; owner-visible conflicting payload throws `TransactionDraftConflictError`; inaccessible owner data is never treated as success. No case automatically repeats the insert.
- [ ] Run `npm test -- src/lib/transactions.test.ts` and confirm the new tests fail before implementation.
- [ ] Extend the existing query type with `gte`, `lte`, and `limit`. Implement bounded candidates using numeric amount filters and Malaysia calendar month bounds.
- [ ] Implement create recovery: call the existing insert once; after an uncertain result or ID conflict, perform an owner-scoped read of the same ID. Return an exact matching row, surface a conflicting existing row for review, or retain the error. Do not use upsert to overwrite an earlier financial entry.
- [ ] Rerun the targeted command; all persistence tests must pass.

## Task 3: Connect Preferences to the existing Income form

**Files:** Modify `src/app/profile/edit.tsx`, `src/app/profile/setup.tsx`, and `src/app/transactions/manage.tsx`.

**Interfaces:**
- Consumes `buildProfileIncomeDraft`, `fetchIncomeCandidates`, `findSimilarIncomeEntries`, `createTransactionWithRecovery`, and existing `appDialog`, `useAuth`, `malaysiaToday`, transaction validation, and alert synchronization.
- Extends profile save to `save(destination: 'back' | 'record_income' = 'back'): Promise<void>`; the normal save still returns to its existing destination.
- Uses `/transactions/manage` with only `prefill: 'profile_income'`. Existing `transactionId` edit requests take precedence.

- [ ] Update the two profile field labels and helper text to the exact spec copy; add `Record monthly income` in edit Preferences with positive-amount gating.
- [ ] Compare current editable values, including tracked categories, with their loaded baseline. If dirty, show `Save & continue` / `Cancel`; the former reuses profile and tracked-category saving and navigates only after success. The action never inserts income itself.
- [ ] In the transaction screen, initialize a profile-income draft once after its saved profile and categories are loaded. Use Task 1 defaults; retain editable amount/source/category/date/note. Missing or invalid saved amounts offer normal Income entry with a clear message rather than creating data. Edits load their stored values regardless of a prefill parameter.
- [ ] Keep one UUID for each new form draft. Guard the submit handler with a synchronous ref as well as its disabled button. Preserve the UUID and attempted payload through a failed/uncertain save; resolve an existing record before offering to record changed input as a new payment.
- [ ] For new Income entries, run the owner-scoped similarity check using current validated values. Display existing dates, sources, and amounts; `Review entries` opens Transactions, `Cancel` writes nothing, and `Record another payment` continues with the reviewed draft. Query overflow produces a broader warning. Check failures offer `Retry check` / `Cancel`. Any later form edits invalidate the confirmation.
- [ ] Use `createTransactionWithRecovery` for new manual entries and existing `updateTransaction` for edits. Once persistence succeeds, retain existing alert synchronization and navigation. Retry of alert synchronization must not insert a transaction again.
- [ ] Manually verify invalid amounts, unsaved Preferences, partial save failure, all six source types, missing income categories, cancellation, existing transaction edits, background profile updates, and double taps. Prefer behavioral tests for extracted helpers over tests that inspect source strings.
- [ ] Run `npm run typecheck` and `npm run lint`; fix introduced failures while preserving unrelated workspace changes.

## Task 4: Verify totals and record acceptance evidence

**Files:** Test `src/lib/report-domain.test.ts`; update `docs/acceptance-tests.md`. Existing Reports code is expected to require no production changes.

**Interfaces:**
- Consumes ordinary `TransactionWithCategory` rows produced by both entry paths and existing `compileFinancialReport(source, selection)`.
- Produces regression evidence for the spec's numerical examples and a device acceptance checklist.

- [ ] Add a report regression that uses the Task 1 prefill amount and a second manually entered amount: one saved RM2,000 allowance plus RM500 earnings totals RM2,500; RM300 expenses yield RM2,200 net balance.
- [ ] Cover editing RM2,000 to RM1,900 and deleting it; verify totals change by exactly the edited/deleted amount. Include an out-of-period income and a nonmatching category to prove active filters are honored.
- [ ] Run `npm test -- src/lib/transaction-domain.test.ts src/lib/transactions.test.ts src/lib/report-domain.test.ts src/lib/report-ui.test.ts src/lib/reports.test.ts`, then typecheck and lint after any source repairs. Report counts and failures accurately.
- [ ] On an authorized test account, record and inspect real rows for the RM2,000 shortcut and RM500 manual entry. Reopen/refresh Reports and verify RM2,500. Changing Preferences alone must leave the recorded total unchanged. Test cancel, edit, delete, equal installments, matching manual entries, network-result recovery, and owner isolation. Use a disposable fixture and remove only its test rows.
- [ ] Check changed forms on Honor 200 and a small Android screen for safe-area, keyboard, and scrolling behavior. Use Expo development-build hot reload for these JavaScript changes; build an APK only if the user requests delivery.
- [ ] Record separately which checks were local automated tests, real Supabase evidence, and device observations. If a device or test account is unavailable, report that limitation rather than claiming it passed.

## Review and handoff

- Planning artifacts are the only changes for this request. Await the user's implementation instruction.
- Once approved, execute the tasks in this chat. No commit, migration application, backend deployment, or APK release is implied by the request for a plan.
- Before any requested commit, inspect diffs and selectively stage intended files/hunks because the current workspace already contains unrelated changes.

