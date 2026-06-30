# FinCoach Mobile

Expo Router + TypeScript mobile app for the FinCoach User Management module.

## Current Scope

- Onboarding 1-3 based on the Stitch prototype.
- Email/password signup and login with Supabase Auth.
- Google OAuth through Supabase Auth.
- Password reset route.
- Basic student profile and spending-records consent.
- Local 4-digit PIN using Expo SecureStore.
- Supabase `profiles` table SQL with Row Level Security (RLS).

AI Coach, finance tracking, budgets, receipt scanning, reports, and notifications are intentionally out of scope for this first module.

## Environment

Create `.env` from `.env.example`:

```bash
EXPO_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=your-supabase-publishable-key
EXPO_PUBLIC_GOOGLE_AUTH_WEB_CLIENT_ID=your-google-oauth-web-client-id.apps.googleusercontent.com
```

Never place Supabase service-role or secret keys in this Expo app.

## Supabase Setup

1. Create a Supabase project named `FinCoach`.
2. Run `supabase/profiles.sql` in the Supabase SQL editor.
3. Enable email/password auth.
4. Configure Google as an auth provider in Supabase.
5. Add `fincoach://auth/callback` and the Expo development redirect URL to Supabase Auth redirect URLs.

For new Supabase projects created after April 28, 2026, public tables may not be exposed to the Data API automatically. The SQL file grants `authenticated` access to `public.profiles`; RLS still restricts rows to `auth.uid() = id`.

## Commands

```bash
npm run typecheck
npx expo-doctor
npx expo start
```

This workspace is inside Google Drive. If npm install fails with tar/write errors, install dependencies in a normal local folder and keep the source files here.

The current verified local mirror is `C:\tmp\fincoach-mobile-deps`. To resync source files there:

```powershell
.\scripts\sync-local-mirror.ps1
```

Manual acceptance tests are listed in `docs/acceptance-tests.md`.

npx expo start --dev-client -c
