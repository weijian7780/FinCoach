
create extension if not exists pgcrypto;
create schema if not exists private;

insert into public.categories (name, type, icon, color)
values ('Income', 'income', 'payments', '#06a96b')
on conflict do nothing;

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  category_id bigint not null references public.categories (id),
  amount numeric(12, 2) not null check (amount > 0),
  transaction_date date not null check (transaction_date <= current_date),
  description text check (description is null or char_length(description) <= 300),
  source text not null check (char_length(btrim(source)) between 1 and 120),
  receipt_image_path text check (
    receipt_image_path is null
    or char_length(receipt_image_path) between 1 and 512
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists transactions_user_date_idx
  on public.transactions (user_id, transaction_date desc, created_at desc);

create index if not exists transactions_user_category_date_idx
  on public.transactions (user_id, category_id, transaction_date desc);

create or replace function private.validate_transaction_category()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.categories c
    where c.id = new.category_id
      and (c.user_id is null or c.user_id = new.user_id)
      and c.type in ('expense', 'income')
  ) then
    raise exception 'Transaction category is not available to this user.'
      using errcode = '23503';
  end if;

  new.source = btrim(new.source);
  new.description = nullif(btrim(coalesce(new.description, '')), '');
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function private.validate_transaction_category()
  from public, anon, authenticated;

drop trigger if exists validate_transaction_category on public.transactions;
create trigger validate_transaction_category
  before insert or update of user_id, category_id, source, description
  on public.transactions
  for each row execute function private.validate_transaction_category();

alter table public.transactions enable row level security;

revoke all on table public.transactions from anon;
grant select, insert, update, delete on table public.transactions to authenticated;

drop policy if exists "Users can read own transactions" on public.transactions;
drop policy if exists "Users can add own transactions" on public.transactions;
drop policy if exists "Users can update own transactions" on public.transactions;
drop policy if exists "Users can delete own transactions" on public.transactions;

create policy "Users can read own transactions"
on public.transactions
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can add own transactions"
on public.transactions
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users can update own transactions"
on public.transactions
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users can delete own transactions"
on public.transactions
for delete
to authenticated
using ((select auth.uid()) = user_id);

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'receipts',
  'receipts',
  false,
  5242880,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read own receipt images" on storage.objects;
drop policy if exists "Users can upload own receipt images" on storage.objects;
drop policy if exists "Users can delete own receipt images" on storage.objects;

create policy "Users can read own receipt images"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'receipts'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);

create policy "Users can upload own receipt images"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'receipts'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);

create policy "Users can delete own receipt images"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'receipts'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);
