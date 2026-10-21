-- Persist one optional user rating for each AI-generated coaching message.
alter table public.coaching_messages
  add column if not exists feedback text;

alter table public.coaching_messages
  drop constraint if exists coaching_messages_feedback_check;

alter table public.coaching_messages
  add constraint coaching_messages_feedback_check
  check (
    feedback is null
    or (
      role = 'assistant'
      and feedback in ('helpful', 'not_helpful')
    )
  );

comment on column public.coaching_messages.feedback is
  'Optional owner rating for an assistant response: helpful or not_helpful.';
