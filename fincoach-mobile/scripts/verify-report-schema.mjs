import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const migrationPath = new URL(
  '../supabase/migrations/20260716025356_complete_financial_report_analytics.sql',
  import.meta.url,
);
const migration = readFileSync(migrationPath, 'utf8').toLowerCase();
const schema = readFileSync(new URL('../supabase/schema.sql', import.meta.url), 'utf8').toLowerCase();

const required = [
  'create table if not exists public.reports',
  'reports_type_check',
  'reports_user_generated_idx',
  'alter table public.reports enable row level security',
  'for select to authenticated',
  'for insert to authenticated',
  '(select auth.uid()) = user_id',
  'revoke update, delete on table public.reports from authenticated',
  'drop policy if exists "users manage own reports"',
];

for (const [label, sql] of [['migration', migration], ['schema', schema]]) {
  for (const fragment of required) {
    if (!sql.includes(fragment)) {
      throw new Error(`${label} is missing required report SQL: ${fragment}`);
    }
  }
}

if (!migration.includes("'monthly_category'") || !migration.includes("'custom_category'")) {
  throw new Error('migration is missing constrained category report types');
}

process.stdout.write(`REPORT_SCHEMA_VERIFIED ${root}\n`);
