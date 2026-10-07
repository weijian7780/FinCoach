-- Commit a generated coaching reply and all related metadata in one transaction.
-- The function is callable only by the FastAPI service-role client.
create or replace function public.complete_coaching_turn(
  p_user_id uuid,
  p_session_id uuid,
  p_user_message_id uuid,
  p_assistant_message jsonb,
  p_retrievals jsonb,
  p_title text
)
returns setof public.coaching_messages
language plpgsql
security invoker
set search_path = ''
as $$
declare
  assistant public.coaching_messages;
begin
  if jsonb_typeof(p_assistant_message) <> 'object' then
    raise exception 'Assistant message payload must be an object.';
  end if;
  if jsonb_typeof(coalesce(p_retrievals, '[]'::jsonb)) <> 'array' then
    raise exception 'Retrieval payload must be an array.';
  end if;
  if not exists (
    select 1
    from public.coaching_sessions as session
    join public.coaching_messages as user_message
      on user_message.session_id = session.id
    where session.id = p_session_id
      and session.user_id = p_user_id
      and user_message.id = p_user_message_id
      and user_message.user_id = p_user_id
      and user_message.role = 'user'
  ) then
    raise exception 'Invalid coaching turn.';
  end if;

  insert into public.coaching_messages (
    id,
    session_id,
    user_id,
    role,
    content,
    reply_to_message_id,
    status,
    error_code,
    model,
    prompt_tokens,
    completion_tokens
  )
  values (
    (p_assistant_message ->> 'id')::uuid,
    p_session_id,
    p_user_id,
    'assistant',
    p_assistant_message ->> 'content',
    p_user_message_id,
    'completed',
    null,
    p_assistant_message ->> 'model',
    (p_assistant_message ->> 'prompt_tokens')::integer,
    (p_assistant_message ->> 'completion_tokens')::integer
  )
  returning * into assistant;

  insert into public.coaching_retrievals (
    user_id,
    assistant_message_id,
    knowledge_document_id,
    rank,
    similarity,
    title,
    source
  )
  select
    p_user_id,
    assistant.id,
    (item ->> 'knowledge_document_id')::bigint,
    (item ->> 'rank')::smallint,
    (item ->> 'similarity')::double precision,
    item ->> 'title',
    item ->> 'source'
  from jsonb_array_elements(coalesce(p_retrievals, '[]'::jsonb)) as entries(item);

  update public.coaching_messages
  set status = 'completed',
      error_code = null
  where id = p_user_message_id
    and user_id = p_user_id
    and role = 'user';

  update public.coaching_sessions
  set last_message_at = now(),
      title = coalesce(p_title, title)
  where id = p_session_id
    and user_id = p_user_id;

  return next assistant;
end;
$$;

revoke execute on function public.complete_coaching_turn(
  uuid, uuid, uuid, jsonb, jsonb, text
) from public, anon, authenticated;
grant execute on function public.complete_coaching_turn(
  uuid, uuid, uuid, jsonb, jsonb, text
) to service_role;
