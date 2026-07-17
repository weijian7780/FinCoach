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

# AI Financial Coaching Acceptance Tests

Deploy `supabase/migrations/20260717021519_complete_ai_financial_coaching.sql`, ingest the
approved finance corpus, configure the FastAPI server, and set
`EXPO_PUBLIC_FINCOACH_API_URL` before running this section.

## Physical Device And Connectivity

- On the Honor 200, a LAN URL using the PC IPv4 address reaches `/health`; `localhost` is not used.
- The same flows work against the deployed HTTPS API when the production URL replaces the LAN URL.
- The Coach tab opens the real chat UI, stays readable above the Android keyboard, and scrolls to the latest message.
- The production Android bundle contains no Supabase service-role key, LLM key, provider key, or backend `.env` value.

## Authentication And Isolation

- Signed-out, missing-token, malformed-token, anonymous, and expired-token calls are rejected without spending an LLM request.
- A mobile `401` triggers one Supabase refresh and one retry; another `401` shows the sign-in message without looping.
- User A cannot list, rename, delete, or read User B's conversations, messages, or retrieval evidence.
- Starting, renaming, selecting, and deleting multiple conversations persists correctly after app restart.

## Grounded Coaching

- BGE-M3 retrieval returns only references above the configured similarity threshold and shows available source labels.
- The LLM response references the signed-in user's recorded allowance, expenses, category limits, budgets, and savings goals correctly.
- Missing financial records are stated as unavailable; no bank balance, transaction, budget, or goal is invented.
- A malicious instruction placed inside a knowledge document is treated as untrusted reference data and is not followed.
- Advice ends with an educational-not-financial-advice reminder and remains bounded by the configured output limit.

## Reliability And Safeguards

- Sending the same client message ID twice returns the existing completed reply or a safe `409`; it never creates two assistant replies.
- Airplane mode or an unreachable API shows a retry state without deleting previously loaded messages.
- Provider failure returns safe `502` copy; provider timeout returns safe `504` copy; neither exposes provider/database exception text.
- Missing LLM configuration never echoes the constructed prompt or private financial context.
- Per-minute and daily usage limits return `429`, persist across backend restarts, and do not rely on mobile state.
- Every backend response contains a bounded `X-Request-ID`; logs contain route, status, and latency but no token, prompt, message body, or financial context.
