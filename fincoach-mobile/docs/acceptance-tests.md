# FinCoach User Management Acceptance Tests

Use this checklist after the Supabase `FinCoach` project exists and `.env` is filled.

## Auth

- New email signup creates an auth user.
- If Supabase returns a session after signup, the app continues to profile setup.
- If Supabase returns no session after signup, the app shows the check-email screen.
- Existing email/password user can log in.
- Google OAuth opens the provider flow and returns to FinCoach through `/auth/callback`.
- Forgot password sends a reset email.
- Reset-password link opens `/auth/reset-password` and updates the password.
- Logout clears the Supabase session and returns to login.

## Profile And Consent

- New user can save basic profile details.
- Consent can be set to `unset`, `granted`, `denied`, or `withdrawn`.
- Profile updates persist after app reload.
- User can view their email, profile status, onboarding status, and PIN status.

## PIN

- App rejects non-4-digit PIN values.
- App rejects mismatched PIN confirmation.
- Valid PIN saves only a local salted hash through SecureStore.
- Supabase stores only `pin_enabled = true`.
- Unlock succeeds with the correct PIN.
- Unlock fails with an incorrect PIN.
- Reset local PIN clears SecureStore and sets `pin_enabled = false`.

## RLS

- User A can read and update only their own row in `public.profiles`.
- User A cannot read User B's `public.profiles` row.
- User A cannot update User B's `public.profiles` row.
