-- AI Financial Coaching: shared RAG knowledge plus owner-scoped conversation history.
create extension if not exists vector;

create table if not exists public.knowledge_documents (
  id bigint generated always as identity primary key,
  title text,
  content text not null,
  source text,
  embedding vector(1024) not null,
  page_number integer,
  chunk_index integer,
  content_hash text,
  created_at timestamptz not null default now(),
  constraint knowledge_documents_page_number_check check (page_number is null or page_number > 0),
  constraint knowledge_documents_chunk_index_check check (chunk_index is null or chunk_index >= 0)
);

alter table public.knowledge_documents add column if not exists page_number integer;
alter table public.knowledge_documents add column if not exists chunk_index integer;
alter table public.knowledge_documents add column if not exists content_hash text;

create unique index if not exists knowledge_documents_content_hash_idx
  on public.knowledge_documents (content_hash);
create index if not exists knowledge_documents_embedding_idx
  on public.knowledge_documents using hnsw (embedding vector_cosine_ops);

create or replace function public.match_knowledge_documents(
  query_embedding vector(1024),
  match_count integer default 5
)
returns table (
  id bigint,
  title text,
  content text,
  source text,
  page_number integer,
  chunk_index integer,
  similarity double precision
)
language sql
stable
set search_path = ''
as $$
  select
    document.id,
    document.title,
    document.content,
    document.source,
    document.page_number,
    document.chunk_index,
    1 - (document.embedding <=> query_embedding) as similarity
  from public.knowledge_documents as document
  order by document.embedding <=> query_embedding
  limit greatest(1, least(match_count, 10));
$$;

alter table public.knowledge_documents enable row level security;
drop policy if exists "Authenticated users can read knowledge" on public.knowledge_documents;
revoke all on table public.knowledge_documents from anon, authenticated;
revoke select on table public.knowledge_documents from anon, authenticated;
grant select, insert, update, delete on table public.knowledge_documents to service_role;
grant usage, select on sequence public.knowledge_documents_id_seq to service_role;
revoke execute on function public.match_knowledge_documents(vector, integer) from public;
revoke execute on function public.match_knowledge_documents(vector, integer) from anon, authenticated;
grant execute on function public.match_knowledge_documents(vector, integer) to service_role;

create table if not exists public.coaching_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz not null default now(),
  constraint coaching_sessions_title_check check (char_length(btrim(title)) between 1 and 80)
);

create table if not exists public.coaching_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.coaching_sessions (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null,
  content text not null,
  reply_to_message_id uuid references public.coaching_messages (id) on delete set null,
  status text not null default 'completed',
  error_code text,
  model text,
  prompt_tokens integer,
  completion_tokens integer,
  created_at timestamptz not null default now(),
  constraint coaching_messages_role_check check (role in ('user', 'assistant')),
  constraint coaching_messages_status_check check (status in ('completed', 'failed')),
  constraint coaching_messages_content_check check (char_length(btrim(content)) between 1 and 8000),
  constraint coaching_messages_reply_shape_check check (
    (role = 'user' and reply_to_message_id is null)
    or (role = 'assistant' and reply_to_message_id is not null)
  ),
  constraint coaching_messages_prompt_tokens_check check (prompt_tokens is null or prompt_tokens >= 0),
  constraint coaching_messages_completion_tokens_check check (completion_tokens is null or completion_tokens >= 0),
  unique (reply_to_message_id)
);

create table if not exists public.coaching_retrievals (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  assistant_message_id uuid not null references public.coaching_messages (id) on delete cascade,
  knowledge_document_id bigint references public.knowledge_documents (id) on delete set null,
  rank smallint not null,
  similarity double precision not null,
  title text,
  source text,
  created_at timestamptz not null default now(),
  constraint coaching_retrievals_rank_check check (rank between 1 and 10),
  constraint coaching_retrievals_similarity_check check (similarity between -1 and 1),
  unique (assistant_message_id, knowledge_document_id)
);

create index if not exists coaching_sessions_user_last_message_idx
  on public.coaching_sessions (user_id, last_message_at desc);
create index if not exists coaching_messages_session_created_idx
  on public.coaching_messages (session_id, created_at asc);
create index if not exists coaching_messages_user_created_idx
  on public.coaching_messages (user_id, created_at desc)
  where role = 'user';
create index if not exists coaching_retrievals_message_rank_idx
  on public.coaching_retrievals (assistant_message_id, rank asc);

alter table public.coaching_sessions enable row level security;
alter table public.coaching_messages enable row level security;
alter table public.coaching_retrievals enable row level security;

grant select, insert, update, delete on table public.coaching_sessions to authenticated;
grant select, insert on table public.coaching_messages to authenticated;
grant select on table public.coaching_retrievals to authenticated;
grant select, insert, update, delete on table public.coaching_sessions to service_role;
grant select, insert, update, delete on table public.coaching_messages to service_role;
grant select, insert, update, delete on table public.coaching_retrievals to service_role;
grant usage, select on sequence public.coaching_retrievals_id_seq to service_role;

drop policy if exists "Users can read own coaching sessions" on public.coaching_sessions;
create policy "Users can read own coaching sessions"
  on public.coaching_sessions for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own coaching sessions" on public.coaching_sessions;
create policy "Users can create own coaching sessions"
  on public.coaching_sessions for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update own coaching sessions" on public.coaching_sessions;
create policy "Users can update own coaching sessions"
  on public.coaching_sessions for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete own coaching sessions" on public.coaching_sessions;
create policy "Users can delete own coaching sessions"
  on public.coaching_sessions for delete to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can read own coaching messages" on public.coaching_messages;
create policy "Users can read own coaching messages"
  on public.coaching_messages for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can send own coaching messages" on public.coaching_messages;
create policy "Users can send own coaching messages"
  on public.coaching_messages for insert to authenticated
  with check ((select auth.uid()) = user_id and role = 'user');

drop policy if exists "Users can read own coaching retrievals" on public.coaching_retrievals;
create policy "Users can read own coaching retrievals"
  on public.coaching_retrievals for select to authenticated
  using ((select auth.uid()) = user_id);

drop trigger if exists coaching_sessions_set_updated_at on public.coaching_sessions;
create trigger coaching_sessions_set_updated_at
before update on public.coaching_sessions
for each row execute function private.set_updated_at();
