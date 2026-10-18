-- Targeted compatibility repair for installed mobile clients sending receipt_items.
-- Existing transactions receive an empty item list; no transactions are deleted.
-- This does not mark the broader financial-integrity migration as deployed.
begin;
alter table public.transactions
  add column if not exists receipt_items jsonb not null default '[]'::jsonb;
notify pgrst, 'reload schema';
commit;

-- Confirm the column is available after committing.
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'transactions'
  and column_name = 'receipt_items';
