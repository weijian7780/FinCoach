-- Fence conflicting decisions and commit action effects together with message state.
begin;
create index if not exists coaching_messages_history_cursor_idx on public.coaching_messages(user_id,session_id,created_at desc,id desc);
-- SECURITY INVOKER uses the server role's privileges. Explicit grants also
-- support clean schema installations without hosted Supabase default grants.
grant select on public.categories to service_role;
grant select, update on public.reports to service_role;
create function public.commit_coach_action(p_user_id uuid,p_message_id uuid,p_expected_payload jsonb,p_next_payload jsonb,p_reminder jsonb default null)
returns setof public.coaching_messages language plpgsql security invoker set search_path='' as $$
declare message public.coaching_messages; old_status text; new_status text; action_kind text; action_id uuid; report public.reports; requested_category text;
begin
  select * into message from public.coaching_messages where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload is distinct from p_expected_payload then raise exception 'Action state changed. Reload and try again.'; end if;
  if jsonb_typeof(p_next_payload) is distinct from 'object' or p_expected_payload->>'type' is distinct from 'action'
    or (p_next_payload-'status'-'result') is distinct from (p_expected_payload-'status'-'result')
  then raise exception 'Invalid action transition.'; end if;
  old_status:=p_expected_payload->>'status'; new_status:=p_next_payload->>'status';
  action_kind:=p_expected_payload->>'action_type'; action_id:=(p_expected_payload->>'action_id')::uuid;
  if action_id is null or action_kind not in ('create_reminder','generate_report') or not coalesce(
    (new_status='cancelled' and old_status in ('pending','approved','failed'))
    or (action_kind='create_reminder' and old_status='pending' and new_status='executed')
    or (action_kind='generate_report' and old_status in ('pending','failed') and new_status='approved')
    or (action_kind='generate_report' and old_status='approved' and new_status in ('executed','failed')),false)
  then raise exception 'Invalid action transition.'; end if;
  if p_reminder is not null and not (action_kind='create_reminder' and new_status='executed') then raise exception 'Unexpected reminder effect.'; end if;
  if action_kind='create_reminder' and new_status='executed' then
    if p_reminder is not null then
      if p_reminder->>'id' is distinct from action_id::text or p_reminder->>'user_id' is distinct from p_user_id::text then raise exception 'Invalid reminder owner.'; end if;
      -- Columns and owner are fixed; arbitrary fields in JSON cannot alter unrelated records.
      insert into public.reminders(id,user_id,type,title,amount,due_at,lead_days,recurrence,recurrence_anchor_day,enabled,next_trigger_at)
      values(action_id,p_user_id,'bill',p_reminder->>'title',(p_reminder->>'amount')::numeric,(p_reminder->>'due_at')::timestamptz,
        (p_reminder->>'lead_days')::integer,p_reminder->>'recurrence',(p_reminder->>'recurrence_anchor_day')::integer,true,(p_reminder->>'next_trigger_at')::timestamptz)
      on conflict(id) do nothing;
    end if;
    if not exists(select 1 from public.reminders where id=action_id and user_id=p_user_id)
      or p_next_payload->'result'->>'reminder_id' is distinct from action_id::text then raise exception 'Reminder effect missing.'; end if;
  end if;
  if action_kind='generate_report' and new_status='executed' then
    select * into report from public.reports where id=(p_next_payload->'result'->>'report_id')::bigint and user_id=p_user_id for key share;
    requested_category:=nullif(lower(btrim(p_expected_payload->'arguments'->>'category_name')),'');
    if not found or report.start_date::text is distinct from p_expected_payload->'arguments'->>'start_date'
      or report.end_date::text is distinct from p_expected_payload->'arguments'->>'end_date'
      or report.storage_path is null or report.storage_path not like p_user_id::text || '/%'
      or report.storage_path is distinct from p_next_payload->'result'->>'storage_path'
      or (requested_category is null and report.category_id is not null)
      or (requested_category is not null and not exists(select 1 from public.categories where id=report.category_id and lower(btrim(name))=requested_category and (user_id is null or user_id=p_user_id)))
    then raise exception 'Report effect missing or does not match approved action.'; end if;
  end if;
  return query update public.coaching_messages set ui_payload=p_next_payload where id=p_message_id and user_id=p_user_id returning *;
end $$;
revoke all on function public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb) to service_role;
commit;
