import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const migrationsUrl = new URL('../supabase/migrations/', import.meta.url);
const schemaUrl = new URL('../supabase/schema.sql', import.meta.url);

for (const [name, sql] of [
  ...readdirSync(migrationsUrl)
    .filter((fileName) => fileName.endsWith('.sql'))
    .map((fileName) => [
      `supabase/migrations/${fileName}`,
      readFileSync(new URL(fileName, migrationsUrl), 'utf8'),
    ]),
  ['supabase/schema.sql', readFileSync(schemaUrl, 'utf8')],
]) {
  const lines = sql.split(/\r?\n/);
  const patchArtifactIndex = lines.findIndex((line) => line.startsWith('+'));
  if (patchArtifactIndex >= 0) {
    throw new Error(
      `${name}:${patchArtifactIndex + 1} starts with an accidental patch marker (+).`,
    );
  }
}

const migrationName = readdirSync(migrationsUrl).find((name) =>
  name.endsWith('_complete_ai_financial_coaching.sql'),
);
const securityMigrationName = readdirSync(migrationsUrl).find((name) =>
  name.endsWith('_secure_ai_coaching_message_ownership.sql'),
);
const completionMigrationName = readdirSync(migrationsUrl).find((name) =>
  name.endsWith('_transactional_ai_coaching_completion.sql'),
);
const feedbackMigrationName = readdirSync(migrationsUrl).find((name) =>
  name.endsWith('_add_ai_coaching_message_feedback.sql'),
);
const agentInteractionMigrationName = readdirSync(migrationsUrl).find((name) =>
  name.endsWith('_add_coach_agent_interactions.sql'),
);

if (!migrationName) {
  throw new Error('AI coaching migration is missing.');
}
if (!securityMigrationName) {
  throw new Error('AI coaching ownership security migration is missing.');
}
if (!completionMigrationName) {
  throw new Error('AI coaching transactional completion migration is missing.');
}
if (!feedbackMigrationName) {
  throw new Error('AI coaching message feedback migration is missing.');
}
if (!agentInteractionMigrationName) {
  throw new Error('AI coaching agent-interaction migration is missing.');
}

const migration = readFileSync(new URL(migrationName, migrationsUrl), 'utf8').toLowerCase();
const securityMigration = readFileSync(
  new URL(securityMigrationName, migrationsUrl),
  'utf8',
).toLowerCase();
const completionMigration = readFileSync(
  new URL(completionMigrationName, migrationsUrl),
  'utf8',
).toLowerCase();
const feedbackMigration = readFileSync(
  new URL(feedbackMigrationName, migrationsUrl),
  'utf8',
).toLowerCase();
const agentInteractionMigration = readFileSync(
  new URL(agentInteractionMigrationName, migrationsUrl),
  'utf8',
).toLowerCase();
const schema = readFileSync(schemaUrl, 'utf8').toLowerCase();

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
  'drop function if exists public.match_knowledge_documents(vector, integer)',
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

for (const [label, sql] of [
  ['migration', migration],
  ['schema', schema],
]) {
  const dropAt = sql.indexOf('drop function if exists public.match_knowledge_documents(vector, integer)');
  const createAt = sql.indexOf('create or replace function public.match_knowledge_documents');
  if (dropAt < 0 || createAt < 0 || dropAt > createAt) {
    throw new Error(`${label} must drop the old vector RPC before recreating its return type.`);
  }

  const functionEndAt = sql.indexOf('$$;', createAt);
  const vectorRpc = sql.slice(createAt, functionEndAt);
  if (!vectorRpc.includes('set search_path = pg_catalog, extensions, public')) {
    throw new Error(`${label} vector RPC must include the pgvector extension schema in its search path.`);
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

const ownershipPolicyFragments = [
  'drop policy if exists "users can send own coaching messages"',
  'create policy "users can send own coaching messages"',
  'exists (',
  'session.id = coaching_messages.session_id',
  'session.user_id = (select auth.uid())',
];

for (const [label, sql] of [
  ['security migration', securityMigration],
  ['schema', schema],
]) {
  for (const fragment of ownershipPolicyFragments) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing session ownership enforcement: ${fragment}`);
    }
  }
}

const completionFunctionFragments = [
  'create or replace function public.complete_coaching_turn',
  'returns setof public.coaching_messages',
  'security invoker',
  'insert into public.coaching_messages',
  'insert into public.coaching_retrievals',
  'update public.coaching_messages',
  'update public.coaching_sessions',
  'revoke execute on function public.complete_coaching_turn',
  'grant execute on function public.complete_coaching_turn',
];

for (const [label, sql] of [
  ['completion migration', completionMigration],
  ['schema', schema],
]) {
  for (const fragment of completionFunctionFragments) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing atomic turn completion SQL: ${fragment}`);
    }
  }
}

const feedbackConstraintFragments = [
  'coaching_messages_feedback_check',
  "role = 'assistant'",
  "feedback in ('helpful', 'not_helpful')",
];

for (const [label, sql] of [
  ['feedback migration', feedbackMigration],
  ['schema', schema],
]) {
  for (const fragment of feedbackConstraintFragments) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing persistent message feedback SQL: ${fragment}`);
    }
  }
}
if (!feedbackMigration.includes('add column if not exists feedback text')) {
  throw new Error('feedback migration is missing the feedback column upgrade.');
}
if (!schema.includes('feedback text,')) {
  throw new Error('schema is missing the feedback column definition.');
}

const agentInteractionFragments = [
  'coaching_messages_ui_payload_object_check',
  "jsonb_typeof(ui_payload) = 'object'",
  "coalesce(p_assistant_message -> 'ui_payload', '{}'::jsonb)",
];

for (const [label, sql] of [
  ['agent interaction migration', agentInteractionMigration],
  ['schema', schema],
]) {
  for (const fragment of agentInteractionFragments) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing durable agent interaction SQL: ${fragment}`);
    }
  }
}
if (!agentInteractionMigration.includes(
  "add column if not exists ui_payload jsonb not null default '{}'::jsonb",
)) {
  throw new Error('agent interaction migration is missing the ui_payload column upgrade.');
}
if (!schema.includes("ui_payload jsonb not null default '{}'::jsonb")) {
  throw new Error('schema is missing the ui_payload column definition.');
}

process.stdout.write(`COACHING_SCHEMA_VERIFIED ${root}\n`);
