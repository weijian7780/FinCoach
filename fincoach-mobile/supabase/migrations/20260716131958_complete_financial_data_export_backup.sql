-- Complete Financial Data Export and Backup.
-- Logical ERD: USER 1:N DATA_EXPORT 1:N EXPORT_CONTENT; USER 1:N BACKUP.

alter table public.profiles
  add column if not exists auto_backup_enabled boolean not null default true;

create table if not exists public.data_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  format text not null check (format in ('csv', 'pdf')),
  status text not null check (status in ('pending', 'processing', 'completed', 'failed')),
  file_name text not null check (char_length(btrim(file_name)) between 1 and 255),
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  date_from date not null,
  date_to date not null,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint data_exports_date_range_check check (date_from <= date_to)
);

create table if not exists public.export_contents (
  export_id uuid not null references public.data_exports (id) on delete cascade,
  content_type text not null
    check (content_type in ('transaction', 'budget', 'savings', 'report')),
  primary key (export_id, content_type)
);

create table if not exists public.backups (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  backup_type text not null check (backup_type in ('manual', 'automatic')),
  status text not null check (status in ('pending', 'processing', 'completed', 'failed')),
  file_name text not null check (char_length(btrim(file_name)) between 1 and 255),
  storage_path text check (
    storage_path is null or char_length(storage_path) between 1 and 512
  ),
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  checksum_sha256 text check (
    checksum_sha256 is null or checksum_sha256 ~ '^[a-f0-9]{64}$'
  ),
  schema_version integer not null default 1 check (schema_version > 0),
  last_restore_status text check (
    last_restore_status is null
    or last_restore_status in ('pending', 'processing', 'completed', 'failed')
  ),
  last_restored_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists data_exports_user_created_idx
  on public.data_exports (user_id, created_at desc);
create index if not exists data_exports_user_period_idx
  on public.data_exports (user_id, date_from, date_to);
create index if not exists backups_user_created_idx
  on public.backups (user_id, created_at desc);
create index if not exists backups_user_automatic_idx
  on public.backups (user_id, backup_type, status, completed_at desc);

alter table public.data_exports enable row level security;
alter table public.export_contents enable row level security;
alter table public.backups enable row level security;

revoke all on table public.data_exports, public.export_contents, public.backups from anon;
grant select, insert, update, delete
  on table public.data_exports, public.export_contents, public.backups
  to authenticated;

drop policy if exists "Users can read own data exports" on public.data_exports;
create policy "Users can read own data exports" on public.data_exports
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can create own data exports" on public.data_exports;
create policy "Users can create own data exports" on public.data_exports
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Users can update own data exports" on public.data_exports;
create policy "Users can update own data exports" on public.data_exports
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can delete own data exports" on public.data_exports;
create policy "Users can delete own data exports" on public.data_exports
  for delete to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "Users can read own export contents" on public.export_contents;
create policy "Users can read own export contents" on public.export_contents
  for select to authenticated using (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );
drop policy if exists "Users can create own export contents" on public.export_contents;
create policy "Users can create own export contents" on public.export_contents
  for insert to authenticated with check (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );
drop policy if exists "Users can update own export contents" on public.export_contents;
create policy "Users can update own export contents" on public.export_contents
  for update to authenticated
  using (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );
drop policy if exists "Users can delete own export contents" on public.export_contents;
create policy "Users can delete own export contents" on public.export_contents
  for delete to authenticated using (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );

drop policy if exists "Users can read own backups" on public.backups;
create policy "Users can read own backups" on public.backups
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can create own backups" on public.backups;
create policy "Users can create own backups" on public.backups
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Users can update own backups" on public.backups;
create policy "Users can update own backups" on public.backups
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can delete own backups" on public.backups;
create policy "Users can delete own backups" on public.backups
  for delete to authenticated using ((select auth.uid()) = user_id);

insert into storage.buckets (
  id, name, public, file_size_limit, allowed_mime_types
)
values (
  'financial-backups',
  'financial-backups',
  false,
  10485760,
  array['application/json']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read own financial backups" on storage.objects;
create policy "Users can read own financial backups" on storage.objects
  for select to authenticated using (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can upload own financial backups" on storage.objects;
create policy "Users can upload own financial backups" on storage.objects
  for insert to authenticated with check (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can update own financial backups" on storage.objects;
create policy "Users can update own financial backups" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  )
  with check (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can delete own financial backups" on storage.objects;
create policy "Users can delete own financial backups" on storage.objects
  for delete to authenticated using (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

create or replace function public.restore_financial_backup_v1(
  payload jsonb,
  backup_record_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  owner_id uuid := (select auth.uid());
  profile_data jsonb := payload -> 'data' -> 'profile';
begin
  if owner_id is null then
    raise exception 'Authentication required.';
  end if;
  if coalesce((payload ->> 'schemaVersion')::integer, 0) <> 1 then
    raise exception 'Unsupported backup schema.';
  end if;
  if payload ->> 'userId' <> owner_id::text then
    raise exception 'Backup owner mismatch.';
  end if;
  if not exists (
    select 1 from public.backups b
    where b.id = backup_record_id
      and b.user_id = owner_id
      and b.status = 'completed'
  ) then
    raise exception 'Completed backup not found.';
  end if;

  update public.backups
  set last_restore_status = 'processing'
  where id = backup_record_id and user_id = owner_id;

  delete from public.alerts where user_id = owner_id;
  delete from public.reminders where user_id = owner_id;
  delete from public.notification_preferences where user_id = owner_id;
  delete from public.transactions where user_id = owner_id;
  delete from public.budgets where user_id = owner_id;
  delete from public.monthly_budgets where user_id = owner_id;
  delete from public.savings_contributions
  where goal_id in (select id from public.savings_goals where user_id = owner_id);
  delete from public.savings_goals where user_id = owner_id;
  delete from public.reports where user_id = owner_id;
  delete from public.categories where user_id = owner_id;

  if profile_data is not null and profile_data <> 'null'::jsonb then
    update public.profiles
    set email = coalesce(profile_data ->> 'email', email),
        full_name = profile_data ->> 'full_name',
        avatar_url = profile_data ->> 'avatar_url',
        monthly_allowance = nullif(profile_data ->> 'monthly_allowance', '')::numeric,
        university = coalesce(profile_data ->> 'university', university),
        year_of_study = profile_data ->> 'year_of_study',
        income_source = profile_data ->> 'income_source',
        financial_status = profile_data ->> 'financial_status',
        coaching_style = profile_data ->> 'coaching_style',
        onboarding_completed = coalesce(
          (profile_data ->> 'onboarding_completed')::boolean,
          onboarding_completed
        ),
        spending_records_consent = coalesce(
          (profile_data ->> 'spending_records_consent')::public.spending_records_consent,
          spending_records_consent
        ),
        updated_at = now()
    where id = owner_id;
  end if;

  insert into public.categories (id, name, type, icon, user_id, color)
  overriding system value
  select id, name, type, icon, owner_id, color
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb))
    as x(id bigint, name text, type text, icon text, user_id uuid, color text);

  insert into public.monthly_budgets (
    id, user_id, month, limit_amount, created_at, updated_at
  )
  select id, owner_id, month, limit_amount, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb))
    as x(
      id uuid, user_id uuid, month date, limit_amount numeric,
      created_at timestamptz, updated_at timestamptz
    );

  insert into public.budgets (
    id, user_id, category_id, amount, month, created_at, updated_at
  )
  overriding system value
  select id, owner_id, category_id, amount, month, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb))
    as x(
      id bigint, user_id uuid, category_id bigint, amount numeric, month date,
      created_at timestamptz, updated_at timestamptz
    );

  insert into public.savings_goals (
    id, user_id, name, target_amount, current_amount, deadline, created_at, updated_at
  )
  select id, owner_id, name, target_amount, 0, deadline, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb))
    as x(
      id uuid, user_id uuid, name text, target_amount numeric, current_amount numeric,
      deadline date, created_at timestamptz, updated_at timestamptz
    );

  insert into public.savings_contributions (
    id, goal_id, amount, contributed_on, note, created_at
  )
  overriding system value
  select id, goal_id, amount, contributed_on, note, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb))
    as x(
      id bigint, goal_id uuid, amount numeric, contributed_on date,
      note text, created_at timestamptz
    );

  insert into public.transactions (
    id, user_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, created_at, updated_at
  )
  select
    id, owner_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb))
    as x(
      id uuid, user_id uuid, category_id bigint, amount numeric,
      transaction_date date, description text, source text,
      receipt_image_path text, created_at timestamptz, updated_at timestamptz
    );

  insert into public.reports (id, user_id, period, type, generated_at)
  overriding system value
  select id, owner_id, period, type, generated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb))
    as x(id bigint, user_id uuid, period text, type text, generated_at timestamptz);

  insert into public.notification_preferences (
    user_id, budget_enabled, savings_enabled, savings_lead_days,
    savings_reminder_time, savings_milestones_enabled, spending_enabled,
    spending_frequency, spending_weekday, spending_reminder_time, bills_enabled,
    default_bill_lead_days, default_bill_reminder_time, timezone, created_at, updated_at
  )
  select
    owner_id, budget_enabled, savings_enabled, savings_lead_days,
    savings_reminder_time, savings_milestones_enabled, spending_enabled,
    spending_frequency, spending_weekday, spending_reminder_time, bills_enabled,
    default_bill_lead_days, default_bill_reminder_time, timezone, created_at, updated_at
  from jsonb_to_record(coalesce(payload -> 'data' -> 'notificationPreferences', '{}'::jsonb))
    as x(
      user_id uuid, budget_enabled boolean, savings_enabled boolean,
      savings_lead_days smallint, savings_reminder_time time,
      savings_milestones_enabled boolean, spending_enabled boolean,
      spending_frequency text, spending_weekday smallint, spending_reminder_time time,
      bills_enabled boolean, default_bill_lead_days smallint,
      default_bill_reminder_time time, timezone text,
      created_at timestamptz, updated_at timestamptz
    )
  where payload -> 'data' -> 'notificationPreferences' is not null
    and payload -> 'data' -> 'notificationPreferences' <> 'null'::jsonb;

  insert into public.reminders (
    id, user_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at,
    created_at, updated_at
  )
  select
    id, owner_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at,
    created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb))
    as x(
      id uuid, user_id uuid, type text, title text, amount numeric,
      due_at timestamptz, lead_days smallint, recurrence text,
      recurrence_anchor_day smallint, enabled boolean, next_trigger_at timestamptz,
      last_triggered_at timestamptz, created_at timestamptz, updated_at timestamptz
    );

  insert into public.alerts (
    id, user_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for,
    delivered_at, read_at, dismissed_at, delivery_status, delivery_error,
    delivery_attempt_count, delivery_claimed_at, next_delivery_attempt_at,
    delivery_receipts, created_at
  )
  select
    id, owner_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for,
    delivered_at, read_at, dismissed_at, delivery_status, delivery_error,
    delivery_attempt_count, delivery_claimed_at, next_delivery_attempt_at,
    delivery_receipts, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
    as x(
      id uuid, user_id uuid, type text, kind text, title text, message text,
      budget_id uuid, category_limit_id bigint, savings_goal_id uuid, reminder_id uuid,
      source_data jsonb, dedupe_key text, scheduled_for timestamptz,
      delivered_at timestamptz, read_at timestamptz, dismissed_at timestamptz,
      delivery_status text, delivery_error text, delivery_attempt_count smallint,
      delivery_claimed_at timestamptz, next_delivery_attempt_at timestamptz,
      delivery_receipts jsonb, created_at timestamptz
    );

  perform setval(
    pg_get_serial_sequence('public.categories', 'id'),
    greatest(coalesce((select max(id) from public.categories), 1), 1),
    true
  );
  perform setval(
    pg_get_serial_sequence('public.budgets', 'id'),
    greatest(coalesce((select max(id) from public.budgets), 1), 1),
    true
  );
  perform setval(
    pg_get_serial_sequence('public.savings_contributions', 'id'),
    greatest(coalesce((select max(id) from public.savings_contributions), 1), 1),
    true
  );
  perform setval(
    pg_get_serial_sequence('public.reports', 'id'),
    greatest(coalesce((select max(id) from public.reports), 1), 1),
    true
  );

  update public.backups
  set last_restore_status = 'completed',
      last_restored_at = now()
  where id = backup_record_id and user_id = owner_id;

  return jsonb_build_object(
    'profile', case when profile_data is null or profile_data = 'null'::jsonb then 0 else 1 end,
    'customCategories', jsonb_array_length(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb)),
    'transactions', jsonb_array_length(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb)),
    'monthlyBudgets', jsonb_array_length(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb)),
    'categoryLimits', jsonb_array_length(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb)),
    'savingsGoals', jsonb_array_length(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb)),
    'savingsContributions', jsonb_array_length(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb)),
    'reports', jsonb_array_length(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb)),
    'notificationPreferences',
      case when payload -> 'data' -> 'notificationPreferences' is null
        or payload -> 'data' -> 'notificationPreferences' = 'null'::jsonb then 0 else 1 end,
    'reminders', jsonb_array_length(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb)),
    'alerts', jsonb_array_length(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
  );
end;
$$;

revoke execute on function public.restore_financial_backup_v1(jsonb, uuid) from public;
revoke execute on function public.restore_financial_backup_v1(jsonb, uuid) from anon;
grant execute on function public.restore_financial_backup_v1(jsonb, uuid) to authenticated;
