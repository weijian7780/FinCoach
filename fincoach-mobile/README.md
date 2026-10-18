# FinCoach Mobile

Expo Router and TypeScript Android client for the FinCoach personal-finance final-year project. The app uses Supabase for authentication and financial data. It calls the separate FastAPI backend only for receipt extraction and AI Financial Coaching.

## Current Scope

- User Management: email/password and Google sign-in, password reset, onboarding, and session handling.
- Financial Profile Management: profile setup, editing, avatar, and spending-record consent.
- Transaction and Receipt Capture: manual transaction management, receipt camera capture, editable OCR review, and categorisation.
- Budget and Category Limit Management: monthly budgets, category limits, and user-defined expense categories.
- Savings Goal Management: goals, contributions, deadline tracking, and saving suggestions.
- Alert and Reminder Management: spending, budget, savings, and bill reminders with notification preferences.
- Financial Report and Analytics: selected-period spending analysis, budget and savings context, report history, and PDF export.
- Financial Data Export and Backup: CSV/PDF export, private cloud backup, validation, and restore.
- AI Financial Coaching: authenticated saved conversations, retrieved Malaysian-finance guidance, and read-only financial tools. Write actions are disabled unless explicitly enabled on the backend after acceptance testing.

The repository contains local implementation work. A feature is not production-ready until its Supabase migration, required backend or Edge Function, and device acceptance checks have passed.

## Environment

Create `.env` from `.env.example`:

```bash
EXPO_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-supabase-publishable-key
EXPO_PUBLIC_GOOGLE_AUTH_WEB_CLIENT_ID=your-google-oauth-web-client-id.apps.googleusercontent.com
EXPO_PUBLIC_FINCOACH_API_URL=https://your-fincoach-api.example
```

For a physical Android phone on the same Wi-Fi network, use the PC's LAN IP for `EXPO_PUBLIC_FINCOACH_API_URL`; never use `localhost`.

Do not place service-role keys, LLM keys, Firebase admin credentials, webhook secrets, or Edge Function secrets in this app or in Git. Configure server-only alert secrets with Supabase Secrets.

## Database and backend setup

1. Apply `supabase/schema.sql`, then apply every migration in `supabase/migrations` in chronological order.
2. Configure Supabase Auth and the `fincoach://auth/callback` redirect URL for email confirmation, password reset, and Google sign-in.
3. Deploy the FastAPI backend before using receipt extraction or AI Coaching. It owns the Supabase service-role key, OCR, embeddings, retrieval, and LLM provider credentials.
4. Follow [Alert deployment](docs/alert-reminder-deployment.md) before claiming closed-app push notifications work.
5. Keep `fincoach-mobile` as the canonical source. `C:\fcb` is only a temporary short-path Android build copy.

## Local commands

PowerShell may block `npm.ps1`; use the `.cmd` form below when that happens.

```powershell
npm.cmd run typecheck
npm.cmd test
npx.cmd expo start --dev-client -c
```

For a release build, synchronize the canonical source to `C:\fcb`, then build from that short path. A standalone APK does not need Metro, but it still needs network access to Supabase and the FastAPI backend.

## Verification and demo

- [Acceptance tests](docs/acceptance-tests.md) cover module-specific manual checks and Row Level Security (RLS) isolation.
- [Device demo evidence](docs/device-demo-evidence.md) records the APK, device, screenshots, and pass/fail result for an examiner-ready demonstration.
- Run `npm.cmd run typecheck` and `npm.cmd test` before a demo.
- Run the matching `scripts/verify-*-schema.mjs` script after each Supabase migration deployment.
- Use two normal user accounts for RLS checks; SQL Editor and service-role clients bypass RLS and cannot prove user isolation.

For an examiner demo, show one end-to-end journey: sign in, save a transaction or receipt, view the budget effect, create a reminder, generate a report, export or restore data, then ask the Coach a read-only financial question.
