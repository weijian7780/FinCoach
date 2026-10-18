import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const migrationsDir = join(projectRoot, 'supabase', 'migrations');
const migrationNames = readdirSync(migrationsDir).filter((name) =>
  name.endsWith('_complete_alert_reminder_management.sql'),
);

assert.equal(
  migrationNames.length,
  1,
  'Expected exactly one CLI-generated complete_alert_reminder_management migration.',
);

const sources = [
  ['canonical schema', join(projectRoot, 'supabase', 'schema.sql')],
  ['Alert migration', join(migrationsDir, migrationNames[0])],
];

const requiredFragments = [
  'create table if not exists public.notification_preferences',
  'user_id uuid primary key references auth.users (id) on delete cascade',
  "spending_frequency text not null default 'weekly'",
  "timezone text not null default 'asia/kuala_lumpur'",
  'create table if not exists public.reminders',
  "type text not null default 'bill'",
  'due_at timestamptz not null',
  'recurrence_anchor_day smallint not null',
  'next_trigger_at timestamptz',
  "recurrence in ('none', 'weekly', 'monthly', 'yearly')",
  'create table if not exists public.alerts',
  'budget_id uuid references public.monthly_budgets (id) on delete set null',
  'category_limit_id bigint references public.budgets (id) on delete set null',
  'savings_goal_id uuid references public.savings_goals (id) on delete set null',
  'reminder_id uuid references public.reminders (id) on delete set null',
  'delivery_receipts jsonb not null default',
  'unique (user_id, dedupe_key)',
  'create table if not exists public.user_devices',
  'expo_push_token text not null unique',
  'notification_preferences_user_updated_idx',
  'reminders_due_idx',
  'alerts_inbox_idx',
  'alerts_delivery_retry_idx',
  'user_devices_active_idx',
  'alter table public.notification_preferences enable row level security',
  'alter table public.reminders enable row level security',
  'alter table public.alerts enable row level security',
  'alter table public.user_devices enable row level security',
  'create policy "users can read own notification preferences"',
  'create policy "users can add own notification preferences"',
  'create policy "users can update own notification preferences"',
  'create policy "users can read own reminders"',
  'create policy "users can add own reminders"',
  'create policy "users can update own reminders"',
  'create policy "users can delete own reminders"',
  'create policy "users can read own alerts"',
  'create policy "users can add own alerts"',
  'using ((select auth.uid()) = user_id)',
  'with check ((select auth.uid()) = user_id)',
  'revoke update on table public.alerts from authenticated',
  'grant update (read_at, dismissed_at) on table public.alerts to authenticated',
  'revoke all on table public.user_devices from anon, authenticated',
  'public.reassign_user_device',
  'public.claim_alert_delivery',
  'public.claim_bill_reminder_occurrence',
  'revoke all on function public.reassign_user_device',
  'revoke all on function public.claim_alert_delivery',
  'revoke all on function public.claim_bill_reminder_occurrence',
  'grant execute on function public.reassign_user_device',
  'grant execute on function public.claim_alert_delivery',
  'grant execute on function public.claim_bill_reminder_occurrence',
  'create trigger notification_preferences_set_updated_at',
  'create trigger reminders_set_updated_at',
  'create trigger user_devices_set_updated_at',
  'create trigger deliver_inserted_alert',
  'vault.decrypted_secrets',
  "name = 'alert_webhook_url'",
  "name = 'alert_webhook_secret'",
  'net.http_post',
  "'x-fincoach-webhook-secret'",
];

let failed = false;
for (const [label, path] of sources) {
  const sql = readFileSync(path, 'utf8').toLowerCase().replace(/\s+/g, ' ');
  const missing = requiredFragments.filter(
    (fragment) => !sql.includes(fragment.toLowerCase().replace(/\s+/g, ' ')),
  );

  if (missing.length > 0) {
    failed = true;
    console.error(`${label} is missing:`);
    for (const fragment of missing) console.error(`  - ${fragment}`);
  }

  const forbiddenFragments = [
    'budget_id bigint references public.monthly_budgets',
    'category_limit_id uuid references public.budgets',
    'savings_goal_id bigint references public.savings_goals',
    'grant all on table public.user_devices to authenticated',
    'grant update on table public.alerts to authenticated',
  ];
  for (const fragment of forbiddenFragments) {
    if (sql.includes(fragment)) {
      failed = true;
      console.error(`${label} contains forbidden fragment: ${fragment}`);
    }
  }
}

if (failed) process.exit(1);
console.log('Alert/reminder schema verification passed for canonical schema and migration.');
