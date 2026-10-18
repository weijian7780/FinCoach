import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const migrationName = readdirSync(join(projectRoot, 'supabase', 'migrations')).find((name) =>
  name.endsWith('_complete_transaction_receipt_capture.sql'),
);

assert.ok(migrationName, 'Missing CLI-generated complete_transaction_receipt_capture migration.');

const sources = [
  ['canonical schema', join(projectRoot, 'supabase', 'schema.sql')],
  ['Transaction migration', join(projectRoot, 'supabase', 'migrations', migrationName)],
];

const requiredFragments = [
  'create table if not exists public.transactions',
  'id uuid primary key default gen_random_uuid()',
  'user_id uuid not null references auth.users (id) on delete cascade',
  'category_id bigint not null references public.categories (id)',
  'amount numeric(12, 2) not null check (amount > 0)',
  'transaction_date date not null check (transaction_date <= current_date)',
  'receipt_image_path text',
  'transactions_user_date_idx',
  'transactions_user_category_date_idx',
  'alter table public.transactions enable row level security',
  'grant select, insert, update, delete on table public.transactions to authenticated',
  'create policy "Users can read own transactions"',
  'create policy "Users can add own transactions"',
  'create policy "Users can update own transactions"',
  'create policy "Users can delete own transactions"',
  'using ((select auth.uid()) = user_id)',
  'with check ((select auth.uid()) = user_id)',
  "values ('Income', 'income', 'payments', '#06a96b')",
  "values ( 'receipts', 'receipts', false, 5242880",
  'image/jpeg',
  'image/png',
  'image/webp',
  'create policy "Users can read own receipt images"',
  'create policy "Users can upload own receipt images"',
  'create policy "Users can delete own receipt images"',
  "bucket_id = 'receipts'",
  "(storage.foldername(name))[1] = (select auth.uid()::text)",
];

let failed = false;
for (const [label, path] of sources) {
  const sql = readFileSync(path, 'utf8').toLowerCase().replace(/\s+/g, ' ');
  const missing = requiredFragments.filter((fragment) =>
    !sql.includes(fragment.toLowerCase().replace(/\s+/g, ' ')),
  );
  if (missing.length > 0) {
    failed = true;
    console.error(`${label} is missing:`);
    for (const fragment of missing) console.error(`  - ${fragment}`);
  }
}

if (failed) process.exit(1);
console.log('Transaction schema verification passed for canonical schema and migration.');
