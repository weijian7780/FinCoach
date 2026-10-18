-- Make one report generation attempt safe across devices: a private leased
-- record per attempt, one immutable PDF path, and the history row written in
-- the same transaction that marks the action executed.
begin;

create table public.report_attempts (
  attempt_id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  message_id uuid not null references public.coaching_messages(id) on delete cascade,
  action_id uuid not null,
  storage_path text not null,
  period text not null,
  report_type text not null,
  start_date date not null,
  end_date date not null,
  category_id bigint,
  category_name text,
  arguments jsonb not null default '{}'::jsonb,
  status text not null default 'active',
  report_id bigint references public.reports(id) on delete set null,
  lease_expires_at timestamptz not null,
  lease_owner uuid,
  lease_renewed_at timestamptz,
  lease_renewal_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint report_attempts_status_check check (status in ('active','completed','cancelled','superseded')),
  constraint report_attempts_type_check check (report_type in ('monthly','monthly_category','multi_month','multi_month_category','custom','custom_category')),
  constraint report_attempts_dates_check check (start_date<=end_date),
  -- The path is derived from the attempt id; mobile can never choose it and a
  -- new attempt always writes a new file instead of overwriting an old one.
  constraint report_attempts_path_check check (storage_path=user_id::text||'/coach/'||attempt_id::text||'.pdf')
);
create unique index report_attempts_active_action_idx on public.report_attempts(action_id) where status='active';
create index report_attempts_owner_path_idx on public.report_attempts(user_id,storage_path);
create index report_attempts_owner_message_idx on public.report_attempts(user_id,message_id);

alter table public.report_attempts enable row level security;
revoke all on table public.report_attempts from public,anon,authenticated;
grant select on table public.report_attempts to authenticated;
grant all on table public.report_attempts to service_role;
create policy "Users can read own report attempts" on public.report_attempts
  for select to authenticated using ((select auth.uid())=user_id);
create policy account_must_be_active on public.report_attempts as restrictive for all to authenticated
  using (private.is_active_account()) with check (private.is_active_account());

-- Only the owner's active, unexpired attempt can upload its own reserved path.
-- Client updates/deletes of reserved coaching artifacts stay blocked; the
-- backup 'restored' namespace and manual report files keep working.
drop policy if exists "Users can upload own financial reports" on storage.objects;
create policy "Users can upload own financial reports" on storage.objects
  for insert to authenticated
  with check (
    bucket_id='financial-reports' and (storage.foldername(name))[1]=(select auth.uid()::text)
    and (coalesce((storage.foldername(name))[2],'')<>'coach' or exists(
      select 1 from public.report_attempts a where a.user_id=(select auth.uid()) and a.storage_path=name
        and a.status='active' and a.lease_expires_at>clock_timestamp()))
  );
drop policy if exists "Users can update own financial reports" on storage.objects;
create policy "Users can update own financial reports" on storage.objects
  for update to authenticated
  using (bucket_id='financial-reports' and (storage.foldername(name))[1]=(select auth.uid()::text)
    and coalesce((storage.foldername(name))[2],'')<>'coach')
  with check (bucket_id='financial-reports' and (storage.foldername(name))[1]=(select auth.uid()::text)
    and coalesce((storage.foldername(name))[2],'')<>'coach');
drop policy if exists "Users can delete own financial reports" on storage.objects;
create policy "Users can delete own financial reports" on storage.objects
  for delete to authenticated
  using (bucket_id='financial-reports' and (storage.foldername(name))[1]=(select auth.uid()::text)
    and coalesce((storage.foldername(name))[2],'')<>'coach');

-- Coach history rows are written by the completing transaction; manual rows
-- stay client-writable exactly as before.
drop policy if exists "Users can create own reports" on public.reports;
create policy "Users can create own reports" on public.reports
  for insert to authenticated
  with check ((select auth.uid())=user_id and coalesce(report_key,'') not like 'coach:%');
drop policy if exists "Users can update own reports" on public.reports;
create policy "Users can update own reports" on public.reports
  for update to authenticated
  using ((select auth.uid())=user_id and coalesce(report_key,'') not like 'coach:%')
  with check ((select auth.uid())=user_id and coalesce(report_key,'') not like 'coach:%');

grant select,insert,update on public.reports to service_role;
grant usage,select on sequence public.reports_id_seq to service_role;

-- Replaces the 5-parameter version: report approvals start or resume one
-- attempt, and report completions insert the verified history row and swap in
-- the server-issued result. The new arguments trail the reminder payload so
-- existing positional callers keep working.
drop function if exists public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb);
create function public.commit_coach_action(p_user_id uuid,p_message_id uuid,p_expected_payload jsonb,p_next_payload jsonb,p_reminder jsonb default null,p_attempt_id uuid default null,p_report jsonb default null)
returns setof public.coaching_messages language plpgsql security invoker set search_path='' as $$
declare message public.coaching_messages; old_status text; new_status text; action_kind text; resolved_action_id uuid; requested_category text;
  attempt public.report_attempts; live public.report_attempts; started_id uuid; next_payload jsonb; inserted public.reports;
  generated_at timestamptz; report_title text; report_file_name text; resolved_category bigint;
begin
  select * into message from public.coaching_messages where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload is distinct from p_expected_payload then raise exception 'Action state changed. Reload and try again.'; end if;
  if jsonb_typeof(p_next_payload) is distinct from 'object' or p_expected_payload->>'type' is distinct from 'action'
    or (p_next_payload-'status'-'result') is distinct from (p_expected_payload-'status'-'result')
  then raise exception 'Invalid action transition.'; end if;
  old_status:=p_expected_payload->>'status'; new_status:=p_next_payload->>'status';
  action_kind:=p_expected_payload->>'action_type'; resolved_action_id:=(p_expected_payload->>'action_id')::uuid;
  if resolved_action_id is null or action_kind not in ('create_reminder','generate_report') or not coalesce(
    (new_status='cancelled' and old_status in ('pending','approved','failed'))
    or (action_kind='create_reminder' and old_status='pending' and new_status='executed')
    or (action_kind='generate_report' and old_status in ('pending','failed') and new_status='approved')
    or (action_kind='generate_report' and old_status='approved' and new_status='approved')
    or (action_kind='generate_report' and old_status='approved' and new_status in ('executed','failed')),false)
  then raise exception 'Invalid action transition.'; end if;
  if p_reminder is not null and not (action_kind='create_reminder' and new_status='executed') then raise exception 'Unexpected reminder effect.'; end if;
  next_payload:=p_next_payload;
  if action_kind='create_reminder' and new_status='executed' then
    if p_reminder is not null then
      if p_reminder->>'id' is distinct from resolved_action_id::text or p_reminder->>'user_id' is distinct from p_user_id::text then raise exception 'Invalid reminder owner.'; end if;
      -- Columns and owner are fixed; arbitrary fields in JSON cannot alter unrelated records.
      insert into public.reminders(id,user_id,type,title,amount,due_at,lead_days,recurrence,recurrence_anchor_day,enabled,next_trigger_at)
      values(resolved_action_id,p_user_id,'bill',p_reminder->>'title',(p_reminder->>'amount')::numeric,(p_reminder->>'due_at')::timestamptz,
        (p_reminder->>'lead_days')::integer,p_reminder->>'recurrence',(p_reminder->>'recurrence_anchor_day')::integer,true,(p_reminder->>'next_trigger_at')::timestamptz)
      on conflict(id) do nothing;
    end if;
    if not exists(select 1 from public.reminders where id=resolved_action_id and user_id=p_user_id)
      or p_next_payload->'result'->>'reminder_id' is distinct from resolved_action_id::text then raise exception 'Reminder effect missing.'; end if;
  end if;
  if action_kind='generate_report' and new_status='approved' then
    -- A fresh confirmation of the same live attempt resumes it; any other
    -- start supersedes the live attempt so only one attempt can publish.
    select * into live from public.report_attempts where action_id=resolved_action_id and status='active' for update;
    if found and live.attempt_id=p_attempt_id then
      update public.report_attempts set lease_expires_at=clock_timestamp()+interval '5 minutes',lease_owner=p_user_id,
        lease_renewed_at=clock_timestamp(),lease_renewal_count=lease_renewal_count+1,updated_at=clock_timestamp()
        where attempt_id=live.attempt_id;
    else
      if found then update public.report_attempts set status='superseded',updated_at=clock_timestamp() where attempt_id=live.attempt_id; end if;
      if jsonb_typeof(p_next_payload->'arguments') is distinct from 'object'
        or p_next_payload->'arguments'->>'start_date' !~ '^\d{4}-\d{2}-\d{2}$' or p_next_payload->'arguments'->>'end_date' !~ '^\d{4}-\d{2}-\d{2}$'
        or (p_next_payload->'arguments'->>'start_date')::date > (p_next_payload->'arguments'->>'end_date')::date
      then raise exception 'Invalid report selection.'; end if;
      -- Never reuse an id whose path may already hold an abandoned file.
      started_id:=case when p_attempt_id is null or exists(select 1 from public.report_attempts where attempt_id=p_attempt_id) then gen_random_uuid() else p_attempt_id end;
      requested_category:=nullif(lower(btrim(p_next_payload->'arguments'->>'category_name')),'');
      select c.id into resolved_category from public.categories c
        where lower(btrim(c.name))=requested_category and (c.user_id is null or c.user_id=p_user_id)
        order by (c.user_id is null),(c.type<>'expense'),c.id limit 1;
      -- A requested category that no longer resolves would silently widen the
      -- report scope, so the attempt is refused instead of mislabelled.
      if requested_category is not null and resolved_category is null then
        raise exception 'The report category is no longer available.' using errcode='P0003';
      end if;
      insert into public.report_attempts(attempt_id,user_id,message_id,action_id,storage_path,period,report_type,start_date,end_date,category_id,category_name,arguments,lease_expires_at,lease_owner)
      values(started_id,p_user_id,p_message_id,resolved_action_id,p_user_id::text||'/coach/'||started_id::text||'.pdf',
        coalesce(nullif(btrim(p_next_payload->'arguments'->>'period'),''),'custom'),
        case when p_next_payload->'arguments'->>'period' in ('current_month','last_month') then 'monthly'
          when p_next_payload->'arguments'->>'period'='last_3_months' then 'multi_month' else 'custom' end
          || case when requested_category is null then '' else '_category' end,
        (p_next_payload->'arguments'->>'start_date')::date,(p_next_payload->'arguments'->>'end_date')::date,
        resolved_category,
        nullif(btrim(p_next_payload->'arguments'->>'category_name'),''),p_next_payload->'arguments',
        clock_timestamp()+interval '5 minutes',p_user_id);
    end if;
  end if;
  if action_kind='generate_report' and new_status in ('executed','failed') then
    if p_attempt_id is null then raise exception 'The report attempt is required to finish this action.'; end if;
    select * into attempt from public.report_attempts
      where attempt_id=p_attempt_id and user_id=p_user_id and message_id=p_message_id and action_id=resolved_action_id for update;
    -- A late completion can never publish for a cancelled, superseded or
    -- foreign attempt, and an expired lease stops a zombie renderer.
    if not found or attempt.status<>'active' then raise exception 'The report attempt is no longer active.' using errcode='P0003'; end if;
    if new_status='executed' then
      if attempt.lease_expires_at<=clock_timestamp() then raise exception 'The report attempt lease expired.' using errcode='P0003'; end if;
      if jsonb_typeof(p_report) is distinct from 'object' or jsonb_typeof(p_report->'title') is distinct from 'string'
        or jsonb_typeof(p_report->'file_name') is distinct from 'string' or jsonb_typeof(p_report->'generated_at') is distinct from 'string'
      then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
      report_title:=btrim(p_report->>'title'); report_file_name:=btrim(p_report->>'file_name');
      if char_length(report_title) not between 1 and 160 or char_length(report_file_name) not between 5 and 255
        or report_file_name not like '%.pdf' or report_file_name ~ '[/\\]'
      then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
      begin
        generated_at:=(p_report->>'generated_at')::timestamptz;
      exception when others then raise exception 'Invalid report metadata.' using errcode='P0003'; end;
      if generated_at is null then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
      -- Selection, path and key come from the attempt, never from the caller.
      insert into public.reports(user_id,period,type,title,file_name,storage_path,report_key,start_date,end_date,category_id,generated_at)
      values(p_user_id,
        case when attempt.report_type in ('monthly','monthly_category') then to_char(attempt.start_date,'YYYY-MM')
          when attempt.report_type in ('multi_month','multi_month_category') then to_char(attempt.start_date,'YYYY-MM')||'..'||to_char(attempt.end_date,'YYYY-MM')
          else attempt.start_date::text||'..'||attempt.end_date::text end,
        attempt.report_type,report_title,report_file_name,attempt.storage_path,'coach:'||attempt.attempt_id::text,
        attempt.start_date,attempt.end_date,attempt.category_id,generated_at)
      returning * into inserted;
      update public.report_attempts set status='completed',report_id=inserted.id,updated_at=clock_timestamp() where attempt_id=attempt.attempt_id;
      next_payload:=jsonb_set(p_next_payload,'{result}',jsonb_build_object('report_id',inserted.id,'storage_path',inserted.storage_path,'title',inserted.title));
    else
      update public.report_attempts set status='cancelled',updated_at=clock_timestamp() where attempt_id=attempt.attempt_id;
    end if;
  end if;
  if action_kind='generate_report' and new_status='cancelled' then
    update public.report_attempts set status='cancelled',updated_at=clock_timestamp() where action_id=resolved_action_id and user_id=p_user_id and status='active';
  end if;
  return query update public.coaching_messages set ui_payload=next_payload where id=p_message_id and user_id=p_user_id returning *;
end $$;
revoke all on function public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb,uuid,jsonb) to service_role;

create function public.renew_report_attempt(p_user_id uuid,p_message_id uuid,p_attempt_id uuid)
returns setof public.report_attempts language plpgsql security invoker set search_path='' as $$
declare attempt public.report_attempts;
begin
  update public.report_attempts set lease_expires_at=clock_timestamp()+interval '5 minutes',lease_owner=p_user_id,
    lease_renewed_at=clock_timestamp(),lease_renewal_count=lease_renewal_count+1,updated_at=clock_timestamp()
  where attempt_id=p_attempt_id and user_id=p_user_id and message_id=p_message_id and status='active' and lease_expires_at>clock_timestamp()
  returning * into attempt;
  if not found then raise exception 'The report attempt lease expired or was replaced.' using errcode='P0002'; end if;
  return next attempt;
end $$;
revoke all on function public.renew_report_attempt(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.renew_report_attempt(uuid,uuid,uuid) to service_role;
commit;
