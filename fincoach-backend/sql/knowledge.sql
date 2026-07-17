-- ============================================================
-- FinCoach — RAG knowledge base (Supabase / pgvector)
-- Run this in the Supabase SQL Editor (project yqsyrzdpvtasldkthhfg).
-- Maps to the ERD entity KNOWLEDGE DOCUMENT. One row = one chunk.
-- ============================================================

-- pgvector extension (vector storage + similarity search)
create extension if not exists vector;

-- ---------- knowledge_documents : ERD KNOWLEDGE DOCUMENT ----------
-- bge-m3 produces 1024-dim embeddings, so the column is vector(1024).
create table if not exists public.knowledge_documents (
  id bigint generated always as identity primary key,
  title text,                                  -- KNOWLEDGE_Title
  content text not null,                       -- KNOWLEDGE_Content (one chunk)
  source text,                                 -- KNOWLEDGE_Source (file / url)
  embedding vector(1024) not null,             -- KNOWLEDGE_Embedding
  page_number integer,
  chunk_index integer,
  content_hash text,
  created_at timestamptz not null default now()
);

alter table public.knowledge_documents add column if not exists page_number integer;
alter table public.knowledge_documents add column if not exists chunk_index integer;
alter table public.knowledge_documents add column if not exists content_hash text;

create unique index if not exists knowledge_documents_content_hash_idx
  on public.knowledge_documents (content_hash);

-- Approximate-nearest-neighbour index for fast cosine search.
create index if not exists knowledge_documents_embedding_idx
  on public.knowledge_documents
  using hnsw (embedding vector_cosine_ops);

-- The corpus is shared (not per-user). The backend reads it with the service-role
-- key (which bypasses RLS). The mobile app never reads raw chunks or embeddings;
-- ingestion and retrieval are server-only operations.
alter table public.knowledge_documents enable row level security;
drop policy if exists "Authenticated users can read knowledge" on public.knowledge_documents;
revoke all on table public.knowledge_documents from anon, authenticated;
revoke select on table public.knowledge_documents from anon, authenticated;
grant select, insert, update, delete on table public.knowledge_documents to service_role;
grant usage, select on sequence public.knowledge_documents_id_seq to service_role;

-- ---------- vector search function (called by the backend via RPC) ----------
-- Returns the most similar chunks to a query embedding, with a similarity score.
drop function if exists public.match_knowledge_documents(vector, integer);

create or replace function public.match_knowledge_documents(
  query_embedding vector(1024),
  match_count int default 5
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
    kd.id,
    kd.title,
    kd.content,
    kd.source,
    kd.page_number,
    kd.chunk_index,
    1 - (kd.embedding <=> query_embedding) as similarity   -- cosine similarity
  from public.knowledge_documents kd
  order by kd.embedding <=> query_embedding                 -- nearest first
  limit greatest(1, least(match_count, 10));
$$;

revoke execute on function public.match_knowledge_documents(vector, integer) from public;
revoke execute on function public.match_knowledge_documents(vector, integer) from anon, authenticated;
grant execute on function public.match_knowledge_documents(vector, integer) to service_role;
