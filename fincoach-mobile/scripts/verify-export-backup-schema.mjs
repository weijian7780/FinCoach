import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const migration = readFileSync(
  new URL(
    '../supabase/migrations/20260716131958_complete_financial_data_export_backup.sql',
    import.meta.url,
  ),
  'utf8',
).toLowerCase();
const schema = readFileSync(new URL('../supabase/schema.sql', import.meta.url), 'utf8').toLowerCase();

const required = [
  'create table if not exists public.data_exports',
  'create table if not exists public.export_contents',
  'primary key (export_id, content_type)',
  'create table if not exists public.backups',
  'add column if not exists auto_backup_enabled',
  "'financial-backups'",
  "array['application/json']",
  '10485760',
  'alter table public.data_exports enable row level security',
  'alter table public.export_contents enable row level security',
  'alter table public.backups enable row level security',
  '(storage.foldername(name))[1] = (select auth.uid()::text)',
  'create or replace function public.restore_financial_backup_v1',
  'security definer',
  "set search_path = ''",
  'revoke execute on function public.restore_financial_backup_v1',
];

for (const [label, sql] of [
  ['migration', migration],
  ['schema', schema],
]) {
  for (const fragment of required) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing required export/backup SQL: ${fragment}`);
    }
  }
}

const relationshipChecks = [
  'references public.data_exports (id) on delete cascade',
  "content_type in ('transaction', 'budget', 'savings', 'report')",
  'data_exports_user_created_idx',
  'backups_user_created_idx',
  'backups_user_automatic_idx',
  'for select to authenticated',
  'for insert to authenticated',
  'for update to authenticated',
  'for delete to authenticated',
  'with check ((select auth.uid()) = user_id)',
  'grant execute on function public.restore_financial_backup_v1(jsonb, uuid) to authenticated',
];

for (const fragment of relationshipChecks) {
  if (!migration.includes(fragment)) {
    throw new Error(`migration is missing normalized/security SQL: ${fragment}`);
  }
}

process.stdout.write(`EXPORT_BACKUP_SCHEMA_VERIFIED ${root}\n`);
