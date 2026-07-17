import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const migrationsUrl = new URL('../supabase/migrations/', import.meta.url);
const migrationName = readdirSync(migrationsUrl).find((name) =>
  name.endsWith('_complete_ai_financial_coaching.sql'),
);

if (!migrationName) {
  throw new Error('AI coaching migration is missing.');
}

const migration = readFileSync(new URL(migrationName, migrationsUrl), 'utf8').toLowerCase();
const schema = readFileSync(new URL('../supabase/schema.sql', import.meta.url), 'utf8').toLowerCase();

const requiredInBoth = [
  'create table if not exists public.coaching_sessions',
  'create table if not exists public.coaching_messages',
  'create table if not exists public.coaching_retrievals',
  'alter table public.coaching_sessions enable row level security',
  'alter table public.coaching_messages enable row level security',
  'alter table public.coaching_retrievals enable row level security',
  'coaching_sessions_user_last_message_idx',
  'coaching_messages_session_created_idx',
  'coaching_messages_user_created_idx',
  'coaching_retrievals_message_rank_idx',
  'with check ((select auth.uid()) = user_id)',
  "role = 'user'",
  'unique (reply_to_message_id)',
  'unique (assistant_message_id, knowledge_document_id)',
  'add column if not exists page_number integer',
  'add column if not exists chunk_index integer',
  'add column if not exists content_hash text',
  'revoke select on table public.knowledge_documents from anon, authenticated',
  'revoke execute on function public.match_knowledge_documents(vector, integer)',
];

for (const [label, sql] of [
  ['migration', migration],
  ['schema', schema],
]) {
  for (const fragment of requiredInBoth) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing required coaching SQL: ${fragment}`);
    }
  }
}

const migrationOnly = [
  'references auth.users (id) on delete cascade',
  'references public.coaching_sessions (id) on delete cascade',
  'references public.coaching_messages (id) on delete cascade',
  'references public.knowledge_documents (id) on delete set null',
  'for select to authenticated',
  'for insert to authenticated',
  'for update to authenticated',
  'for delete to authenticated',
  "check (role in ('user', 'assistant'))",
  "check (status in ('completed', 'failed'))",
  'grant select, insert, update, delete on table public.coaching_sessions to authenticated',
  'grant select, insert on table public.coaching_messages to authenticated',
  'grant select on table public.coaching_retrievals to authenticated',
];

for (const fragment of migrationOnly) {
  if (!migration.includes(fragment)) {
    throw new Error(`migration is missing coaching relationship/security SQL: ${fragment}`);
  }
}

process.stdout.write(`COACHING_SCHEMA_VERIFIED ${root}\n`);
