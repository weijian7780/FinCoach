begin;
-- Private leases are inaccessible to mobile clients; a token fences abandoned workers.
create table private.coaching_processing_leases (
  message_id uuid primary key references public.coaching_messages(id) on delete cascade,
  token uuid not null,
  expires_at timestamptz not null
);
revoke all on private.coaching_processing_leases from public,anon,authenticated;

create function public.claim_coaching_message(p_user_id uuid,p_message_id uuid,p_token uuid,p_session_id uuid default null,p_content text default null)
returns setof public.coaching_messages language plpgsql security definer set search_path='' as $$
declare message public.coaching_messages; lease private.coaching_processing_leases;
begin
  perform pg_advisory_xact_lock(hashtextextended('coach:' || p_message_id::text,0));
  select * into message from public.coaching_messages where id=p_message_id for update;
  if not found then
    if p_session_id is null or p_content is null then return; end if;
    if not exists(select 1 from public.coaching_sessions where id=p_session_id and user_id=p_user_id) then raise exception 'Conversation not found'; end if;
    insert into public.coaching_messages(id,session_id,user_id,role,content,status)
      values(p_message_id,p_session_id,p_user_id,'user',p_content,'completed') returning * into message;
  else
    if message.user_id<>p_user_id or message.role<>'user' or (p_session_id is not null and message.session_id<>p_session_id)
      or (p_content is not null and message.content<>p_content) then raise exception 'Message identifier is already in use'; end if;
    if exists(select 1 from public.coaching_messages where reply_to_message_id=p_message_id) then return; end if;
    select * into lease from private.coaching_processing_leases where message_id=p_message_id;
    if found and lease.expires_at>clock_timestamp() then return; end if;
    -- Pre-migration requests have no lease; allow the old worker a bounded grace period.
    if lease.message_id is null and message.status<>'failed' and message.created_at>clock_timestamp()-interval '15 minutes' then return; end if;
    update public.coaching_messages set status='completed',error_code=null where id=p_message_id returning * into message;
  end if;
  insert into private.coaching_processing_leases(message_id,token,expires_at)
    values(p_message_id,p_token,clock_timestamp()+interval '15 minutes')
    on conflict(message_id) do update set token=excluded.token,expires_at=excluded.expires_at;
  return next message;
end $$;
revoke all on function public.claim_coaching_message(uuid,uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.claim_coaching_message(uuid,uuid,uuid,uuid,text) to service_role;

create function public.fail_coaching_message(p_user_id uuid,p_message_id uuid,p_token uuid,p_error_code text)
returns setof public.coaching_messages language plpgsql security definer set search_path='' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('coach:' || p_message_id::text,0));
  if not exists(select 1 from private.coaching_processing_leases where message_id=p_message_id and token=p_token)
    or not exists(select 1 from public.coaching_messages where id=p_message_id and user_id=p_user_id and role='user')
    or exists(select 1 from public.coaching_messages where reply_to_message_id=p_message_id) then return; end if;
  return query update public.coaching_messages set status='failed',error_code=p_error_code where id=p_message_id returning *;
  delete from private.coaching_processing_leases where message_id=p_message_id and token=p_token;
end $$;
revoke all on function public.fail_coaching_message(uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.fail_coaching_message(uuid,uuid,uuid,text) to service_role;

create function public.complete_coaching_turn_leased(p_user_id uuid,p_session_id uuid,p_user_message_id uuid,
  p_assistant_message jsonb,p_retrievals jsonb,p_title text,p_token uuid)
returns setof public.coaching_messages language plpgsql security definer set search_path='' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('coach:' || p_user_message_id::text,0));
  if not exists(select 1 from private.coaching_processing_leases where message_id=p_user_message_id and token=p_token and expires_at>clock_timestamp()) then
    raise exception 'Processing claim expired or was replaced';
  end if;
  return query select * from public.complete_coaching_turn(p_user_id,p_session_id,p_user_message_id,p_assistant_message,p_retrievals,p_title);
  delete from private.coaching_processing_leases where message_id=p_user_message_id and token=p_token;
end $$;
revoke all on function public.complete_coaching_turn_leased(uuid,uuid,uuid,jsonb,jsonb,text,uuid) from public,anon,authenticated;
grant execute on function public.complete_coaching_turn_leased(uuid,uuid,uuid,jsonb,jsonb,text,uuid) to service_role;
commit;
