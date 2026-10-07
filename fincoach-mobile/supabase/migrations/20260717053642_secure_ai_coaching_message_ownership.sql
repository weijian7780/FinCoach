-- Prevent an authenticated user from attaching a message to another user's
-- conversation by supplying that conversation UUID.
drop policy if exists "Users can send own coaching messages"
  on public.coaching_messages;

create policy "Users can send own coaching messages"
  on public.coaching_messages
  for insert
  to authenticated
  with check (
    (select auth.uid()) is not null
    and (select auth.uid()) = user_id
    and role = 'user'
    and exists (
      select 1
      from public.coaching_sessions as session
      where session.id = coaching_messages.session_id
        and session.user_id = (select auth.uid())
    )
  );
