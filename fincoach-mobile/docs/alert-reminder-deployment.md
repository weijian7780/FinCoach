# Alert and Reminder Deployment

This guide deploys the FinCoach Alert and Reminder module without placing service credentials in the app bundle or Git.

## 1. Confirm the Supabase project

The current mobile configuration points to project reference `yqsyrzdpvtasldkthhfg`, but the local Supabase CLI is not linked. Confirm that this is the intended project before any remote write.

```powershell
npx.cmd supabase projects list
npx.cmd supabase link --project-ref yqsyrzdpvtasldkthhfg
Get-Content -LiteralPath supabase\.temp\project-ref
```

The last command must print exactly `yqsyrzdpvtasldkthhfg`. Stop if it does not.

## 2. Verify and apply the database migration

```powershell
node scripts\verify-alert-schema.mjs
npx.cmd supabase db push --dry-run
npx.cmd supabase db push
node scripts\verify-alert-schema.mjs
```

The migration creates `notification_preferences`, `reminders`, `alerts`, `user_devices`, owner Row Level Security (RLS), server-only claim functions, the alert-insert webhook trigger, and the `pg_net`, `pg_cron`, and Vault extensions.

## 3. Create server-only secrets

Generate two different random values. Enter them interactively; do not paste them into `.env`, `eas.json`, source files, screenshots, or commits.

```powershell
$webhookSecret = Read-Host 'New ALERT_WEBHOOK_SECRET'
$cronSecret = Read-Host 'New ALERT_CRON_SECRET'
npx.cmd supabase secrets set "ALERT_WEBHOOK_SECRET=$webhookSecret" "ALERT_CRON_SECRET=$cronSecret"
```

If Expo Push Service access-token security is enabled in the Expo dashboard:

```powershell
$expoAccessToken = Read-Host 'Expo push access token'
npx.cmd supabase secrets set "EXPO_ACCESS_TOKEN=$expoAccessToken"
```

Do not set a blank `EXPO_ACCESS_TOKEN`. The functions work without it when Expo push security is disabled.

## 4. Deploy the Edge Functions

`register-device` keeps JWT verification enabled. `send-alert` and `process-alerts` intentionally use custom server-to-server secrets and have platform JWT verification disabled in `supabase/config.toml`.

```powershell
node scripts\verify-alert-functions.mjs
npx.cmd supabase functions deploy register-device
npx.cmd supabase functions deploy send-alert
npx.cmd supabase functions deploy process-alerts
node scripts\verify-alert-functions.mjs
```

## 5. Configure Vault and the alert webhook

Run this in the Supabase SQL Editor. Replace each angle-bracket value only in the editor. The webhook secret must equal `ALERT_WEBHOOK_SECRET` from step 3.

```sql
select vault.create_secret(
  'https://yqsyrzdpvtasldkthhfg.supabase.co/functions/v1/send-alert',
  'alert_webhook_url'
);

select vault.create_secret('<ALERT_WEBHOOK_SECRET>', 'alert_webhook_secret');
select vault.create_secret(
  'https://yqsyrzdpvtasldkthhfg.supabase.co/functions/v1/process-alerts',
  'alert_process_url'
);
select vault.create_secret('<ALERT_CRON_SECRET>', 'alert_cron_secret');
```

If a named secret already exists, update it instead of creating a duplicate:

```sql
select vault.update_secret(
  (select id from vault.secrets where name = 'alert_webhook_secret' limit 1),
  '<NEW_ALERT_WEBHOOK_SECRET>'
);
```

## 6. Schedule due processing and failed-webhook recovery

Run every minute. Database Webhooks remain the immediate delivery path. This Cron job is also the recovery path for alerts that remain `pending` for at least two minutes and for `retryable` alerts whose next attempt is due. The `claim_alert_delivery` database function atomically claims each alert, so a delayed webhook and Cron recovery cannot deliver the same alert twice.

```sql
select cron.schedule(
  'fincoach-process-alerts',
  '* * * * *',
  $cron$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'alert_process_url' limit 1),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-fincoach-cron-secret',
      (select decrypted_secret from vault.decrypted_secrets where name = 'alert_cron_secret' limit 1)
    ),
    body := '{}'::jsonb
  );
  $cron$
);
```

Because the recovery grace period is two minutes and Cron runs every minute, a failed immediate webhook normally begins recovery within approximately two to three minutes. Keep the one-minute schedule if that recovery time is required.

To inspect alerts waiting for delivery:

```sql
select id, type, delivery_status, created_at,
       delivery_attempt_count, next_delivery_attempt_at,
       delivery_error
from public.alerts
where delivery_status in ('pending', 'retryable')
order by created_at asc;
```

To detect alerts that should already have been recovered:

```sql
select count(*) as stale_pending_alerts
from public.alerts
where delivery_status = 'pending'
  and created_at <= now() - interval '2 minutes';
```

After Cron has completed its next run, `stale_pending_alerts` should be `0`. If it is not, inspect the `process-alerts` Edge Function log and `delivery_error` for the affected alert ID.

This recovery update is server-side only. Deploy `process-alerts`; do not rebuild the Android APK solely for this change.

If slower recovery is acceptable after acceptance testing, change to a five-minute schedule:

```sql
select cron.alter_job(
  (select jobid from cron.job where jobname = 'fincoach-process-alerts' limit 1),
  schedule := '*/5 * * * *'
);
```

## 7. Configure Android FCM v1

1. In Firebase, register Android package `com.fincoach.app`.
2. Download `google-services.json` to the mobile project root.
3. Add `"googleServicesFile": "./google-services.json"` inside `expo.android` in `app.json`.
4. Generate a Firebase service-account key with the Firebase Messaging API Admin role.
5. Upload that private JSON key through EAS credentials. Never commit the private service-account JSON.

```powershell
npx.cmd eas-cli@latest credentials
```

Choose Android, the intended build profile, Google Service Account, and FCM v1 push notifications. The Firebase `project_number` in `google-services.json` must match the FCM v1 credential uploaded to the existing EAS project `99cc58a7-e240-4e3e-9f17-071def6cecab`.

## 8. Rebuild the Android app

`expo-notifications`, its icon/channel config, and `google-services.json` are native configuration. Expo Go is not sufficient and an old APK cannot acquire the correct push token.

Local development build for the connected Honor 200:

```powershell
Set-Location C:\fcb
npx.cmd expo run:android --device AJ4UVB5217000493
```

APK without waiting for EAS:

```powershell
Set-Location C:\fcb\android
.\gradlew.bat assembleDebug
```

The debug APK is `C:\fcb\android\app\build\outputs\apk\debug\app-debug.apk`. Keep `fincoach-mobile` as the canonical source; recreate/synchronize `C:\fcb` from it before each native build.

## 9. Database verification queries

```sql
-- Four tables exist.
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in ('notification_preferences', 'reminders', 'alerts', 'user_devices')
order by table_name;

-- RLS is enabled on all four tables.
select relname, relrowsecurity
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in ('notification_preferences', 'reminders', 'alerts', 'user_devices')
order by relname;

-- Inspect policies and roles.
select tablename, policyname, roles, cmd, qual, with_check
from pg_policies
where schemaname = 'public'
  and tablename in ('notification_preferences', 'reminders', 'alerts', 'user_devices')
order by tablename, policyname;

-- Device registration and Cron state. Tokens are intentionally not selected.
select user_id, platform, device_name, is_active, last_seen_at
from public.user_devices
order by last_seen_at desc;

select jobid, jobname, schedule, active
from cron.job
where jobname = 'fincoach-process-alerts';

-- Dedupe and delivery health.
select user_id, dedupe_key, count(*)
from public.alerts
group by user_id, dedupe_key
having count(*) > 1;

select delivery_status, count(*)
from public.alerts
group by delivery_status
order by delivery_status;

select id, type, delivery_status, delivery_attempt_count, delivery_error,
       created_at, delivered_at
from public.alerts
order by created_at desc
limit 30;
```

The duplicate query must return zero rows. Test cross-user isolation with two normal signed-in app sessions; do not use the SQL Editor/service role because it bypasses RLS. User A must not be able to select or modify User B's preferences, reminders, alerts, or devices.

## 10. Honor 200 acceptance sequence

1. Install the rebuilt development APK and start Metro with `npx.cmd expo start --dev-client --lan`.
2. Sign in, accept notification permission, and confirm one active `user_devices` row.
3. Close FinCoach completely and insert one server-side test alert with a unique `dedupe_key`; verify one notification arrives.
4. Tap it and confirm the correct Budget, Savings, Transaction, or Bill Reminder route opens.
5. Test Budget 80% and 100%, Savings 25/50/75/100% and deadline, daily/weekly spending suppression, and one-time/recurring bills.
6. Disable each type separately and confirm only that type stops.
7. Mark read and dismiss on one device; refresh a second device and confirm synchronized state.
8. Log out and confirm that installation's token becomes inactive.

Do not mark closed-app cloud push as accepted until FCM v1 is configured, the native APK is rebuilt, and this physical-device sequence passes.
