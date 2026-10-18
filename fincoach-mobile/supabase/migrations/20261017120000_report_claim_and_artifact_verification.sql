-- Corrective protocol after 20261016120000: one transactional claim returns the
-- authoritative attempt, and completion publishes only a verified PDF object.
-- The original migration stays applied; this one replaces its report paths.
begin;

-- Claim = confirm for report actions. The owner's action message is locked
-- first, then its current live attempt, and the exact claimed attempt is
-- returned with the updated message from the same transaction.
create function public.claim_coach_report_attempt(
  p_user_id uuid, p_message_id uuid, p_action_id uuid, p_attempt_id uuid
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare
  message public.coaching_messages;
  attempt public.report_attempts;
  live public.report_attempts;
  terminal public.report_attempts;
  action_status text;
  requested_category text;
  resolved_category bigint;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload->>'type' is distinct from 'action'
    or message.ui_payload->>'action_type' is distinct from 'generate_report'
    or message.ui_payload->>'action_id' is distinct from p_action_id::text
  then raise exception 'Action not found.' using errcode='P0002'; end if;
  -- Compatibility: a report confirmation without the device-reserved attempt id
  -- must be refused before any state changes.
  if p_attempt_id is null then
    raise exception 'Update FinCoach to generate this report.' using errcode='P0101';
  end if;
  action_status:=message.ui_payload->>'status';
  if action_status='executed' then
    select * into terminal from public.report_attempts
      where action_id=p_action_id and user_id=p_user_id and message_id=p_message_id
        and status='completed'
      order by updated_at desc limit 1;
    return jsonb_build_object('message',to_jsonb(message),
      'attempt',case when terminal.attempt_id is null then null else to_jsonb(terminal) end);
  end if;
  if action_status='cancelled' then
    raise exception 'This report action was cancelled. Ask for a new report.' using errcode='P0001';
  end if;
  if action_status not in ('pending','failed','approved') or action_status is null then
    raise exception 'Invalid action transition.';
  end if;
  -- Lock order everywhere: the owned action message, then its current attempt.
  select * into live from public.report_attempts
    where action_id=p_action_id and user_id=p_user_id and status='active' for update;
  if found and live.attempt_id=p_attempt_id then
    -- The same device resumes its attempt; a lapsed lease is safely reacquired
    -- while the attempt is still the one active attempt.
    update public.report_attempts
      set lease_expires_at=clock_timestamp()+interval '5 minutes',lease_owner=p_user_id,
        lease_renewed_at=clock_timestamp(),lease_renewal_count=lease_renewal_count+1,
        updated_at=clock_timestamp()
      where attempt_id=live.attempt_id returning * into attempt;
  elsif found and live.lease_expires_at>clock_timestamp() then
    -- Another device's lease is still valid: never replace or adopt it.
    raise exception 'Report generation is already in progress.' using errcode='P0102',
      detail=jsonb_build_object('lease_expires_at',live.lease_expires_at)::text;
  else
    if found then
      -- Only an expired attempt can be replaced, and its future completion is
      -- permanently fenced by the superseded status.
      update public.report_attempts set status='superseded',updated_at=clock_timestamp()
        where attempt_id=live.attempt_id;
    end if;
    -- A terminal attempt id has a reserved path that may already hold a file,
    -- so it is never silently reused or substituted.
    if exists(select 1 from public.report_attempts where attempt_id=p_attempt_id) then
      raise exception 'This report attempt can no longer be used. Start a new attempt.'
        using errcode='P0104';
    end if;
    if jsonb_typeof(message.ui_payload->'arguments') is distinct from 'object'
      or message.ui_payload->'arguments'->>'start_date' !~ '^\d{4}-\d{2}-\d{2}$'
      or message.ui_payload->'arguments'->>'end_date' !~ '^\d{4}-\d{2}-\d{2}$'
      or (message.ui_payload->'arguments'->>'start_date')::date
         > (message.ui_payload->'arguments'->>'end_date')::date
    then raise exception 'Invalid report selection.'; end if;
    requested_category:=nullif(lower(btrim(message.ui_payload->'arguments'->>'category_name')),'');
    select c.id into resolved_category from public.categories c
      where lower(btrim(c.name))=requested_category and (c.user_id is null or c.user_id=p_user_id)
      order by (c.user_id is null),(c.type<>'expense'),c.id limit 1;
    -- A requested category that no longer resolves would silently widen the
    -- report scope, so the attempt is refused instead of mislabelled.
    if requested_category is not null and resolved_category is null then
      raise exception 'The report category is no longer available.' using errcode='P0003';
    end if;
    insert into public.report_attempts(attempt_id,user_id,message_id,action_id,storage_path,
      period,report_type,start_date,end_date,category_id,category_name,arguments,
      lease_expires_at,lease_owner)
    values(p_attempt_id,p_user_id,p_message_id,p_action_id,
      p_user_id::text||'/coach/'||p_attempt_id::text||'.pdf',
      coalesce(nullif(btrim(message.ui_payload->'arguments'->>'period'),''),'custom'),
      case when message.ui_payload->'arguments'->>'period' in ('current_month','last_month') then 'monthly'
        when message.ui_payload->'arguments'->>'period'='last_3_months' then 'multi_month' else 'custom' end
        || case when requested_category is null then '' else '_category' end,
      (message.ui_payload->'arguments'->>'start_date')::date,
      (message.ui_payload->'arguments'->>'end_date')::date,
      resolved_category,nullif(btrim(message.ui_payload->'arguments'->>'category_name'),''),
      message.ui_payload->'arguments',clock_timestamp()+interval '5 minutes',p_user_id)
    returning * into attempt;
  end if;
  if message.ui_payload->>'status' is distinct from 'approved' then
    update public.coaching_messages
      set ui_payload=jsonb_set(message.ui_payload,'{status}','"approved"')
      where id=p_message_id and user_id=p_user_id returning * into message;
  end if;
  return jsonb_build_object('message',to_jsonb(message),'attempt',to_jsonb(attempt));
end $$;
revoke all on function public.claim_coach_report_attempt(uuid,uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.claim_coach_report_attempt(uuid,uuid,uuid,uuid) to service_role;

-- Completion publishes only the exact object the backend downloaded and checked.
-- The transaction locks the action message, the attempt and the storage row, so
-- a replaced or rewritten object can never publish, and inserts the history row,
-- completes the attempt and executes the action together.
create function public.complete_coach_report_attempt(
  p_user_id uuid, p_message_id uuid, p_action_id uuid, p_attempt_id uuid,
  p_success boolean, p_report jsonb default null, p_storage jsonb default null
) returns setof public.coaching_messages language plpgsql security invoker set search_path='' as $$
declare
  message public.coaching_messages;
  attempt public.report_attempts;
  stored storage.objects;
  stored_json jsonb;
  stored_updated timestamptz;
  claimed_updated timestamptz;
  inserted public.reports;
  next_payload jsonb;
  generated_at timestamptz;
  report_title text;
  report_file_name text;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload->>'type' is distinct from 'action'
    or message.ui_payload->>'action_type' is distinct from 'generate_report'
    or message.ui_payload->>'action_id' is distinct from p_action_id::text
  then raise exception 'Action not found.' using errcode='P0002'; end if;
  if p_attempt_id is null then
    raise exception 'Update FinCoach to generate this report.' using errcode='P0101';
  end if;
  -- A repeated success after the action already executed returns the terminal
  -- result instead of inserting a second history row.
  if message.ui_payload->>'status'='executed' then
    if p_success then return next message; return; end if;
    raise exception 'Invalid action transition.';
  end if;
  if message.ui_payload->>'status' is distinct from 'approved' then
    raise exception 'The report action has not been approved.';
  end if;
  select * into attempt from public.report_attempts
    where attempt_id=p_attempt_id and user_id=p_user_id and message_id=p_message_id
      and action_id=p_action_id and status='active' for update;
  if not found then
    -- Superseded, cancelled, replaced or foreign attempts can no longer publish.
    raise exception 'The report attempt expired before it could be used.' using errcode='P0103';
  end if;
  if not p_success then
    -- A render failure releases the attempt so the action can be retried.
    update public.report_attempts set status='cancelled',updated_at=clock_timestamp()
      where attempt_id=attempt.attempt_id;
    next_payload:=jsonb_set(message.ui_payload,'{status}','"failed"');
    next_payload:=jsonb_set(next_payload,'{result}',coalesce(p_report,'{}'::jsonb));
    return query update public.coaching_messages set ui_payload=next_payload
      where id=p_message_id and user_id=p_user_id returning *;
    return;
  end if;
  if attempt.lease_expires_at<=clock_timestamp() then
    raise exception 'The report attempt expired before it could be used.' using errcode='P0103';
  end if;
  if jsonb_typeof(p_report) is distinct from 'object'
    or jsonb_typeof(p_report->'title') is distinct from 'string'
    or jsonb_typeof(p_report->'file_name') is distinct from 'string'
    or jsonb_typeof(p_report->'generated_at') is distinct from 'string'
  then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
  report_title:=btrim(p_report->>'title');
  report_file_name:=btrim(p_report->>'file_name');
  if char_length(report_title) not between 1 and 160
    or char_length(report_file_name) not between 5 and 255
    or report_file_name not like '%.pdf' or report_file_name ~ '[/\\]'
  then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
  begin
    generated_at:=(p_report->>'generated_at')::timestamptz;
  exception when others then raise exception 'Invalid report metadata.' using errcode='P0003'; end;
  if generated_at is null then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
  -- Recheck the exact object identity/version the backend downloaded. The
  -- caller can never choose the path: it must equal the attempt's reserved path.
  if p_storage is null or jsonb_typeof(p_storage) is distinct from 'object'
    or p_storage->>'path' is distinct from attempt.storage_path
    or nullif(p_storage->>'object_id','') is null
    or nullif(p_storage->>'version','') is null
    or nullif(p_storage->>'updated_at','') is null
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  select * into stored from storage.objects
    where bucket_id='financial-reports' and name=attempt.storage_path for share;
  if not found then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  stored_json:=to_jsonb(stored);
  if coalesce(stored_json->>'owner','')<>p_user_id::text
    and coalesce(stored_json->>'owner_id','')<>p_user_id::text
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  if stored_json->>'id' is distinct from p_storage->>'object_id'
    or coalesce(stored_json->>'version','') is distinct from p_storage->>'version'
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  -- The storage API serialises the row's updated_at with millisecond
  -- precision, so the same instant is compared at millisecond granularity.
  begin
    stored_updated:=(stored_json->>'updated_at')::timestamptz;
    claimed_updated:=(p_storage->>'updated_at')::timestamptz;
  exception when others then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end;
  if stored_updated is null or claimed_updated is null
    or date_trunc('milliseconds',stored_updated)
       is distinct from date_trunc('milliseconds',claimed_updated)
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  if coalesce(stored_json->'metadata'->>'size','NONE') !~ '^\d+$'
    or (stored_json->'metadata'->>'size')::bigint<=0
    or lower(btrim(split_part(coalesce(stored_json->'metadata'->>'mimetype',''),';',1))) <> 'application/pdf'
    or coalesce(p_storage->>'size','NONE') !~ '^\d+$'
    or (stored_json->'metadata'->>'size')::bigint is distinct from (p_storage->>'size')::bigint
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  -- Selection, path and key come from the attempt, never from the caller.
  insert into public.reports(user_id,period,type,title,file_name,storage_path,report_key,
    start_date,end_date,category_id,generated_at)
  values(p_user_id,
    case when attempt.report_type in ('monthly','monthly_category') then to_char(attempt.start_date,'YYYY-MM')
      when attempt.report_type in ('multi_month','multi_month_category') then
        to_char(attempt.start_date,'YYYY-MM')||'..'||to_char(attempt.end_date,'YYYY-MM')
      else attempt.start_date::text||'..'||attempt.end_date::text end,
    attempt.report_type,report_title,report_file_name,attempt.storage_path,
    'coach:'||attempt.attempt_id::text,attempt.start_date,attempt.end_date,
    attempt.category_id,generated_at)
  returning * into inserted;
  update public.report_attempts
    set status='completed',report_id=inserted.id,updated_at=clock_timestamp()
    where attempt_id=attempt.attempt_id;
  next_payload:=jsonb_set(message.ui_payload,'{status}','"executed"');
  next_payload:=jsonb_set(next_payload,'{result}',
    jsonb_build_object('report_id',inserted.id,'storage_path',inserted.storage_path,
      'title',inserted.title));
  return query update public.coaching_messages set ui_payload=next_payload
    where id=p_message_id and user_id=p_user_id returning *;
end $$;
revoke all on function public.complete_coach_report_attempt(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.complete_coach_report_attempt(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb) to service_role;

-- The generic transition function no longer starts or completes reports; those
-- transitions must go through the claim/completion functions above. Reminders
-- and cancellations (which also cancel a live attempt) keep working.
drop function if exists public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb,uuid,jsonb);
create function public.commit_coach_action(
  p_user_id uuid, p_message_id uuid, p_expected_payload jsonb, p_next_payload jsonb,
  p_reminder jsonb default null
) returns setof public.coaching_messages language plpgsql security invoker set search_path='' as $$
declare
  message public.coaching_messages;
  old_status text;
  new_status text;
  action_kind text;
  resolved_action_id uuid;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload is distinct from p_expected_payload then
    raise exception 'Action state changed. Reload and try again.'; end if;
  if jsonb_typeof(p_next_payload) is distinct from 'object'
    or p_expected_payload->>'type' is distinct from 'action'
    or (p_next_payload-'status'-'result') is distinct from (p_expected_payload-'status'-'result')
  then raise exception 'Invalid action transition.'; end if;
  old_status:=p_expected_payload->>'status';
  new_status:=p_next_payload->>'status';
  action_kind:=p_expected_payload->>'action_type';
  resolved_action_id:=(p_expected_payload->>'action_id')::uuid;
  if resolved_action_id is null or action_kind not in ('create_reminder','generate_report') or not coalesce(
    (new_status='cancelled' and old_status in ('pending','approved','failed'))
    or (action_kind='create_reminder' and old_status='pending' and new_status='executed'),false)
  then raise exception 'Invalid action transition.'; end if;
  if p_reminder is not null and not (action_kind='create_reminder' and new_status='executed') then
    raise exception 'Unexpected reminder effect.'; end if;
  if action_kind='create_reminder' and new_status='executed' then
    if p_reminder is not null then
      if p_reminder->>'id' is distinct from resolved_action_id::text
        or p_reminder->>'user_id' is distinct from p_user_id::text
      then raise exception 'Invalid reminder owner.'; end if;
      -- Columns and owner are fixed; arbitrary fields in JSON cannot alter unrelated records.
      insert into public.reminders(id,user_id,type,title,amount,due_at,lead_days,recurrence,
        recurrence_anchor_day,enabled,next_trigger_at)
      values(resolved_action_id,p_user_id,'bill',p_reminder->>'title',(p_reminder->>'amount')::numeric,
        (p_reminder->>'due_at')::timestamptz,(p_reminder->>'lead_days')::integer,
        p_reminder->>'recurrence',(p_reminder->>'recurrence_anchor_day')::integer,true,
        (p_reminder->>'next_trigger_at')::timestamptz)
      on conflict(id) do nothing;
    end if;
    if not exists(select 1 from public.reminders where id=resolved_action_id and user_id=p_user_id)
      or p_next_payload->'result'->>'reminder_id' is distinct from resolved_action_id::text
    then raise exception 'Reminder effect missing.'; end if;
  end if;
  if action_kind='generate_report' and new_status='cancelled' then
    update public.report_attempts set status='cancelled',updated_at=clock_timestamp()
      where action_id=resolved_action_id and user_id=p_user_id and status='active';
  end if;
  return query update public.coaching_messages set ui_payload=p_next_payload
    where id=p_message_id and user_id=p_user_id returning *;
end $$;
revoke all on function public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb) to service_role;

-- Renewal takes the same lock order as claiming and completion: the message
-- first, then the attempt, so a reclaim can never interleave with a heartbeat.
create or replace function public.renew_report_attempt(
  p_user_id uuid, p_message_id uuid, p_attempt_id uuid
) returns setof public.report_attempts language plpgsql security invoker set search_path='' as $$
declare
  message public.coaching_messages;
  attempt public.report_attempts;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  update public.report_attempts
    set lease_expires_at=clock_timestamp()+interval '5 minutes',lease_owner=p_user_id,
      lease_renewed_at=clock_timestamp(),lease_renewal_count=lease_renewal_count+1,
      updated_at=clock_timestamp()
    where attempt_id=p_attempt_id and user_id=p_user_id and message_id=p_message_id
      and status='active' and lease_expires_at>clock_timestamp()
    returning * into attempt;
  if not found then
    raise exception 'The report attempt lease expired or was replaced.' using errcode='P0002';
  end if;
  return next attempt;
end $$;
revoke all on function public.renew_report_attempt(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.renew_report_attempt(uuid,uuid,uuid) to service_role;

-- Manual history cannot acquire references to reserved coaching objects while
-- an abandoned-object sweep is running. Restore uses its own restored prefix.
drop policy if exists "Users can create own reports" on public.reports;
create policy "Users can create own reports" on public.reports for insert to authenticated
  with check ((select auth.uid())=user_id and coalesce(report_key,'') not like 'coach:%'
    and coalesce((storage.foldername(storage_path))[2],'')<>'coach');
drop policy if exists "Users can update own reports" on public.reports;
create policy "Users can update own reports" on public.reports for update to authenticated
  using ((select auth.uid())=user_id and coalesce(report_key,'') not like 'coach:%')
  with check ((select auth.uid())=user_id and coalesce(report_key,'') not like 'coach:%'
    and coalesce((storage.foldername(storage_path))[2],'')<>'coach');

-- A bounded, repeatable sweep catches an upload that arrived after cancellation
-- cleanup. Terminal attempts can never publish; all existing report references
-- (not merely the first REST page) are checked by the database.
create function public.list_abandoned_coach_report_artifacts(
  p_after_created timestamptz default null, p_after_id uuid default null,
  p_user_id uuid default null,p_message_id uuid default null,p_action_id uuid default null
) returns table(attempt_id uuid,user_id uuid,storage_path text,created_at timestamptz)
language sql security invoker set search_path='' as $$
  select a.attempt_id,a.user_id,a.storage_path,a.created_at from public.report_attempts a
  where a.status in ('cancelled','superseded')
    and (p_user_id is null or a.user_id=p_user_id)
    and (p_message_id is null or a.message_id=p_message_id)
    and (p_action_id is null or a.action_id=p_action_id)
    and (p_after_created is null or (a.created_at,a.attempt_id)>(p_after_created,p_after_id))
    and not exists(select 1 from public.reports r where r.storage_path=a.storage_path)
  order by a.created_at,a.attempt_id limit 100
$$;
revoke all on function public.list_abandoned_coach_report_artifacts(timestamptz,uuid,uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.list_abandoned_coach_report_artifacts(timestamptz,uuid,uuid,uuid,uuid) to service_role;
commit;
