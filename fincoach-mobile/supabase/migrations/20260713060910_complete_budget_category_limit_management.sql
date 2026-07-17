-- Budget and Category Limit Management (FRBL-01 through FRBL-05)
-- Safe to run against the legacy schema where budgets are per-category rows.

create extension if not exists pgcrypto;
create schema if not exists private;

-- Extend the shared category lookup with user-owned custom categories.
alter table public.categories
  add column if not exists user_id uuid,
  add column if not exists color text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'categories_user_id_fkey'
      and conrelid = 'public.categories'::regclass
  ) then
    alter table public.categories
      add constraint categories_user_id_fkey
      foreign key (user_id) references auth.users (id) on delete cascade;
  end if;
end;
$$;

alter table public.categories drop constraint if exists categories_name_key;

create unique index if not exists categories_default_name_unique
  on public.categories (lower(name))
  where user_id is null;

create unique index if not exists categories_user_name_unique
  on public.categories (user_id, lower(name))
  where user_id is not null;

update public.categories
set color = case name
  when 'Food' then '#E45C3A'
  when 'Transport' then '#3C78D8'
  when 'Rent' then '#7E57C2'
  when 'Entertainment' then '#D64C7F'
  when 'Education' then '#00897B'
  else '#6B7280'
end
where color is null and user_id is null;

insert into public.categories (name, type, icon, color) values
  ('Food', 'expense', 'restaurant', '#E45C3A'),
  ('Transport', 'expense', 'directions-car', '#3C78D8'),
  ('Rent', 'expense', 'home', '#7E57C2'),
  ('Entertainment', 'expense', 'movie', '#D64C7F'),
  ('Education', 'expense', 'school', '#00897B'),
  ('Others', 'expense', 'more-horiz', '#6B7280')
on conflict do nothing;

-- One overall parent budget per user and calendar month.
create table if not exists public.monthly_budgets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  month date not null,
  limit_amount numeric(12, 2) not null check (limit_amount > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, month),
  constraint monthly_budgets_month_first_day_check
    check (month = date_trunc('month', month)::date)
);

create index if not exists monthly_budgets_user_month_idx
  on public.monthly_budgets (user_id, month desc);

-- Preserve legacy category limits by deriving the smallest valid parent total.
insert into public.monthly_budgets (user_id, month, limit_amount)
select user_id, month, sum(amount)
from public.budgets
where amount > 0
group by user_id, month
on conflict (user_id, month) do update
set limit_amount = greatest(public.monthly_budgets.limit_amount, excluded.limit_amount),
    updated_at = now();

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'budgets_amount_positive_check'
      and conrelid = 'public.budgets'::regclass
  ) then
    alter table public.budgets
      add constraint budgets_amount_positive_check check (amount > 0);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'budgets_month_first_day_check'
      and conrelid = 'public.budgets'::regclass
  ) then
    alter table public.budgets
      add constraint budgets_month_first_day_check
      check (month = date_trunc('month', month)::date);
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'budgets_monthly_budget_fkey'
      and conrelid = 'public.budgets'::regclass
  ) then
    alter table public.budgets
      add constraint budgets_monthly_budget_fkey
      foreign key (user_id, month)
      references public.monthly_budgets (user_id, month) on delete cascade;
  end if;
end;
$$;

create index if not exists budgets_user_month_idx
  on public.budgets (user_id, month desc);

-- Enforce that category allocations never exceed their monthly parent total.
create or replace function private.validate_budget_allocations()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  parent_limit numeric(12, 2);
  allocated numeric(12, 2);
begin
  if tg_table_name = 'budgets' then
    select mb.limit_amount
    into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new.user_id and mb.month = new.month;

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new.user_id
      and b.month = new.month
      and b.id <> coalesce(new.id, -1);

    if allocated + new.amount > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new.user_id and b.month = new.month;

    if allocated > new.limit_amount then
      raise exception 'Overall monthly budget cannot be lower than allocated category limits.'
        using errcode = '23514';
    end if;
  end if;

  new.updated_at = now();
  return new;
end;
$$;

revoke all on function private.validate_budget_allocations() from public, anon, authenticated;

drop trigger if exists validate_category_budget_allocations on public.budgets;
create trigger validate_category_budget_allocations
  before insert or update of user_id, month, amount on public.budgets
  for each row execute function private.validate_budget_allocations();

drop trigger if exists validate_monthly_budget_allocations on public.monthly_budgets;
create trigger validate_monthly_budget_allocations
  before insert or update of user_id, month, limit_amount on public.monthly_budgets
  for each row execute function private.validate_budget_allocations();

-- Data API grants and owner-based RLS.
alter table public.monthly_budgets enable row level security;
alter table public.budgets enable row level security;
alter table public.categories enable row level security;

grant select, insert, update, delete on table public.monthly_budgets to authenticated;
grant select, insert, update, delete on table public.budgets to authenticated;
grant select, insert, update, delete on table public.categories to authenticated;
grant usage, select on sequence public.categories_id_seq to authenticated;
grant usage, select on sequence public.budgets_id_seq to authenticated;

drop policy if exists "Users can read own monthly budgets" on public.monthly_budgets;
create policy "Users can read own monthly budgets" on public.monthly_budgets
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own monthly budgets" on public.monthly_budgets;
create policy "Users can create own monthly budgets" on public.monthly_budgets
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update own monthly budgets" on public.monthly_budgets;
create policy "Users can update own monthly budgets" on public.monthly_budgets
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete own monthly budgets" on public.monthly_budgets;
create policy "Users can delete own monthly budgets" on public.monthly_budgets
  for delete to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users manage own budgets" on public.budgets;
drop policy if exists "Users can read own category limits" on public.budgets;
create policy "Users can read own category limits" on public.budgets
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own category limits" on public.budgets;
create policy "Users can create own category limits" on public.budgets
  for insert to authenticated
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.categories c
      where c.id = category_id
        and c.type = 'expense'
        and (c.user_id is null or c.user_id = (select auth.uid()))
    )
  );

drop policy if exists "Users can update own category limits" on public.budgets;
create policy "Users can update own category limits" on public.budgets
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.categories c
      where c.id = category_id
        and c.type = 'expense'
        and (c.user_id is null or c.user_id = (select auth.uid()))
    )
  );

drop policy if exists "Users can delete own category limits" on public.budgets;
create policy "Users can delete own category limits" on public.budgets
  for delete to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Authenticated users can read categories" on public.categories;
drop policy if exists "Users can read visible expense categories" on public.categories;
create policy "Users can read visible expense categories" on public.categories
  for select to authenticated
  using (user_id is null or (select auth.uid()) = user_id);

drop policy if exists "Users can create own custom categories" on public.categories;
create policy "Users can create own custom categories" on public.categories
  for insert to authenticated
  with check ((select auth.uid()) = user_id and type = 'expense');

drop policy if exists "Users can update own custom categories" on public.categories;
create policy "Users can update own custom categories" on public.categories
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id and type = 'expense');

drop policy if exists "Users can delete own custom categories" on public.categories;
create policy "Users can delete own custom categories" on public.categories
  for delete to authenticated
  using ((select auth.uid()) = user_id);
