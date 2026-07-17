# Budget and Category UI Design QA

- Source visual truth: `C:\tmp\fincoach-budget-reference.png` and `C:\tmp\fincoach-categories-reference.png`
- Implementation: `src/app/(app)/budget.tsx`, `src/app/budget/manage.tsx`, and `src/app/budget/categories.tsx`
- Implementation screenshot: unavailable because no Android device or emulator is connected through ADB
- Reference viewport: 390 x 951 for Budget Overview; 390 x 884 for Categories
- Target state: authenticated user with a monthly budget and category limits

## Full-view comparison evidence

The Stitch reference screenshots were opened and inspected. The coded implementation could not be captured in the same state, so a valid side-by-side visual comparison is blocked.

## Focused region comparison evidence

Source regions inspected: top app bar, title, overall budget card, category cards, category selection chips, progress bars, and bottom navigation. Implementation evidence is limited to source inspection and Android bundle compilation; this is not sufficient for visual fidelity approval.

## Findings

- [Blocked] No implementation screenshot from the Honor 200 or an Android emulator.
  - Impact: typography, wrapping, spacing, card shadows, safe-area placement, and scroll behavior cannot be visually compared at the same viewport.
  - Required check: open Budget, Manage Budget, and Manage Categories on the Honor 200 and capture screenshots.

## Code-level checks completed

- Hanken Grotesk typography and existing FinCoach colour tokens retained.
- Prototype 20px page margins, 16px cards, compact category chips, coloured avatars, and thin progress bars implemented.
- All CRUD behavior and Supabase data flow retained.
- Unit tests, TypeScript, ESLint, and Android production export passed.

## Comparison history

- Initial implementation was visually denser than the source and used large explanation blocks and full-width category selectors.
- Applied fixes: prototype top bar, reduced explanatory copy, compact cards, chip selectors, lighter inputs, 20px margins, and source-aligned shadows/radii.
- Post-fix visual evidence: blocked pending device screenshot.

final result: blocked

---

# Alert Time Picker Design QA

- Source visual truth: `C:\Users\User\Desktop\School\UMS SEM 6\FYP Develop\.codex-remote-attachments\019f565b-64c2-71e0-acc3-32fde149fe14\ebcefeee-7474-4cdb-9949-ad6dbef8b0f9\1-Photo-1.jpg`
- Implementation: `src/components/notifications/time-picker-field.tsx`, `src/app/alerts/settings.tsx`, and `src/app/alerts/reminders/manage.tsx`
- Target device: Honor 200
- State: reminder-time picker open
- Implementation screenshot: unavailable because physical-device testing is assigned to the user

## Full-view comparison evidence

The reference shows the Honor alarm application's native wheel time selector. FinCoach now opens the Android Material 3 system time dialog through Expo UI instead of accepting manually typed text. MagicOS controls the final native dialog rendering, so a same-device screenshot is required for visual comparison.

## Focused region comparison evidence

The closed FinCoach time field retains the existing clock icon, typography, indigo accent, rounded border, and compact/full-width layouts. The open state cannot be visually inspected without launching it on the Honor 200.

## Checks completed

- Savings, spending, default bill, and individual bill-reminder times all use the same reusable picker.
- Manual `HH:MM` keyboard entry was removed from the alert and reminder module.
- Selected times are normalized to the database-compatible 24-hour `HH:MM` value.
- Focused ESLint, TypeScript, six alert UI tests, and the full 159-test suite pass.

## Blocking item

- Open one reminder-time field on the Honor 200 and capture the picker for a same-device visual comparison.

final result: blocked

---

# Alert and Reminder UI Design QA

- Source visual truth: top-level `screens_extra.jsx` and `lib.jsx` in `G:\My Drive\FYP 1 & 2\FinCoach UI`
- Implementation: `src/app/alerts/index.tsx`, `src/app/alerts/settings.tsx`, `src/app/alerts/reminders.tsx`, `src/app/alerts/reminders/manage.tsx`, and `src/components/notifications/alert-card.tsx`
- Target device: Honor 200
- Implementation screenshot: unavailable in this execution because physical-device testing is assigned to the user

## Source-level comparison

- Alerts top bar uses the prototype's 40px circular controls and centered title.
- All, Insights, and Alerts are 36px pill filters with indigo selected and white outlined inactive states.
- Alert cards use 22px radius, subtle border/shadow, 40px tinted icon circles, unread dot, compact time, and 6px insight stripe.
- Swipe-left dismissal exposes a red delete action.
- Prototype colors are retained for budget/error red, insight purple, savings green, and bill amber.
- Settings and reminder screens reuse the same FinCoach Hanken Grotesk, indigo tokens, 20px margins, rounded cards, and Android-safe scrolling.

## Behavioral checks completed

- Loading, empty, database/offline error, retry, notification-permission-denied, unread, read, dismissed, and real-time refresh states exist.
- Settings expose Budget, Savings, Spending, and Bills separately.
- Bill reminder list and form cover add, edit, delete, enable/disable, validation, and recurrence.
- UI source tests and TypeScript validation pass.

## Blocking item

- Capture the Alerts inbox, Notification Settings, Bill Reminders, and New Bill Reminder screens on the Honor 200 at a consistent viewport.
- Compare the implementation screenshot and prototype side by side, then correct visible typography, wrapping, padding, safe-area, shadow, or scroll differences.

final result: blocked

---

# Savings Goal Option 3 Design QA

- Source visual truth: `C:\Users\User\.codex\generated_images\019f565b-64c2-71e0-acc3-32fde149fe14\exec-0f707fe7-8142-4afa-a12d-2271325a4a51.png`
- Implementation: `src/app/savings/manage.tsx` and `src/components/savings/date-field.tsx`
- Reference viewport: 852 x 1844 portrait
- Target device: Honor 200
- Implementation screenshot: unavailable because `adb devices` reports no connected device or emulator

## Full-view comparison evidence

The selected option-3 reference was opened at original resolution and implemented as the visual source of truth. A same-state implementation screenshot could not be captured, so pixel-level comparison is blocked.

## Focused region comparison evidence

Source regions inspected and implemented: top app bar, white live-preview card, circular wallet icon, percentage ring, three tonal input rows, optional-deadline helper, and fixed safe-area primary action.

## Code-level checks completed

- Hanken Grotesk and the existing FinCoach indigo tokens are retained.
- The preview title and percentage update from form/edit state.
- The selected 20px margins, 16px tonal fields, 20px preview card, and bottom safe-area button are implemented.
- Deadline is optional and writes `NULL`, matching the nullable savings-goal schema.
- No `RNCDatePicker` or `react-native-svg` dependency was reintroduced.
- All unit tests, TypeScript, focused ESLint, and Android production export passed.

## Blocking item

- Connect the Honor 200 with USB debugging and capture the New Savings Goal screen at the same state for the final visual comparison.

final result: blocked
