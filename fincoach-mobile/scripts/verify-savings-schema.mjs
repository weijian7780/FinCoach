import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const migrationName = readdirSync(join(projectRoot, 'supabase', 'migrations')).find((name) =>
  name.endsWith('_complete_savings_goal_management.sql'),
);

assert.ok(migrationName, 'Missing CLI-generated complete_savings_goal_management migration.');

const recoveryPath = join(projectRoot, 'supabase', 'savings_uuid_recovery.sql');
assert.ok(existsSync(recoveryPath), 'Missing paste-ready UUID recovery SQL.');

const sources = [
  ['canonical schema', join(projectRoot, 'supabase', 'schema.sql')],
  ['Savings migration', join(projectRoot, 'supabase', 'migrations', migrationName)],
  ['UUID recovery SQL', recoveryPath],
];

const requiredFragments = [
  'create table if not exists public.savings_contributions',
  'references public.savings_goals (id) on delete cascade',
  'check (amount > 0)',
  'check (contributed_on <= current_date)',
  'alter table public.savings_contributions enable row level security',
  'private.refresh_savings_goal_amount',
  'create trigger refresh_savings_goal_amount',
  'security definer',
  "set search_path = ''",
  'revoke all on function private.refresh_savings_goal_amount()',
  'grant select, insert, delete on table public.savings_contributions to authenticated',
  'create policy "Users can read own savings contributions"',
  'create policy "Users can add own savings contributions"',
  'create policy "Users can delete own savings contributions"',
  'select auth.uid()',
  'add column if not exists deadline date',
  'goal_id uuid not null references public.savings_goals (id) on delete cascade',
  'affected_goal_id uuid;',
  'where g.id = affected_goal_id\n  for update;',
];

let failed = false;
for (const [label, path] of sources) {
  const sql = readFileSync(path, 'utf8').toLowerCase();
  if (/^\s*\+--/m.test(sql)) {
    failed = true;
    console.error(`${label} contains a stray patch marker before a SQL comment.`);
  }
  const missing = requiredFragments.filter((fragment) => !sql.includes(fragment.toLowerCase()));
  if (missing.length > 0) {
    failed = true;
    console.error(`${label} is missing:`);
    for (const fragment of missing) console.error(`  - ${fragment}`);
  }

  const deadlineUpgrade = sql.indexOf('add column if not exists deadline date');
  const deadlineGrant = sql.indexOf('grant update (name, target_amount, deadline, updated_at)');
  if (deadlineUpgrade === -1 || deadlineGrant === -1 || deadlineUpgrade > deadlineGrant) {
    failed = true;
    console.error(`${label} must add the legacy deadline column before granting access to it.`);
  }

  if (label === 'canonical schema' && !sql.includes('id uuid primary key default gen_random_uuid()')) {
    failed = true;
    console.error('canonical schema must create UUID savings goal IDs to match the deployed database contract.');
  }
}

if (failed) process.exit(1);
console.log('Savings schema verification passed for canonical schema and migration.');
