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
  created_at timestamptz not null default now()
);

-- Approximate-nearest-neighbour index for fast cosine search.
create index if not exists knowledge_documents_embedding_idx
  on public.knowledge_documents
  using hnsw (embedding vector_cosine_ops);

-- The corpus is shared (not per-user). The backend reads it with the service-role
-- key (which bypasses RLS); we still enable RLS and allow authenticated reads so the
-- app could read it directly if ever needed. Writes happen only from the ingest script.
alter table public.knowledge_documents enable row level security;
grant select on table public.knowledge_documents to authenticated;

drop policy if exists "Authenticated users can read knowledge" on public.knowledge_documents;
create policy "Authenticated users can read knowledge" on public.knowledge_documents
  for select to authenticated using (true);

-- ---------- vector search function (called by the backend via RPC) ----------
-- Returns the most similar chunks to a query embedding, with a similarity score.
create or replace function public.match_knowledge_documents(
  query_embedding vector(1024),
  match_count int default 5
)
returns table (
  id bigint,
  title text,
  content text,
  source text,
  similarity float
)
language sql
stable
as $$
  select
    kd.id,
    kd.title,
    kd.content,
    kd.source,
    1 - (kd.embedding <=> query_embedding) as similarity   -- cosine similarity
  from public.knowledge_documents kd
  order by kd.embedding <=> query_embedding                 -- nearest first
  limit match_count;
$$;
