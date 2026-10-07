import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const migrationName = readdirSync(join(projectRoot, 'supabase', 'migrations')).find((name) =>
  name.endsWith('_complete_budget_category_limit_management.sql'),
);

assert.ok(migrationName, 'Missing CLI-generated Budget migration.');

const sources = [
  ['canonical schema', join(projectRoot, 'supabase', 'schema.sql')],
  ['Budget migration', join(projectRoot, 'supabase', 'migrations', migrationName)],
];

const requiredFragments = [
  'create table if not exists public.monthly_budgets',
  'id uuid primary key default gen_random_uuid()',
  'user_id uuid not null references auth.users (id) on delete cascade',
  'limit_amount numeric(12, 2) not null check (limit_amount > 0)',
  'unique (user_id, month)',
  'add column if not exists user_id uuid',
  'add column if not exists color text',
  'foreign key (user_id, month)',
  'references public.monthly_budgets (user_id, month) on delete cascade',
  'private.validate_budget_allocations',
  'create trigger validate_category_budget_allocations',
  'create trigger validate_monthly_budget_allocations',
  'alter table public.monthly_budgets enable row level security',
  'alter table public.budgets enable row level security',
  'alter table public.categories enable row level security',
  'grant select, insert, update, delete on table public.monthly_budgets to authenticated',
  'grant select, insert, update, delete on table public.budgets to authenticated',
  'create policy "Users can read own monthly budgets"',
  'create policy "Users can update own monthly budgets"',
  'create policy "Users can read visible expense categories"',
  'create policy "Users can create own custom categories"',
  'create policy "Users can update own custom categories"',
  'create policy "Users can delete own custom categories"',
  'using ((select auth.uid()) = user_id)',
  'with check ((select auth.uid()) = user_id)',
];

let failed = false;
for (const [label, path] of sources) {
  const sql = readFileSync(path, 'utf8').toLowerCase();
  const missing = requiredFragments.filter((fragment) => !sql.includes(fragment.toLowerCase()));
  if (missing.length > 0) {
    failed = true;
    console.error(`${label} is missing:`);
    for (const fragment of missing) console.error(`  - ${fragment}`);
  }

  if (sql.includes('goal_id bigint') || sql.includes('monthly_budget_id bigint')) {
    failed = true;
    console.error(`${label} contains a known incompatible bigint/UUID relationship.`);
  }
}

if (failed) process.exit(1);
console.log('Budget schema verification passed for canonical schema and migration.');
