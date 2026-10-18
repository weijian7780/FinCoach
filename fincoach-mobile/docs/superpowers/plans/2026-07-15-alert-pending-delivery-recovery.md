# Alert Pending Delivery Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development while implementing each task.

**Goal:** Automatically recover alert push deliveries that remain `pending` when the immediate database webhook fails or never reaches the Edge Function.

**Architecture:** Database Webhooks remain the fast delivery path. The existing once-per-minute `process-alerts` Cron job becomes the recovery path: it selects `pending` alerts older than a two-minute grace period and due `retryable` alerts, then passes each alert to the existing atomic `deliverAlert` flow. The database `claim_alert_delivery` function remains the concurrency guard so a late webhook and Cron cannot send the same alert twice.

**Tech Stack:** Supabase PostgreSQL, Database Webhooks, Supabase Cron (`pg_cron`), Supabase Edge Functions/Deno, TypeScript, Node test runner.

## Global Constraints

- Work only in the canonical repository: `C:\Users\User\Desktop\School\UMS SEM 6\FYP Develop\fincoach-mobile`.
- Do not create a branch, worktree, commit, or push. The user manages GitHub.
- Do not edit or build from `C:\fcb`; this is a server-only change.
- Do not add a database migration or change the alert schema. Existing columns and `claim_alert_delivery` already support `pending` and `retryable` delivery claims.
- Do not change the immediate Database Webhook flow.
- Recover `pending` alerts only after two minutes to avoid racing a healthy but slightly delayed webhook.
- Keep the processing batch bounded at 100 alerts per Cron run.
- Never log webhook, Cron, Firebase, or service-role secrets.
- Do not rebuild the Android APK; deployment is limited to the `process-alerts` Edge Function.

---

## Why this recovery is needed

Current failure path:

1. FinCoach inserts an alert with `delivery_status = 'pending'`.
2. The Database Webhook should call the alert delivery Edge Function immediately.
3. If that HTTP request fails, the alert stays `pending`.
4. The current Cron recovery code selects only `retryable` alerts, so it never sees that stuck `pending` alert.
5. The in-app alert remains visible, but the phone push may never arrive.

Target recovery path:

1. Keep immediate webhook delivery as the normal path.
2. Every minute, Cron finds `pending` alerts older than two minutes.
3. Cron calls the existing `deliverAlert` function.
4. `claim_alert_delivery` atomically claims the alert before sending.
5. A successful push updates the alert to `sent`/`delivered`; a temporary failure follows the existing retry schedule; a permanent failure follows the existing failed-delivery handling.

---

## Task 1: Define delivery eligibility with tests

**Files:**

- Modify: `supabase/functions/_shared/due-domain.test.ts`
- Modify: `supabase/functions/_shared/due-domain.ts`

- [ ] **Step 1: Add failing eligibility tests**

Replace the retry-only test coverage with tests for a general recovery helper:

```ts
import {
  PENDING_ALERT_RECOVERY_DELAY_MS,
  shouldAttemptAlertDelivery,
} from './due-domain.ts';

const now = '2026-07-15T08:00:00.000Z';

assert.equal(
  shouldAttemptAlertDelivery(
    {
      deliveryStatus: 'pending',
      createdAt: '2026-07-15T07:58:01.000Z',
      nextDeliveryAttemptAt: null,
    },
    now,
  ),
  false,
);

assert.equal(PENDING_ALERT_RECOVERY_DELAY_MS, 120_000);

assert.equal(
  shouldAttemptAlertDelivery(
    {
      deliveryStatus: 'pending',
      createdAt: '2026-07-15T07:58:00.000Z',
      nextDeliveryAttemptAt: null,
    },
    now,
  ),
  true,
);
```

Add cases for:

- `pending` at 119 seconds: `false`.
- `pending` at exactly 120 seconds: `true`.
- `retryable` with a due `nextDeliveryAttemptAt`: `true`.
- `retryable` with a future `nextDeliveryAttemptAt`: `false`.
- `delivered`, `sent`, and `failed`: `false`.
- Invalid or missing timestamps: `false`.

- [ ] **Step 2: Run the focused test and confirm RED**

Run from the canonical repository:

```powershell
npm.cmd test -- supabase/functions/_shared/due-domain.test.ts
```

Expected: failure because `PENDING_ALERT_RECOVERY_DELAY_MS` and `shouldAttemptAlertDelivery` do not exist yet.

- [ ] **Step 3: Implement the pure eligibility rule**

In `due-domain.ts`, export:

```ts
export const PENDING_ALERT_RECOVERY_DELAY_MS = 2 * 60 * 1000;

export function shouldAttemptAlertDelivery(
  alert: {
    deliveryStatus: string;
    createdAt: string;
    nextDeliveryAttemptAt: string | null;
  },
  now: string,
): boolean {
  const nowMs = Date.parse(now);
  if (!Number.isFinite(nowMs)) return false;

  if (alert.deliveryStatus === 'pending') {
    const createdAtMs = Date.parse(alert.createdAt);
    return Number.isFinite(createdAtMs)
      && createdAtMs <= nowMs - PENDING_ALERT_RECOVERY_DELAY_MS;
  }

  if (alert.deliveryStatus === 'retryable') {
    if (!alert.nextDeliveryAttemptAt) return false;
    const nextAttemptMs = Date.parse(alert.nextDeliveryAttemptAt);
    return Number.isFinite(nextAttemptMs) && nextAttemptMs <= nowMs;
  }

  return false;
}
```

Remove `shouldRetryAlert` after all imports are migrated so there is one source of truth.

- [ ] **Step 4: Run the focused test and confirm GREEN**

```powershell
npm.cmd test -- supabase/functions/_shared/due-domain.test.ts
```

Expected: all delivery eligibility cases pass.

---

## Task 2: Extend the Cron processor to recover stale pending alerts

**Files:**

- Modify: `scripts/verify-alert-functions.mjs`
- Modify: `supabase/functions/process-alerts/index.ts`

- [ ] **Step 1: Strengthen the structural verifier first**

Update `verify-alert-functions.mjs` so `process-alerts` must contain evidence of:

- `shouldAttemptAlertDelivery`.
- A query for `delivery_status = 'pending'`.
- A query for `delivery_status = 'retryable'`.
- Pending age filtering through `created_at`.
- Retry scheduling through `next_delivery_attempt_at`.
- Reuse of `deliverAlert`.
- A maximum combined batch size of 100.

- [ ] **Step 2: Run the verifier and confirm RED**

```powershell
node scripts/verify-alert-functions.mjs
```

Expected: failure because the current processor only queries `retryable` alerts.

- [ ] **Step 3: Replace retry-only processing with recoverable-delivery processing**

In `process-alerts/index.ts`:

1. Rename `processDeliveryRetries` to `processRecoverableDeliveries`.
2. Compute the stale-pending cutoff from `PENDING_ALERT_RECOVERY_DELAY_MS`.
3. Query stale `pending` alerts:

```ts
const pendingBefore = new Date(
  now.getTime() - PENDING_ALERT_RECOVERY_DELAY_MS,
).toISOString();

const { data: pendingAlerts, error: pendingError } = await service
  .from('alerts')
  .select('id,created_at,delivery_status,next_delivery_attempt_at')
  .eq('delivery_status', 'pending')
  .lte('created_at', pendingBefore)
  .order('created_at', { ascending: true })
  .limit(100);
```

4. Query due `retryable` alerts:

```ts
const { data: retryableAlerts, error: retryableError } = await service
  .from('alerts')
  .select('id,created_at,delivery_status,next_delivery_attempt_at')
  .eq('delivery_status', 'retryable')
  .lte('next_delivery_attempt_at', now.toISOString())
  .order('next_delivery_attempt_at', { ascending: true })
  .limit(100);
```

5. Throw on either query error so the Cron invocation reports failure instead of silently skipping recovery.
6. Merge both result sets, de-duplicate by alert ID, order oldest first, and slice the combined list to 100.
7. Recheck every row with `shouldAttemptAlertDelivery` before calling `deliverAlert`.
8. Call `deliverAlert(service, alert.id)` sequentially or with the existing bounded behavior; do not create an unbounded `Promise.all`.
9. Update the main Cron handler to call `processRecoverableDeliveries`.

The existing `claim_alert_delivery` RPC must remain inside `deliverAlert`. It is the final duplicate-send protection if a delayed webhook and Cron select the same alert.

- [ ] **Step 4: Run the verifier and focused tests and confirm GREEN**

```powershell
node scripts/verify-alert-functions.mjs
npm.cmd test -- supabase/functions/_shared/due-domain.test.ts
```

Expected: both commands pass.

---

## Task 3: Document, verify, deploy, and monitor

**Files:**

- Modify: `docs/alert-reminder-deployment.md`

- [ ] **Step 1: Document the two delivery paths**

Add a section explaining:

- Database Webhook: immediate push delivery.
- Cron: once-per-minute recovery for `pending` alerts older than two minutes and due `retryable` alerts.
- Normal worst-case recovery start: approximately two to three minutes after alert creation because of the two-minute grace period plus the next Cron tick.
- Duplicate protection: `claim_alert_delivery`.
- No mobile rebuild is required for this server-side update.

Include this operational check:

```sql
select id, type, delivery_status, created_at,
       delivery_attempt_count, next_delivery_attempt_at,
       last_delivery_error
from public.alerts
where delivery_status in ('pending', 'retryable')
order by created_at asc;
```

Include this stuck-pending count:

```sql
select count(*) as stale_pending_alerts
from public.alerts
where delivery_status = 'pending'
  and created_at <= now() - interval '2 minutes';
```

Expected during normal operation: `stale_pending_alerts = 0` after Cron has had time to run.

- [ ] **Step 2: Run local verification**

```powershell
npm.cmd test -- supabase/functions/_shared/due-domain.test.ts
node scripts/verify-alert-functions.mjs
npm.cmd run typecheck
```

If the repository has a lint script, also run:

```powershell
npm.cmd run lint
```

Expected: all commands pass. If `typecheck` or `lint` fails because of an unrelated pre-existing issue, record the exact file and error instead of claiming full success.

- [ ] **Step 3: Deploy only the changed Edge Function**

```powershell
npx.cmd supabase functions deploy process-alerts --project-ref yqsyrzdpvtasldkthhfg
```

Expected: Supabase reports a successful `process-alerts` deployment. No SQL migration and no APK build are required.

- [ ] **Step 4: Verify the deployed recovery path**

After at least three Cron ticks, run the two SQL monitoring queries above.

Acceptance criteria:

- No alert remains `pending` for more than the grace period plus a Cron execution window.
- Due `retryable` alerts are still processed.
- Successfully delivered alerts have `delivery_status` of `sent` or `delivered` and no current delivery error.
- A single alert is not sent twice when the webhook and Cron overlap.
- The existing immediate phone-notification behavior on the Honor 200 remains unchanged.

- [ ] **Step 5: Inspect remote execution evidence**

In Supabase Dashboard:

1. Open **Edge Functions → process-alerts → Logs** and confirm scheduled invocations return HTTP 200.
2. Open **Database → Cron Jobs → History** and confirm the job continues to run every minute.
3. If any alert is still stale, inspect `last_delivery_error` and the Edge Function log using the alert ID; never paste secret values into logs or screenshots.

---

## Definition of Done

- Stale `pending` alerts are eligible for automatic recovery after two minutes.
- Existing due `retryable` alerts continue to work.
- The combined Cron batch is capped at 100.
- Atomic claiming prevents duplicate push delivery.
- Focused tests, structural verification, and type checking pass or any unrelated baseline failure is documented precisely.
- `process-alerts` is deployed successfully.
- Remote Cron and Edge Function logs show successful execution.
- No schema migration, Android APK rebuild, worktree, commit, or GitHub push is performed.
