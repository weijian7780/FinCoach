-- Restore report PDF metadata and tracked-category selections atomically.
-- The existing public active-account wrapper and its grants remain unchanged.
-- Legacy v1 documents without userCategories preserve still-valid selections.
create or replace function private.restore_financial_backup_v1(
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
  selected_categories jsonb;
begin
  if owner_id is null then raise exception 'Authentication required.'; end if;
  if coalesce((payload ->> 'schemaVersion')::integer, 0) <> 1 then
    raise exception 'Unsupported backup schema.';
  end if;
  if payload ->> 'userId' <> owner_id::text then raise exception 'Backup owner mismatch.'; end if;
  if not exists (
    select 1 from public.backups b
    where b.id = backup_record_id and b.user_id = owner_id and b.status = 'completed'
  ) then raise exception 'Completed backup not found.'; end if;

  -- New backups capture tracked categories. Older v1 backups did not, so keep
  -- the current selections whose categories still exist in the restored data.
  if (payload -> 'data') ? 'userCategories' then
    selected_categories := payload -> 'data' -> 'userCategories';
    if jsonb_typeof(selected_categories) is distinct from 'array' then
      raise exception 'Invalid tracked categories in backup.';
    end if;
  else
    select coalesce(jsonb_agg(to_jsonb(uc)), '[]'::jsonb)
      into selected_categories
    from public.user_categories uc where uc.user_id = owner_id;
  end if;
  if exists (
    select 1 from jsonb_to_recordset(selected_categories)
      as x(user_id uuid, category_id bigint)
    where x.user_id is distinct from owner_id or x.category_id is null
  ) then raise exception 'Invalid tracked category owner in backup.'; end if;

  update public.backups set last_restore_status = 'processing'
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
  delete from public.user_categories where user_id = owner_id;
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
        onboarding_completed = coalesce((profile_data ->> 'onboarding_completed')::boolean, onboarding_completed),
        spending_records_consent = coalesce(
          (jsonb_populate_record(null::public.profiles,
            jsonb_build_object('spending_records_consent',
              profile_data -> 'spending_records_consent'))).spending_records_consent,
          spending_records_consent
        ),
        updated_at = now()
    where id = owner_id;
  end if;

  insert into public.categories (id, name, type, icon, icon_image_path, user_id, color)
  overriding system value
  select id, name, type, icon, icon_image_path, owner_id, color
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb))
    as x(id bigint, name text, type text, icon text, icon_image_path text, user_id uuid, color text);

  -- Validate new snapshots against visible categories. The definer function
  -- must not allow a supplied category ID to link to another account's data.
  if (payload -> 'data') ? 'userCategories' and exists (
    select 1 from jsonb_to_recordset(selected_categories) as x(category_id bigint)
    left join public.categories c on c.id = x.category_id
    where c.id is null or (c.user_id is not null and c.user_id <> owner_id)
  ) then raise exception 'Tracked category is not available to this account.'; end if;

  insert into public.user_categories (user_id, category_id, created_at)
  select owner_id, x.category_id, coalesce(x.created_at, now())
  from jsonb_to_recordset(selected_categories) as x(category_id bigint, created_at timestamptz)
  join public.categories c on c.id = x.category_id
  where c.user_id is null or c.user_id = owner_id;

  insert into public.monthly_budgets (id, user_id, month, limit_amount, created_at, updated_at)
  select id, owner_id, month, limit_amount, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb))
    as x(id uuid, user_id uuid, month date, limit_amount numeric, created_at timestamptz, updated_at timestamptz);

  insert into public.budgets (id, user_id, category_id, amount, month, created_at, updated_at)
  overriding system value
  select id, owner_id, category_id, amount, month, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb))
    as x(id bigint, user_id uuid, category_id bigint, amount numeric, month date, created_at timestamptz, updated_at timestamptz);

  insert into public.savings_goals (id, user_id, name, target_amount, current_amount, deadline, created_at, updated_at)
  select id, owner_id, name, target_amount, 0, deadline, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb))
    as x(id uuid, user_id uuid, name text, target_amount numeric, current_amount numeric, deadline date, created_at timestamptz, updated_at timestamptz);

  insert into public.savings_contributions (id, goal_id, amount, contributed_on, note, created_at)
  overriding system value
  select id, goal_id, amount, contributed_on, note, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb))
    as x(id bigint, goal_id uuid, amount numeric, contributed_on date, note text, created_at timestamptz);

  insert into public.transactions (
    id, user_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, created_at, updated_at
  )
  select id, owner_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb))
    as x(id uuid, user_id uuid, category_id bigint, amount numeric, transaction_date date,
      description text, source text, receipt_image_path text, created_at timestamptz, updated_at timestamptz);

  -- Restore PDF metadata as well as the history row so existing stored files
  -- remain reachable from the report screen after a restore.
  insert into public.reports (
    id, user_id, period, type, generated_at, title, file_name, storage_path,
    report_key, start_date, end_date, category_id
  )
  overriding system value
  select id, owner_id, period, type, generated_at, title, file_name, storage_path,
    report_key, start_date, end_date, category_id
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb))
    as x(id bigint, user_id uuid, period text, type text, generated_at timestamptz,
      title text, file_name text, storage_path text, report_key text,
      start_date date, end_date date, category_id bigint);

  insert into public.notification_preferences (
    user_id, budget_enabled, savings_enabled, savings_lead_days, savings_reminder_time,
    savings_milestones_enabled, spending_enabled, spending_frequency, spending_weekday,
    spending_reminder_time, bills_enabled, default_bill_lead_days,
    default_bill_reminder_time, timezone, created_at, updated_at
  )
  select owner_id, budget_enabled, savings_enabled, savings_lead_days, savings_reminder_time,
    savings_milestones_enabled, spending_enabled, spending_frequency, spending_weekday,
    spending_reminder_time, bills_enabled, default_bill_lead_days,
    default_bill_reminder_time, timezone, created_at, updated_at
  from jsonb_to_record(coalesce(payload -> 'data' -> 'notificationPreferences', '{}'::jsonb))
    as x(user_id uuid, budget_enabled boolean, savings_enabled boolean, savings_lead_days smallint,
      savings_reminder_time time, savings_milestones_enabled boolean, spending_enabled boolean,
      spending_frequency text, spending_weekday smallint, spending_reminder_time time,
      bills_enabled boolean, default_bill_lead_days smallint, default_bill_reminder_time time,
      timezone text, created_at timestamptz, updated_at timestamptz)
  where payload -> 'data' -> 'notificationPreferences' is not null
    and payload -> 'data' -> 'notificationPreferences' <> 'null'::jsonb;

  insert into public.reminders (
    id, user_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at, created_at, updated_at
  )
  select id, owner_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb))
    as x(id uuid, user_id uuid, type text, title text, amount numeric, due_at timestamptz,
      lead_days smallint, recurrence text, recurrence_anchor_day smallint, enabled boolean,
      next_trigger_at timestamptz, last_triggered_at timestamptz, created_at timestamptz, updated_at timestamptz);

  insert into public.alerts (
    id, user_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for, delivered_at,
    read_at, dismissed_at, delivery_status, delivery_error, delivery_attempt_count,
    delivery_claimed_at, next_delivery_attempt_at, delivery_receipts, created_at
  )
  select id, owner_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for, delivered_at,
    read_at, dismissed_at, delivery_status, delivery_error, delivery_attempt_count,
    delivery_claimed_at, next_delivery_attempt_at, delivery_receipts, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
    as x(id uuid, user_id uuid, type text, kind text, title text, message text,
      budget_id uuid, category_limit_id bigint, savings_goal_id uuid, reminder_id uuid,
      source_data jsonb, dedupe_key text, scheduled_for timestamptz, delivered_at timestamptz,
      read_at timestamptz, dismissed_at timestamptz, delivery_status text, delivery_error text,
      delivery_attempt_count smallint, delivery_claimed_at timestamptz,
      next_delivery_attempt_at timestamptz, delivery_receipts jsonb, created_at timestamptz);

  perform setval(pg_get_serial_sequence('public.categories', 'id'),
    greatest(coalesce((select max(id) from public.categories), 1), 1), true);
  perform setval(pg_get_serial_sequence('public.budgets', 'id'),
    greatest(coalesce((select max(id) from public.budgets), 1), 1), true);
  perform setval(pg_get_serial_sequence('public.savings_contributions', 'id'),
    greatest(coalesce((select max(id) from public.savings_contributions), 1), 1), true);
  perform setval(pg_get_serial_sequence('public.reports', 'id'),
    greatest(coalesce((select max(id) from public.reports), 1), 1), true);

  update public.backups
  set last_restore_status = 'completed', last_restored_at = now()
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
    'notificationPreferences', case when payload -> 'data' -> 'notificationPreferences' is null
      or payload -> 'data' -> 'notificationPreferences' = 'null'::jsonb then 0 else 1 end,
    'reminders', jsonb_array_length(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb)),
    'alerts', jsonb_array_length(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
  );
end;
$$;

revoke all on function private.restore_financial_backup_v1(jsonb, uuid) from public, anon, authenticated;
