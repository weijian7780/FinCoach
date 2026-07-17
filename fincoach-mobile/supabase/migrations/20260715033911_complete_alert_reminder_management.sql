create extension if not exists pg_net with schema extensions;
create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists supabase_vault with schema vault;

create schema if not exists private;

create table if not exists public.notification_preferences (
  user_id uuid primary key references auth.users (id) on delete cascade,
  budget_enabled boolean not null default true,
  savings_enabled boolean not null default true,
  savings_lead_days smallint not null default 7,
  savings_reminder_time time not null default '09:00',
  savings_milestones_enabled boolean not null default true,
  spending_enabled boolean not null default true,
  spending_frequency text not null default 'weekly',
  spending_weekday smallint,
  spending_reminder_time time not null default '20:00',
  bills_enabled boolean not null default true,
  default_bill_lead_days smallint not null default 3,
  default_bill_reminder_time time not null default '09:00',
  timezone text not null default 'Asia/Kuala_Lumpur',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint notification_preferences_savings_lead_days_check
    check (savings_lead_days between 0 and 365),
  constraint notification_preferences_spending_frequency_check
    check (spending_frequency in ('daily', 'weekly')),
  constraint notification_preferences_spending_weekday_check
    check (spending_weekday is null or spending_weekday between 0 and 6),
  constraint notification_preferences_bill_lead_days_check
    check (default_bill_lead_days between 0 and 365),
  constraint notification_preferences_timezone_check
    check (char_length(btrim(timezone)) between 1 and 100)
);

create table if not exists public.reminders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  type text not null default 'bill',
  title text not null,
  amount numeric(12, 2),
  due_at timestamptz not null,
  lead_days smallint not null default 3,
  recurrence text not null default 'none',
  recurrence_anchor_day smallint not null,
  enabled boolean not null default true,
  next_trigger_at timestamptz,
  last_triggered_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint reminders_type_check check (type = 'bill'),
  constraint reminders_title_check check (char_length(btrim(title)) between 1 and 100),
  constraint reminders_amount_check check (amount is null or amount > 0),
  constraint reminders_lead_days_check check (lead_days between 0 and 365),
  constraint reminders_recurrence_check
    check (recurrence in ('none', 'weekly', 'monthly', 'yearly')),
  constraint reminders_recurrence_anchor_day_check
    check (recurrence_anchor_day between 1 and 31)
);

create table if not exists public.alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  type text not null,
  kind text not null default 'alert',
  title text not null,
  message text not null,
  budget_id uuid references public.monthly_budgets (id) on delete set null,
  category_limit_id bigint references public.budgets (id) on delete set null,
  savings_goal_id uuid references public.savings_goals (id) on delete set null,
  reminder_id uuid references public.reminders (id) on delete set null,
  source_data jsonb not null default '{}'::jsonb,
  dedupe_key text not null,
  scheduled_for timestamptz,
  delivered_at timestamptz,
  read_at timestamptz,
  dismissed_at timestamptz,
  delivery_status text not null default 'pending',
  delivery_error text,
  delivery_attempt_count smallint not null default 0,
  delivery_claimed_at timestamptz,
  next_delivery_attempt_at timestamptz,
  delivery_receipts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint alerts_type_check check (
    type in (
      'budget_warning',
      'budget_exceeded',
      'savings_deadline',
      'savings_milestone',
      'spending_reminder',
      'bill_reminder'
    )
  ),
  constraint alerts_kind_check check (kind in ('alert', 'insight')),
  constraint alerts_title_check check (char_length(btrim(title)) between 1 and 100),
  constraint alerts_message_check check (char_length(btrim(message)) between 1 and 500),
  constraint alerts_dedupe_key_check check (char_length(btrim(dedupe_key)) between 1 and 200),
  constraint alerts_delivery_status_check check (
    delivery_status in (
      'pending',
      'sending',
      'sent',
      'delivered',
      'partially_delivered',
      'retryable',
      'failed',
      'no_active_device'
    )
  ),
  constraint alerts_delivery_error_check
    check (delivery_error is null or char_length(delivery_error) <= 1000),
  constraint alerts_delivery_attempt_count_check
    check (delivery_attempt_count between 0 and 100),
  unique (user_id, dedupe_key)
);

create table if not exists public.user_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  expo_push_token text not null unique,
  platform text not null,
  device_name text,
  active boolean not null default true,
  last_seen_at timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_devices_token_check
    check (char_length(btrim(expo_push_token)) between 20 and 255),
  constraint user_devices_platform_check check (platform in ('android', 'ios')),
  constraint user_devices_device_name_check
    check (device_name is null or char_length(device_name) <= 100),
  constraint user_devices_last_error_check
    check (last_error is null or char_length(last_error) <= 1000)
);

create index if not exists notification_preferences_user_updated_idx
  on public.notification_preferences (user_id, updated_at desc);
create index if not exists reminders_user_due_idx
  on public.reminders (user_id, due_at, created_at desc);
create index if not exists reminders_due_idx
  on public.reminders (next_trigger_at)
  where enabled = true and next_trigger_at is not null;
create index if not exists alerts_inbox_idx
  on public.alerts (user_id, created_at desc)
  where dismissed_at is null;
create index if not exists alerts_unread_idx
  on public.alerts (user_id, created_at desc)
  where read_at is null and dismissed_at is null;
create index if not exists alerts_delivery_retry_idx
  on public.alerts (next_delivery_attempt_at, created_at)
  where delivery_status in ('pending', 'retryable', 'sent');
create index if not exists alerts_budget_source_idx
  on public.alerts (budget_id, category_limit_id)
  where budget_id is not null or category_limit_id is not null;
create index if not exists alerts_savings_source_idx
  on public.alerts (savings_goal_id)
  where savings_goal_id is not null;
create index if not exists alerts_reminder_source_idx
  on public.alerts (reminder_id)
  where reminder_id is not null;
create index if not exists user_devices_active_idx
  on public.user_devices (user_id, last_seen_at desc)
  where active = true;

create or replace function private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function private.refresh_reminder_schedule()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.title = btrim(new.title);
  if new.recurrence_anchor_day is null then
    new.recurrence_anchor_day = extract(day from new.due_at)::smallint;
  end if;
  if new.enabled then
    new.next_trigger_at = new.due_at - make_interval(days => new.lead_days);
  else
    new.next_trigger_at = null;
  end if;
  return new;
end;
$$;

drop trigger if exists notification_preferences_set_updated_at on public.notification_preferences;
create trigger notification_preferences_set_updated_at
before update on public.notification_preferences
for each row execute function private.set_updated_at();

drop trigger if exists reminders_refresh_schedule on public.reminders;
create trigger reminders_refresh_schedule
before insert or update of title, due_at, lead_days, recurrence_anchor_day, enabled on public.reminders
for each row execute function private.refresh_reminder_schedule();

drop trigger if exists reminders_set_updated_at on public.reminders;
create trigger reminders_set_updated_at
before update on public.reminders
for each row execute function private.set_updated_at();

drop trigger if exists user_devices_set_updated_at on public.user_devices;
create trigger user_devices_set_updated_at
before update on public.user_devices
for each row execute function private.set_updated_at();

create or replace function public.reassign_user_device(
  p_user_id uuid,
  p_expo_push_token text,
  p_platform text,
  p_device_name text default null
)
returns public.user_devices
language plpgsql
security definer
set search_path = ''
as $$
declare
  registered_device public.user_devices;
begin
  insert into public.user_devices (
    user_id,
    expo_push_token,
    platform,
    device_name,
    active,
    last_seen_at,
    last_error
  )
  values (
    p_user_id,
    btrim(p_expo_push_token),
    p_platform,
    nullif(btrim(p_device_name), ''),
    true,
    now(),
    null
  )
  on conflict (expo_push_token) do update
  set user_id = excluded.user_id,
      platform = excluded.platform,
      device_name = excluded.device_name,
      active = true,
      last_seen_at = now(),
      last_error = null
  returning * into registered_device;

  return registered_device;
end;
$$;

create or replace function public.deactivate_user_device(
  p_user_id uuid,
  p_expo_push_token text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_count integer;
begin
  update public.user_devices
  set active = false,
      updated_at = now()
  where user_id = p_user_id
    and expo_push_token = p_expo_push_token;

  get diagnostics affected_count = row_count;
  return affected_count > 0;
end;
$$;

create or replace function public.claim_alert_delivery(p_alert_id uuid)
returns setof public.alerts
language sql
security definer
set search_path = ''
as $$
  update public.alerts
  set delivery_status = 'sending',
      delivery_claimed_at = now(),
      delivery_attempt_count = delivery_attempt_count + 1,
      next_delivery_attempt_at = null
  where id = p_alert_id
    and (
      delivery_status in ('pending', 'retryable')
      or (
        delivery_status = 'sending'
        and delivery_claimed_at < now() - interval '5 minutes'
      )
    )
    and (next_delivery_attempt_at is null or next_delivery_attempt_at <= now())
  returning *;
$$;

create or replace function public.claim_bill_reminder_occurrence(
  p_reminder_id uuid,
  p_expected_trigger_at timestamptz,
  p_next_due_at timestamptz,
  p_title text,
  p_message text,
  p_dedupe_key text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  claimed_reminder public.reminders;
  claimed_alert_id uuid;
begin
  select reminder.* into claimed_reminder
  from public.reminders as reminder
  where reminder.id = p_reminder_id
    and reminder.enabled = true
    and reminder.next_trigger_at = p_expected_trigger_at
    and reminder.next_trigger_at <= now()
    and exists (
      select 1
      from public.notification_preferences as preference
      where preference.user_id = reminder.user_id
        and preference.bills_enabled = true
    )
  for update;

  if not found then
    return null;
  end if;

  insert into public.alerts (
    user_id,
    type,
    kind,
    title,
    message,
    reminder_id,
    dedupe_key,
    scheduled_for
  )
  values (
    claimed_reminder.user_id,
    'bill_reminder',
    'alert',
    p_title,
    p_message,
    claimed_reminder.id,
    p_dedupe_key,
    p_expected_trigger_at
  )
  on conflict (user_id, dedupe_key) do nothing
  returning id into claimed_alert_id;

  if claimed_alert_id is null then
    select id into claimed_alert_id
    from public.alerts
    where user_id = claimed_reminder.user_id
      and dedupe_key = p_dedupe_key;
  end if;

  if claimed_reminder.recurrence = 'none' then
    update public.reminders
    set enabled = false,
        next_trigger_at = null,
        last_triggered_at = p_expected_trigger_at
    where id = claimed_reminder.id;
  else
    if p_next_due_at is null then
      raise exception 'A recurring reminder requires its next due date.';
    end if;
    update public.reminders
    set due_at = p_next_due_at,
        last_triggered_at = p_expected_trigger_at
    where id = claimed_reminder.id;
  end if;

  return claimed_alert_id;
end;
$$;

revoke all on function public.reassign_user_device(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.deactivate_user_device(uuid, text) from public, anon, authenticated;
revoke all on function public.claim_alert_delivery(uuid) from public, anon, authenticated;
revoke all on function public.claim_bill_reminder_occurrence(uuid, timestamptz, timestamptz, text, text, text) from public, anon, authenticated;
grant execute on function public.reassign_user_device(uuid, text, text, text) to service_role;
grant execute on function public.deactivate_user_device(uuid, text) to service_role;
grant execute on function public.claim_alert_delivery(uuid) to service_role;
grant execute on function public.claim_bill_reminder_occurrence(uuid, timestamptz, timestamptz, text, text, text) to service_role;

create or replace function private.notify_inserted_alert()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  webhook_url text;
  webhook_secret text;
begin
  select decrypted_secret into webhook_url
  from vault.decrypted_secrets
  where name = 'alert_webhook_url'
  limit 1;

  select decrypted_secret into webhook_secret
  from vault.decrypted_secrets
  where name = 'alert_webhook_secret'
  limit 1;

  if webhook_url is null or webhook_secret is null then
    return new;
  end if;

  perform net.http_post(
    url := webhook_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-fincoach-webhook-secret', webhook_secret
    ),
    body := jsonb_build_object('alertId', new.id),
    timeout_milliseconds := 5000
  );

  return new;
exception
  when others then
    raise warning 'Alert delivery webhook could not be queued (SQLSTATE %).', sqlstate;
    return new;
end;
$$;

revoke all on function private.notify_inserted_alert() from public, anon, authenticated;

drop trigger if exists deliver_inserted_alert on public.alerts;
create trigger deliver_inserted_alert
after insert on public.alerts
for each row execute function private.notify_inserted_alert();

alter table public.notification_preferences enable row level security;
alter table public.reminders enable row level security;
alter table public.alerts enable row level security;
alter table public.user_devices enable row level security;

drop policy if exists "Users can read own notification preferences" on public.notification_preferences;
drop policy if exists "Users can add own notification preferences" on public.notification_preferences;
drop policy if exists "Users can update own notification preferences" on public.notification_preferences;
create policy "Users can read own notification preferences"
on public.notification_preferences for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add own notification preferences"
on public.notification_preferences for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update own notification preferences"
on public.notification_preferences for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "Users can read own reminders" on public.reminders;
drop policy if exists "Users can add own reminders" on public.reminders;
drop policy if exists "Users can update own reminders" on public.reminders;
drop policy if exists "Users can delete own reminders" on public.reminders;
create policy "Users can read own reminders"
on public.reminders for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add own reminders"
on public.reminders for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update own reminders"
on public.reminders for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
create policy "Users can delete own reminders"
on public.reminders for delete to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "Users can read own alerts" on public.alerts;
drop policy if exists "Users can add own alerts" on public.alerts;
drop policy if exists "Users can update own alerts" on public.alerts;
create policy "Users can read own alerts"
on public.alerts for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add own alerts"
on public.alerts for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update own alerts"
on public.alerts for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

revoke all on table public.notification_preferences from anon;
revoke all on table public.reminders from anon;
revoke all on table public.alerts from anon;
revoke all on table public.user_devices from anon, authenticated;

grant select, insert, update on table public.notification_preferences to authenticated;
grant select, insert, update, delete on table public.reminders to authenticated;
grant select on table public.alerts to authenticated;
grant insert (
  user_id,
  type,
  kind,
  title,
  message,
  budget_id,
  category_limit_id,
  savings_goal_id,
  reminder_id,
  source_data,
  dedupe_key,
  scheduled_for
) on table public.alerts to authenticated;
revoke update on table public.alerts from authenticated;
grant update (read_at, dismissed_at) on table public.alerts to authenticated;

grant select, insert, update, delete on table public.notification_preferences to service_role;
grant select, insert, update, delete on table public.reminders to service_role;
grant select, insert, update, delete on table public.alerts to service_role;
grant select, insert, update, delete on table public.user_devices to service_role;
