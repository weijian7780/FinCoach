# FinCoach Device Demo Evidence

Use this checklist on the final Android APK. Mark an item complete only after saving the required evidence. Do not record secrets, access tokens, private financial data, or full receipt images in this file.

## Test record

| Field | Record |
| --- | --- |
| Test date and time | |
| Tester | |
| Android device and Android version | |
| Installed FinCoach version and versionCode | |
| Build type | Development / preview / release |
| Supabase project verified | Yes / No |
| FastAPI endpoint verified | Yes / No |
| Network used | Wi-Fi / mobile data |

## Evidence rules

- Use a short screen recording for the main journey and screenshots for each completed module.
- Replace personal values with test values where possible.
- Capture one error state for a missing network or invalid form input.
- Capture only app screens and request IDs. Never capture `.env` files, API keys, service-role credentials, or Firebase admin credentials.

## Core user journey

| Step | Pass condition | Evidence file or video timestamp | Result |
| --- | --- | --- | --- |
| Sign in | A verified user reaches the dashboard. | | Pass / Fail |
| Profile and consent | Profile changes persist after app restart; spending consent state is visible. | | Pass / Fail |
| Manual transaction | A valid expense is saved with its selected category and date. | | Pass / Fail |
| Receipt capture | An image is scanned, the extracted fields can be edited, and the reviewed transaction saves. | | Pass / Fail |
| Budget effect | The saved expense updates the correct monthly and category usage. | | Pass / Fail |
| Savings | A contribution changes goal progress and remaining amount. | | Pass / Fail |
| Reminder | A reminder persists after refresh; attach a closed-app notification capture only when FCM is configured. | | Pass / Fail |
| Report | A selected period produces correct transaction, budget, and savings data; attach the generated PDF. | | Pass / Fail |
| Export and restore | Export opens or shares correctly; backup validation succeeds before restore. Use disposable test data for restore. | | Pass / Fail |
| AI Coach | A read-only question returns a response and conversation history persists after reopening. | | Pass / Fail |

## Security and reliability evidence

| Check | Pass condition | Evidence | Result |
| --- | --- | --- | --- |
| RLS isolation | A second normal user cannot view or modify the first user's records. | | Pass / Fail |
| Backend authentication | Missing or expired access tokens are rejected without returning financial context. | | Pass / Fail |
| Coach advice-only mode | A request to create a reminder or report states that no record was changed. | | Pass / Fail |
| Receipt failure | An unsupported or unreadable image produces a safe error and no transaction is saved. | | Pass / Fail |
| Offline handling | A request with no network gives a readable retry path and does not duplicate data. | | Pass / Fail |

## Pre-demo commands

Run these from the canonical mobile source before recording the final demo:

```powershell
npm.cmd run typecheck
npm.cmd test
```

Run the matching Supabase schema verifier after deployment. Use [acceptance-tests.md](acceptance-tests.md) for the detailed module checks.

## Final decision

| Gate | Status | Notes |
| --- | --- | --- |
| Automated checks pass | | |
| Core user journey passes | | |
| Security and reliability checks pass | | |
| Ready for examiner demo | Yes / No | |
