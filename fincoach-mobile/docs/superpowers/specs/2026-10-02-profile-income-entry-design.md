# Preferences income entry design

Status: proposed for review; application changes are not authorized by the request to plan first.

## Purpose and existing behavior

Connect the expected monthly amount in Preferences to a confirmed income transaction. Preferences currently saves `profiles.monthly_allowance` and `profiles.income_source`; Reports already sums income transactions for its selected date and category filters. The existing manual transaction screen supports Income, an amount, source, category, date, and note.

## Requirements

- Preferences stores the expected monthly amount. Saving or changing this value does not create transactions or rewrite historical income.
- Add a `Record monthly income` action below the Monthly Money Source fields in Preferences.
- Use the label `Expected Monthly Allowance / Income` and helper text `Used for planning. Record money received to include it in Reports.` in profile edit and setup.
- Open the existing transaction form in Income mode with the saved monthly amount. The date defaults to `malaysiaToday()`; amount, source, category, date, and note remain editable.
- If Preferences has unsaved changes, offer `Save & continue` or `Cancel`. Reuse its existing profile and tracked-category persistence. Navigate only after both saves succeed. Explain that this saves Preferences and then opens an income draft; a transaction still needs confirmation.
- Enable the shortcut only when the current amount passes the existing money parser and is greater than zero. Invalid or empty amounts have inline guidance. Saving Preferences normally keeps its existing navigation behavior.
- The route passes only `prefill=profile_income`; read the saved profile for the current authenticated user inside the transaction screen. Do not place financial amounts in route parameters.
- Apply the prefill once per new draft, after profile and categories are ready. Existing transaction edit data takes precedence over the prefill parameter. Background profile changes never replace a user's edited draft.
- Allowance, Part-time job, Scholarship, and PTPTN prefill the source label. Mixed and Other require the user to enter the actual source. A missing source requires normal source entry.
- Select an accessible income category whose name matches the source label, then the generic Income category. If neither exists, require an explicit income-category selection. Never default to an expense category.
- Saving creates one ordinary owner-scoped income transaction. Manual income entries use the same transaction/report behavior.
- Guard repeated taps synchronously and keep one UUID and the attempted payload for each create draft until its save outcome is known. Recovery checks that UUID under the same owner and never blindly repeats an uncertain write.
- For new income entries, check for similar payments from the same user, category, and amount in the selected date's month. Normalize source text when identifying close matches. Show matching entries and offer `Review entries`, `Record another payment`, or `Cancel`.
- Similar-entry detection is advisory. Separate legitimate payments, including two equal installments, are allowed. Do not enforce one income transaction per month. If a bounded candidate query is full, display a broader possible-duplicate warning rather than claiming there are no matches.
- If the similarity check fails, offer `Retry check` or `Cancel` before writing. A confirmed duplicate warning applies only to the exact draft values that were reviewed.
- The existing transaction UUID primary key prevents inserting the same draft twice. This does not guarantee detection of all duplicates opened on separate devices or after an app restart.
- Reports continues to calculate recorded income from saved transactions. Returning to Reports or refreshing reloads its source data. No expected-income fallback or synthetic monthly income is introduced.
- Use the existing schema, owner filters, and Row Level Security. No database migration, backend deployment, dependency change, or automatic recurring income is required for this scope.
- Preserve FinCoach's existing UI, use AppText/AppTextInput, safe-area insets, and scrollable forms. Verify the changed screens on Honor 200 and a small Android screen.
- Implementation is native in the current chat unless the user explicitly requests delegation. Preserve existing workspace changes and stage only intended changes if committing is later requested.

## Acceptance examples

All examples use the same selected report period and relevant income category.

| Action | Expected result |
|---|---|
| Preferences contains RM2,000; no transactions | Report income remains RM0 |
| Open the shortcut and cancel | No transaction; report income remains RM0 |
| Confirm RM2,000 through the shortcut | One income transaction; report income RM2,000 |
| Add RM500 manually | Report income RM2,500 |
| Change Preferences to RM2,500 without recording income | Existing report income remains RM2,500 |
| Record an actual RM1,800 instead of the prefill | Only RM1,800 is added; Preferences is not overwritten |
| Edit a saved RM2,000 entry to RM1,900 | Report income changes by RM100 after reload |
| Delete the saved allowance entry | Reports removes its amount after reload |
| Record two genuine RM1,000 installments | Both allowed after review; report income RM2,000 |
| Save response is lost after insertion | Recovery finds the same transaction ID; no second row |

## Implementation references

- `src/app/profile/edit.tsx`: profile save and monthly money fields.
- `src/app/profile/setup.tsx`: consistent expected-income wording.
- `src/app/transactions/manage.tsx`: transaction draft, validation, and create/edit workflow.
- `src/lib/transaction-domain.ts` and `src/lib/transactions.ts`: form validation and owner-scoped persistence.
- `src/lib/report-domain.ts:229`: report totals from transactions.
- `supabase/schema.sql:665`: transaction UUID primary key and financial fields.
- [Expo SDK 56 reference](https://docs.expo.dev/versions/v56.0.0/) and [Expo Router navigation](https://docs.expo.dev/router/basics/navigation/), checked 2026-10-02. Reuse navigation with route parameters rather than introducing a new screen or dependency.

