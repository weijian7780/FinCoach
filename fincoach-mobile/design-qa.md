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

# Notification Settings Option 2 Design QA

- Source visual truth: `C:\Users\User\.codex\generated_images\019f8fb0-7118-7501-a23c-f1b035c26c8e\call_OEL21fywNNJD93dWSIevRfcK.png`
- Implementation: `src/app/alerts/settings.tsx`
- Source pixels: 852 x 1844
- Intended app viewport: 390 x 844 logical pixels
- Implementation screenshot: unavailable because `adb devices` reports no connected Android device and the local Android SDK has no configured AVD
- Target state: authenticated user with the Spending check-in bottom sheet open

## Full-view comparison evidence

The selected Option 2 reference was opened at original resolution. The implementation could not be rendered and captured in the same authenticated Android state, so a valid combined visual comparison is blocked.

## Focused region comparison evidence

The source sheet header, enabled switch, Repeat, Day, Time rows, grabber, backdrop and Done action were inspected. Implementation evidence is limited to source inspection, automated tests and TypeScript validation; this is insufficient for visual fidelity approval.

## Findings

- [Blocked] No same-state Android implementation screenshot.
  - Impact: bottom-sheet height, backdrop opacity, native switch placement, text wrapping, safe-area padding and short-screen scrolling cannot be visually compared.
  - Required check: connect the Honor 200 or configure the Pixel 8 emulator, open Notification settings, tap Spending check-in and capture the open sheet.

## Code-level checks completed

- Compact overview replaces the all-controls-at-once form.
- Budget, Savings and Spending switches save immediately through the existing Supabase preference API.
- Savings and Spending details open in a focused bottom sheet and save through Done.
- Repeat, weekday, lead-time and native Expo time-picker controls remain functional.
- Hidden milestone and bill-default fields are not overwritten by partial preference updates.
- Full Vitest suite: 41 files and 271 tests passed.
- TypeScript validation passed.
- Focused ESLint validation passed.
- Android production export could not start because Expo CLI could not open its existing `.expo/dev/logs/export.log` file (`EPERM`); this is an environment lock, not a reported TypeScript or test failure.

## Comparison history

- Initial source implementation displayed Savings, Spending and Bill controls simultaneously with a global Save settings button.
- Applied fixes: compact grouped rows, auto-save status, focused modal sheet, simple nested selection lists and one Done action.
- Post-fix visual evidence: blocked pending an Android device screenshot.

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

---

# Budget Option 2 Design QA

## Reference and Test State

- Reference: `C:\Users\User\.codex\generated_images\019f781f-6401-7041-8256-00b87a96ab5b\call_zPKoKZGs5W376QXiK1m4Buix.png`
- Implementation screenshot: `C:\tmp\fincoach-budget-option2-final.png`
- Side-by-side comparison: `C:\Users\User\.codex\visualizations\2026\07\19\019f781f-6401-7041-8256-00b87a96ab5b\fincoach-budget-option2-comparison-final-v2.png`
- Viewport: 390 x 844
- State: June 2026, RM 860 monthly limit, RM 740 assigned, RM 120 available, four category limits.

## Comparison History

### Iteration 1

- P1: Amount text could overflow the compact category input on web.
  - Fix: constrained the row and input widths and allowed the text container to shrink.
- P2: Category rows were too tall, which pushed the create-category action below the first viewport.
  - Fix: reduced row height and tightened card spacing without reducing the 44 px action targets.
- P2: The title was visually heavier than the reference.
  - Fix: reduced the heading size and retained the existing FinCoach type and color tokens.

### Final Comparison

- Hierarchy matches the reference: monthly limit, assigned/available summary, category rows, add/create actions, and persistent save action.
- Labels, values, icons, inputs, progress bar, and action states are readable in the full side-by-side comparison; no additional crop was required.
- Intentional P3 differences:
  - The save action uses the existing FinCoach solid primary token instead of introducing a new gradient dependency.
  - Icons use the app's existing Material Icons set.
- No remaining P0, P1, or P2 visual issues.

## Interaction QA

- Changed the monthly limit from RM 860 to RM 900 and restored it to RM 860.
- Added an Entertainment category limit.
- Entered RM 40 for the new limit.
- Removed the Entertainment limit.
- Confirmed the create-category and save actions remain visible and usable.
- Checked the browser console and page errors during the interaction path: none.

## Result

passed

---

# Category Appearance Option 1 Design QA

- Source visual truth: `C:\Users\User\.codex\generated_images\019f8fb0-7118-7501-a23c-f1b035c26c8e\call_7kloJomJCNlhAnbi1bA5HtxH.png`
- Implementation: `src/app/budget/categories.tsx`
- Reference viewport: 878 x 1791 portrait
- Target device: Honor 200
- Target state: Add custom category with Personal image selected and an uploaded image
- Implementation screenshot: unavailable because `adb devices -l` reports no connected Android device or emulator

## Full-view comparison evidence

The selected option-1 reference was inspected and implemented using the existing FinCoach typography, colour tokens, cards, inputs, and buttons. A same-state implementation screenshot could not be captured, so final visual fidelity approval is blocked.

## Focused region comparison evidence

- Added one mutually exclusive Category appearance selector: Material icon or Personal image.
- Material icon mode shows the searchable icon grid and colour picker.
- Personal image mode hides the icon grid and colour picker, then shows one large image preview with Change image and Remove actions.
- Switching modes preserves the selected personal image until the user explicitly removes it or saves Material icon mode.
- Category rows and chips use the shared image-aware category icon component.

## Code-level checks completed

- Full Vitest suite: 37 files and 258 tests passed.
- TypeScript validation passed.
- Focused ESLint validation passed.
- Upload remains restricted to JPG, PNG, or WebP images up to 2 MB.
- No database or backend schema change was added for this UI refinement.

## Blocking item

- Connect the Honor 200 with USB debugging, open Manage Categories, select Personal image, upload an image, and capture the screen for same-viewport visual comparison.

final result: blocked

---

# Alert and Reminder Navigation Separation QA

- Source visual truth: `C:\Users\User\Desktop\School\UMS SEM 6\FYP Develop\.codex-remote-attachments\019f8fb0-7118-7501-a23c-f1b035c26c8e\ca7aa4af-3165-4efe-ab6c-b90a12bd7dcf\1-Photo-1.jpg`
- Source pixels: 577 x 1280
- Target implementation: `src/components/notifications/reminders-list-screen.tsx`
- Target viewport: Android portrait
- Target state: Reminders list opened from Notification settings, without the `Reminders | Alerts` module selector
- Implementation screenshot: unavailable because `adb devices -l` reports no connected Android device or emulator

## Full-view comparison evidence

The source screenshot was inspected and the duplicated module selector was identified as the removal target. A same-state implementation screenshot could not be captured, so full visual comparison is blocked.

## Focused region comparison evidence

The selector markup, its navigation back to `/alerts`, and all five selector-only styles were removed. No focused implementation crop is available without a connected Android target.

## Code-level checks completed

- The Alerts inbox and Reminders list no longer contain `moduleTabs` or tab-role navigation between the two screens.
- Notification settings still provides the single `Manage reminders` entry.
- Reminder loading, grouping, creation, editing, enable switches, recurrence, and deletion were not changed.
- Full Vitest suite: 41 files and 274 tests passed.
- TypeScript validation passed.
- Focused ESLint validation passed with caching disabled; Expo lint caching remains blocked by an existing `.expo` cache permission lock.

## Blocking item

- Connect the Honor 200 or Pixel 8 emulator, open Notification settings, select Manage reminders, and capture the Reminders screen for the final same-viewport comparison.

final result: blocked
