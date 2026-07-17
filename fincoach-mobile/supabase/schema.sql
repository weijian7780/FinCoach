-- ============================================================
-- FinCoach — database schema (PostgreSQL / Supabase)
-- Paste into Supabase SQL Editor on a fresh project and Run.
-- Scope: auth + Module 1 (Financial Profile Management).
-- The USER entity is stored in `profiles` (linked to Supabase auth.users).
-- CATEGORY, BUDGET, SAVINGS_GOAL, TRANSACTION, ALERT tables are added with
-- their own modules per the ERD. Safe to re-run (idempotent).
-- ============================================================

-- ---------- consent enum (maps to USER "preferences/consent") ----------
do $$
begin
  create type public.spending_records_consent as enum ('unset', 'granted', 'denied', 'withdrawn');
exception
  when duplicate_object then null;
end;
$$;

-- ---------- profiles : ERD USER entity (Module 1) ----------
-- USR_Email / USR_Password are handled by Supabase Auth (auth.users).
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  full_name text,                 -- USR_FirstName + USR_LastName (single field)
  avatar_url text,
  monthly_allowance numeric(12, 2),                                          -- USR_MonthlyAllowance
  university text not null default 'UMS Kota Kinabalu',        -- USR_University
  year_of_study text,                                                        -- USR_YearOfStudy
  income_source text,                                                        -- USR_IncomeSource
  financial_status text,                                                     -- USR_FinancialStatus
  coaching_style text,                                                       -- USR_CoachingStyle
  onboarding_completed boolean not null default false,
  spending_records_consent public.spending_records_consent not null default 'unset',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Module 1 redesign: extend the financial profile (safe to re-run on existing DBs).
alter table public.profiles add column if not exists university text not null default 'UMS Kota Kinabalu';
alter table public.profiles alter column university set default 'UMS Kota Kinabalu';
alter table public.profiles add column if not exists year_of_study text;
alter table public.profiles add column if not exists income_source text;
alter table public.profiles add column if not exists financial_status text;
alter table public.profiles add column if not exists coaching_style text;
alter table public.profiles drop column if exists financial_goal;          -- replaced by SAVINGS_GOAL module

alter table public.profiles enable row level security;

grant usage on schema public to anon, authenticated;
grant select, insert, update on table public.profiles to authenticated;

drop policy if exists "Users can read own profile" on public.profiles;
create policy "Users can read own profile" on public.profiles
  for select to authenticated using (auth.uid() = id);

drop policy if exists "Users can insert own profile" on public.profiles;
create policy "Users can insert own profile" on public.profiles
  for insert to authenticated with check (auth.uid() = id);

drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile" on public.profiles
  for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

-- ---------- auto-create a profile when a new user signs up ----------
create schema if not exists private;

create or replace function private.handle_new_user_profile()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name, avatar_url)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    new.raw_user_meta_data ->> 'avatar_url'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_create_profile on auth.users;
create trigger on_auth_user_created_create_profile
  after insert on auth.users
  for each row execute function private.handle_new_user_profile();

-- ---------- account-collision lookup (pattern #2: "use your original method") ----------
-- Returns which auth providers an email is registered under (e.g. {email}, {google},
-- {email,google}) so the app can prompt the user to sign in with their original method
-- instead of silently creating/linking a second identity.
-- SECURITY DEFINER so it can read the auth schema; callable before login (anon).
-- Trade-off: this reveals whether an email is registered (email enumeration). Acceptable
-- for this UX; add rate-limiting / captcha before a real public launch.
create or replace function public.auth_methods_for_email(p_email text)
returns text[]
language sql
security definer
set search_path = ''
as $$
  select coalesce(array_agg(distinct i.provider), '{}')
  from auth.identities i
  join auth.users u on u.id = i.user_id
  where lower(u.email) = lower(p_email);
$$;

grant execute on function public.auth_methods_for_email(text) to anon, authenticated;

-- ============================================================
-- CATEGORY / USER_CATEGORIES / BUDGET / SAVINGS_GOAL  (ERD entities)
-- Wired through the Edit Profile screen. Safe to re-run.
-- ============================================================

-- ---------- categories : defaults plus user-owned custom expense categories ----------
create table if not exists public.categories (
  id bigint generated always as identity primary key,
  name text not null,                  -- CATEGORY Name
  type text not null default 'expense' check (type in ('expense', 'income')), -- CATEGORY Type
  icon text,                           -- CATEGORY Icon (MaterialIcons name)
  user_id uuid references auth.users (id) on delete cascade,
  color text
);

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
  on public.categories (lower(name)) where user_id is null;
create unique index if not exists categories_user_name_unique
  on public.categories (user_id, lower(name)) where user_id is not null;

alter table public.categories enable row level security;
grant select, insert, update, delete on table public.categories to authenticated;
grant usage, select on sequence public.categories_id_seq to authenticated;

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

insert into public.categories (name, type, icon, color) values
  ('Food', 'expense', 'restaurant', '#E45C3A'),
  ('Transport', 'expense', 'directions-car', '#3C78D8'),
  ('Rent', 'expense', 'home', '#7E57C2'),
  ('Entertainment', 'expense', 'movie', '#D64C7F'),
  ('Education', 'expense', 'school', '#00897B'),
  ('Others', 'expense', 'more-horiz', '#6B7280')
on conflict do nothing;

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

-- ---------- user_categories : which categories each user tracks (M:N) ----------
create table if not exists public.user_categories (
  user_id uuid not null references auth.users (id) on delete cascade,
  category_id bigint not null references public.categories (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, category_id)
);

alter table public.user_categories enable row level security;
grant select, insert, delete on table public.user_categories to authenticated;

drop policy if exists "Users manage own tracked categories" on public.user_categories;
create policy "Users manage own tracked categories" on public.user_categories
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- monthly_budgets : one overall limit per user/month ----------
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

alter table public.monthly_budgets enable row level security;
grant select, insert, update, delete on table public.monthly_budgets to authenticated;

drop policy if exists "Users can read own monthly budgets" on public.monthly_budgets;
create policy "Users can read own monthly budgets" on public.monthly_budgets
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own monthly budgets" on public.monthly_budgets;
create policy "Users can create own monthly budgets" on public.monthly_budgets
  for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update own monthly budgets" on public.monthly_budgets;
create policy "Users can update own monthly budgets" on public.monthly_budgets
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete own monthly budgets" on public.monthly_budgets;
create policy "Users can delete own monthly budgets" on public.monthly_budgets
  for delete to authenticated using ((select auth.uid()) = user_id);

-- ---------- budgets : per-category monthly limits ----------
create table if not exists public.budgets (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  category_id bigint not null references public.categories (id) on delete cascade,
  amount numeric(12, 2) not null check (amount > 0),
  month date not null,                 -- first day of the budget month
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, category_id, month),
  constraint budgets_month_first_day_check
    check (month = date_trunc('month', month)::date),
  constraint budgets_monthly_budget_fkey
    foreign key (user_id, month)
    references public.monthly_budgets (user_id, month) on delete cascade
);

-- Upgrade legacy category-limit rows before adding their parent relationship.
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

alter table public.budgets enable row level security;
grant select, insert, update, delete on table public.budgets to authenticated;
grant usage, select on sequence public.budgets_id_seq to authenticated;

drop policy if exists "Users manage own budgets" on public.budgets;
drop policy if exists "Users can read own category limits" on public.budgets;
create policy "Users can read own category limits" on public.budgets
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own category limits" on public.budgets;
create policy "Users can create own category limits" on public.budgets
  for insert to authenticated
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.categories c
      where c.id = category_id and c.type = 'expense'
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
      where c.id = category_id and c.type = 'expense'
        and (c.user_id is null or c.user_id = (select auth.uid()))
    )
  );

drop policy if exists "Users can delete own category limits" on public.budgets;
create policy "Users can delete own category limits" on public.budgets
  for delete to authenticated using ((select auth.uid()) = user_id);

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
    select mb.limit_amount into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new.user_id and mb.month = new.month;

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0) into allocated
    from public.budgets b
    where b.user_id = new.user_id and b.month = new.month
      and b.id <> coalesce(new.id, -1);

    if allocated + new.amount > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0) into allocated
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

-- ---------- savings_goals : ERD SAVINGS_GOAL (many per user) ----------
create table if not exists public.savings_goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,                          -- SAVINGS_GOAL Name
  target_amount numeric(12, 2) not null,       -- TargetAmount
  current_amount numeric(12, 2) not null default 0, -- CurrentAmount
  deadline date,                               -- Deadline
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.savings_goals enable row level security;
grant select, insert, update, delete on table public.savings_goals to authenticated;

drop policy if exists "Users manage own savings goals" on public.savings_goals;
create policy "Users manage own savings goals" on public.savings_goals
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Complete Savings Goal Management (FRSG-01 through FRSG-05).
-- current_amount is a database-maintained cache of normalized contribution rows.

alter table public.savings_goals
  add column if not exists deadline date;

alter table public.savings_goals drop constraint if exists savings_goals_name_not_blank;
alter table public.savings_goals drop constraint if exists savings_goals_target_positive;
alter table public.savings_goals drop constraint if exists savings_goals_current_nonnegative;
alter table public.savings_goals drop constraint if exists savings_goals_target_covers_current;

alter table public.savings_goals
  add constraint savings_goals_name_not_blank
    check (char_length(btrim(name)) between 1 and 100) not valid,
  add constraint savings_goals_target_positive
    check (target_amount > 0) not valid,
  add constraint savings_goals_current_nonnegative
    check (current_amount >= 0) not valid,
  add constraint savings_goals_target_covers_current
    check (target_amount >= current_amount) not valid;

revoke update on table public.savings_goals from authenticated;
grant select, insert, delete on table public.savings_goals to authenticated;
grant update (name, target_amount, deadline, updated_at)
  on table public.savings_goals to authenticated;

drop policy if exists "Users manage own savings goals" on public.savings_goals;
drop policy if exists "Users can read own savings goals" on public.savings_goals;
drop policy if exists "Users can add own savings goals" on public.savings_goals;
drop policy if exists "Users can update own savings goals" on public.savings_goals;
drop policy if exists "Users can delete own savings goals" on public.savings_goals;

create policy "Users can read own savings goals" on public.savings_goals
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can add own savings goals" on public.savings_goals
  for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update own savings goals" on public.savings_goals
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete own savings goals" on public.savings_goals
  for delete to authenticated
  using ((select auth.uid()) = user_id);

create index if not exists savings_goals_user_id_idx
  on public.savings_goals (user_id);

create table if not exists public.savings_contributions (
  id bigint generated always as identity primary key,
  goal_id uuid not null references public.savings_goals (id) on delete cascade,
  amount numeric(12, 2) not null check (amount > 0),
  contributed_on date not null default current_date check (contributed_on <= current_date),
  note text check (note is null or char_length(note) <= 200),
  created_at timestamptz not null default now()
);

create index if not exists savings_contributions_history_idx
  on public.savings_contributions (goal_id, contributed_on desc, created_at desc);

-- Convert any balance created by the earlier basic screen into auditable history.
insert into public.savings_contributions (goal_id, amount, contributed_on, note)
select g.id, g.current_amount, g.created_at::date, 'Opening balance'
from public.savings_goals as g
where g.current_amount > 0
  and not exists (
    select 1
    from public.savings_contributions as c
    where c.goal_id = g.id
  );

create or replace function private.refresh_savings_goal_amount()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_goal_id uuid;
  authenticated_user_id uuid := (select auth.uid());
  goal_owner_id uuid;
  goal_target numeric(12, 2);
  contribution_total numeric(12, 2);
begin
  affected_goal_id := case when tg_op = 'DELETE' then old.goal_id else new.goal_id end;

  select g.user_id, g.target_amount
  into goal_owner_id, goal_target
  from public.savings_goals as g
  where g.id = affected_goal_id
  for update;

  -- A parent can already be gone during ON DELETE CASCADE.
  if not found then
    return null;
  end if;

  if authenticated_user_id is not null and goal_owner_id <> authenticated_user_id then
    raise exception 'Savings goal ownership check failed.';
  end if;

  select coalesce(sum(c.amount), 0)
  into contribution_total
  from public.savings_contributions as c
  where c.goal_id = affected_goal_id;

  if contribution_total > goal_target then
    raise exception 'Contribution exceeds the remaining savings target.';
  end if;

  update public.savings_goals
  set current_amount = contribution_total,
      updated_at = now()
  where id = affected_goal_id;

  return null;
end;
$$;

revoke all on function private.refresh_savings_goal_amount()
  from public, anon, authenticated;

drop trigger if exists refresh_savings_goal_amount on public.savings_contributions;
create trigger refresh_savings_goal_amount
  after insert or delete on public.savings_contributions
  for each row execute function private.refresh_savings_goal_amount();

alter table public.savings_contributions enable row level security;

revoke all on table public.savings_contributions from anon;
grant select, insert, delete on table public.savings_contributions to authenticated;
grant usage, select on sequence public.savings_contributions_id_seq to authenticated;

drop policy if exists "Users can read own savings contributions" on public.savings_contributions;
drop policy if exists "Users can add own savings contributions" on public.savings_contributions;
drop policy if exists "Users can delete own savings contributions" on public.savings_contributions;

create policy "Users can read own savings contributions"
on public.savings_contributions
for select
to authenticated
using (
  exists (
    select 1
    from public.savings_goals as g
    where g.id = savings_contributions.goal_id
      and g.user_id = (select auth.uid())
  )
);

create policy "Users can add own savings contributions"
on public.savings_contributions
for insert
to authenticated
with check (
  exists (
    select 1
    from public.savings_goals as g
    where g.id = savings_contributions.goal_id
      and g.user_id = (select auth.uid())
  )
);

create policy "Users can delete own savings contributions"
on public.savings_contributions
for delete
to authenticated
using (
  exists (
    select 1
    from public.savings_goals as g
    where g.id = savings_contributions.goal_id
      and g.user_id = (select auth.uid())
  )
);

+-- Transaction and Receipt Capture Management
-- ERD-aligned single transaction record with a private receipt image path.

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



-- ---------- reports : ERD REPORT (immutable log of generated reports, many per user) ----------
-- Metadata only. The live Reports screen calculates analytics from current owner-scoped
-- source records and writes one history row only after an explicit Generate Report action.
create table if not exists public.reports (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  period text not null,                            -- REPORT_Period (e.g. '2026-06')
  type text not null,                              -- constrained report selection type
  generated_at timestamptz not null default now()  -- REPORT_GeneratedDate
);

alter table public.reports drop constraint if exists reports_period_length_check;
alter table public.reports
  add constraint reports_period_length_check
  check (char_length(btrim(period)) between 7 and 50) not valid;

alter table public.reports drop constraint if exists reports_type_check;
alter table public.reports
  add constraint reports_type_check
  check (type in (
    'monthly',
    'monthly_category',
    'multi_month',
    'multi_month_category',
    'custom',
    'custom_category'
  )) not valid;

create index if not exists reports_user_generated_idx
  on public.reports (user_id, generated_at desc);

alter table public.reports enable row level security;
revoke all on table public.reports from anon;
grant select, insert on table public.reports to authenticated;
revoke update, delete on table public.reports from authenticated;
grant usage, select on sequence public.reports_id_seq to authenticated;

drop policy if exists "Users manage own reports" on public.reports;
drop policy if exists "Users can read own reports" on public.reports;
create policy "Users can read own reports" on public.reports
  for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own reports" on public.reports;
create policy "Users can create own reports" on public.reports
  for insert to authenticated with check ((select auth.uid()) = user_id);

-- ============================================================
-- Storage bucket for profile avatars (public read, owner write)
-- Files are stored at  <user_id>/avatar.<ext>
-- ============================================================
insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', true)
on conflict (id) do nothing;

drop policy if exists "Avatar images are publicly readable" on storage.objects;
create policy "Avatar images are publicly readable" on storage.objects
  for select using (bucket_id = 'avatars');

drop policy if exists "Users can upload own avatar" on storage.objects;
create policy "Users can upload own avatar" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "Users can update own avatar" on storage.objects;
create policy "Users can update own avatar" on storage.objects
  for update to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "Users can delete own avatar" on storage.objects;
create policy "Users can delete own avatar" on storage.objects
  for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

-- ============================================================
-- Alert and Reminder Management (FRAR-01 through FRAR-04)
-- ============================================================
create extension if not exists pg_net with schema extensions;
create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists supabase_vault with schema vault;

create schema if not exists private;

create table if not exists public.notification_preferences (
  user_id uuid primary key references auth.users (id) on delete cascade,
  budget_enabled boolean not null default true,
  savings_enabled boolean not null default true,
  savings_lead_days smallint not null default 7,
  savings_reminder_time time not null default '09:00',
  savings_milestones_enabled boolean not null default true,
  spending_enabled boolean not null default true,
  spending_frequency text not null default 'weekly',
  spending_weekday smallint,
  spending_reminder_time time not null default '20:00',
  bills_enabled boolean not null default true,
  default_bill_lead_days smallint not null default 3,
  default_bill_reminder_time time not null default '09:00',
  timezone text not null default 'Asia/Kuala_Lumpur',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint notification_preferences_savings_lead_days_check
    check (savings_lead_days between 0 and 365),
  constraint notification_preferences_spending_frequency_check
    check (spending_frequency in ('daily', 'weekly')),
  constraint notification_preferences_spending_weekday_check
    check (spending_weekday is null or spending_weekday between 0 and 6),
  constraint notification_preferences_bill_lead_days_check
    check (default_bill_lead_days between 0 and 365),
  constraint notification_preferences_timezone_check
    check (char_length(btrim(timezone)) between 1 and 100)
);

create table if not exists public.reminders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  type text not null default 'bill',
  title text not null,
  amount numeric(12, 2),
  due_at timestamptz not null,
  lead_days smallint not null default 3,
  recurrence text not null default 'none',
  recurrence_anchor_day smallint not null,
  enabled boolean not null default true,
  next_trigger_at timestamptz,
  last_triggered_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint reminders_type_check check (type = 'bill'),
  constraint reminders_title_check check (char_length(btrim(title)) between 1 and 100),
  constraint reminders_amount_check check (amount is null or amount > 0),
  constraint reminders_lead_days_check check (lead_days between 0 and 365),
  constraint reminders_recurrence_check
    check (recurrence in ('none', 'weekly', 'monthly', 'yearly')),
  constraint reminders_recurrence_anchor_day_check
    check (recurrence_anchor_day between 1 and 31)
);

create table if not exists public.alerts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  type text not null,
  kind text not null default 'alert',
  title text not null,
  message text not null,
  budget_id uuid references public.monthly_budgets (id) on delete set null,
  category_limit_id bigint references public.budgets (id) on delete set null,
  savings_goal_id uuid references public.savings_goals (id) on delete set null,
  reminder_id uuid references public.reminders (id) on delete set null,
  source_data jsonb not null default '{}'::jsonb,
  dedupe_key text not null,
  scheduled_for timestamptz,
  delivered_at timestamptz,
  read_at timestamptz,
  dismissed_at timestamptz,
  delivery_status text not null default 'pending',
  delivery_error text,
  delivery_attempt_count smallint not null default 0,
  delivery_claimed_at timestamptz,
  next_delivery_attempt_at timestamptz,
  delivery_receipts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint alerts_type_check check (
    type in (
      'budget_warning',
      'budget_exceeded',
      'savings_deadline',
      'savings_milestone',
      'spending_reminder',
      'bill_reminder'
    )
  ),
  constraint alerts_kind_check check (kind in ('alert', 'insight')),
  constraint alerts_title_check check (char_length(btrim(title)) between 1 and 100),
  constraint alerts_message_check check (char_length(btrim(message)) between 1 and 500),
  constraint alerts_dedupe_key_check check (char_length(btrim(dedupe_key)) between 1 and 200),
  constraint alerts_delivery_status_check check (
    delivery_status in (
      'pending',
      'sending',
      'sent',
      'delivered',
      'partially_delivered',
      'retryable',
      'failed',
      'no_active_device'
    )
  ),
  constraint alerts_delivery_error_check
    check (delivery_error is null or char_length(delivery_error) <= 1000),
  constraint alerts_delivery_attempt_count_check
    check (delivery_attempt_count between 0 and 100),
  unique (user_id, dedupe_key)
);

create table if not exists public.user_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  expo_push_token text not null unique,
  platform text not null,
  device_name text,
  active boolean not null default true,
  last_seen_at timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_devices_token_check
    check (char_length(btrim(expo_push_token)) between 20 and 255),
  constraint user_devices_platform_check check (platform in ('android', 'ios')),
  constraint user_devices_device_name_check
    check (device_name is null or char_length(device_name) <= 100),
  constraint user_devices_last_error_check
    check (last_error is null or char_length(last_error) <= 1000)
);

create index if not exists notification_preferences_user_updated_idx
  on public.notification_preferences (user_id, updated_at desc);
create index if not exists reminders_user_due_idx
  on public.reminders (user_id, due_at, created_at desc);
create index if not exists reminders_due_idx
  on public.reminders (next_trigger_at)
  where enabled = true and next_trigger_at is not null;
create index if not exists alerts_inbox_idx
  on public.alerts (user_id, created_at desc)
  where dismissed_at is null;
create index if not exists alerts_unread_idx
  on public.alerts (user_id, created_at desc)
  where read_at is null and dismissed_at is null;
create index if not exists alerts_delivery_retry_idx
  on public.alerts (next_delivery_attempt_at, created_at)
  where delivery_status in ('pending', 'retryable', 'sent');
create index if not exists alerts_budget_source_idx
  on public.alerts (budget_id, category_limit_id)
  where budget_id is not null or category_limit_id is not null;
create index if not exists alerts_savings_source_idx
  on public.alerts (savings_goal_id)
  where savings_goal_id is not null;
create index if not exists alerts_reminder_source_idx
  on public.alerts (reminder_id)
  where reminder_id is not null;
create index if not exists user_devices_active_idx
  on public.user_devices (user_id, last_seen_at desc)
  where active = true;

create or replace function private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function private.refresh_reminder_schedule()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.title = btrim(new.title);
  if new.recurrence_anchor_day is null then
    new.recurrence_anchor_day = extract(day from new.due_at)::smallint;
  end if;
  if new.enabled then
    new.next_trigger_at = new.due_at - make_interval(days => new.lead_days);
  else
    new.next_trigger_at = null;
  end if;
  return new;
end;
$$;

drop trigger if exists notification_preferences_set_updated_at on public.notification_preferences;
create trigger notification_preferences_set_updated_at
before update on public.notification_preferences
for each row execute function private.set_updated_at();

drop trigger if exists reminders_refresh_schedule on public.reminders;
create trigger reminders_refresh_schedule
before insert or update of title, due_at, lead_days, recurrence_anchor_day, enabled on public.reminders
for each row execute function private.refresh_reminder_schedule();

drop trigger if exists reminders_set_updated_at on public.reminders;
create trigger reminders_set_updated_at
before update on public.reminders
for each row execute function private.set_updated_at();

drop trigger if exists user_devices_set_updated_at on public.user_devices;
create trigger user_devices_set_updated_at
before update on public.user_devices
for each row execute function private.set_updated_at();

create or replace function public.reassign_user_device(
  p_user_id uuid,
  p_expo_push_token text,
  p_platform text,
  p_device_name text default null
)
returns public.user_devices
language plpgsql
security definer
set search_path = ''
as $$
declare
  registered_device public.user_devices;
begin
  insert into public.user_devices (
    user_id,
    expo_push_token,
    platform,
    device_name,
    active,
    last_seen_at,
    last_error
  )
  values (
    p_user_id,
    btrim(p_expo_push_token),
    p_platform,
    nullif(btrim(p_device_name), ''),
    true,
    now(),
    null
  )
  on conflict (expo_push_token) do update
  set user_id = excluded.user_id,
      platform = excluded.platform,
      device_name = excluded.device_name,
      active = true,
      last_seen_at = now(),
      last_error = null
  returning * into registered_device;

  return registered_device;
end;
$$;

create or replace function public.deactivate_user_device(
  p_user_id uuid,
  p_expo_push_token text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_count integer;
begin
  update public.user_devices
  set active = false,
      updated_at = now()
  where user_id = p_user_id
    and expo_push_token = p_expo_push_token;

  get diagnostics affected_count = row_count;
  return affected_count > 0;
end;
$$;

create or replace function public.claim_alert_delivery(p_alert_id uuid)
returns setof public.alerts
language sql
security definer
set search_path = ''
as $$
  update public.alerts
  set delivery_status = 'sending',
      delivery_claimed_at = now(),
      delivery_attempt_count = delivery_attempt_count + 1,
      next_delivery_attempt_at = null
  where id = p_alert_id
    and (
      delivery_status in ('pending', 'retryable')
      or (
        delivery_status = 'sending'
        and delivery_claimed_at < now() - interval '5 minutes'
      )
    )
    and (next_delivery_attempt_at is null or next_delivery_attempt_at <= now())
  returning *;
$$;

create or replace function public.claim_bill_reminder_occurrence(
  p_reminder_id uuid,
  p_expected_trigger_at timestamptz,
  p_next_due_at timestamptz,
  p_title text,
  p_message text,
  p_dedupe_key text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  claimed_reminder public.reminders;
  claimed_alert_id uuid;
begin
  select reminder.* into claimed_reminder
  from public.reminders as reminder
  where reminder.id = p_reminder_id
    and reminder.enabled = true
    and reminder.next_trigger_at = p_expected_trigger_at
    and reminder.next_trigger_at <= now()
    and exists (
      select 1
      from public.notification_preferences as preference
      where preference.user_id = reminder.user_id
        and preference.bills_enabled = true
    )
  for update;

  if not found then
    return null;
  end if;

  insert into public.alerts (
    user_id,
    type,
    kind,
    title,
    message,
    reminder_id,
    dedupe_key,
    scheduled_for
  )
  values (
    claimed_reminder.user_id,
    'bill_reminder',
    'alert',
    p_title,
    p_message,
    claimed_reminder.id,
    p_dedupe_key,
    p_expected_trigger_at
  )
  on conflict (user_id, dedupe_key) do nothing
  returning id into claimed_alert_id;

  if claimed_alert_id is null then
    select id into claimed_alert_id
    from public.alerts
    where user_id = claimed_reminder.user_id
      and dedupe_key = p_dedupe_key;
  end if;

  if claimed_reminder.recurrence = 'none' then
    update public.reminders
    set enabled = false,
        next_trigger_at = null,
        last_triggered_at = p_expected_trigger_at
    where id = claimed_reminder.id;
  else
    if p_next_due_at is null then
      raise exception 'A recurring reminder requires its next due date.';
    end if;
    update public.reminders
    set due_at = p_next_due_at,
        last_triggered_at = p_expected_trigger_at
    where id = claimed_reminder.id;
  end if;

  return claimed_alert_id;
end;
$$;

revoke all on function public.reassign_user_device(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.deactivate_user_device(uuid, text) from public, anon, authenticated;
revoke all on function public.claim_alert_delivery(uuid) from public, anon, authenticated;
revoke all on function public.claim_bill_reminder_occurrence(uuid, timestamptz, timestamptz, text, text, text) from public, anon, authenticated;
grant execute on function public.reassign_user_device(uuid, text, text, text) to service_role;
grant execute on function public.deactivate_user_device(uuid, text) to service_role;
grant execute on function public.claim_alert_delivery(uuid) to service_role;
grant execute on function public.claim_bill_reminder_occurrence(uuid, timestamptz, timestamptz, text, text, text) to service_role;

create or replace function private.notify_inserted_alert()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  webhook_url text;
  webhook_secret text;
begin
  select decrypted_secret into webhook_url
  from vault.decrypted_secrets
  where name = 'alert_webhook_url'
  limit 1;

  select decrypted_secret into webhook_secret
  from vault.decrypted_secrets
  where name = 'alert_webhook_secret'
  limit 1;

  if webhook_url is null or webhook_secret is null then
    return new;
  end if;

  perform net.http_post(
    url := webhook_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-fincoach-webhook-secret', webhook_secret
    ),
    body := jsonb_build_object('alertId', new.id),
    timeout_milliseconds := 5000
  );

  return new;
exception
  when others then
    raise warning 'Alert delivery webhook could not be queued (SQLSTATE %).', sqlstate;
    return new;
end;
$$;

revoke all on function private.notify_inserted_alert() from public, anon, authenticated;

drop trigger if exists deliver_inserted_alert on public.alerts;
create trigger deliver_inserted_alert
after insert on public.alerts
for each row execute function private.notify_inserted_alert();

alter table public.notification_preferences enable row level security;
alter table public.reminders enable row level security;
alter table public.alerts enable row level security;
alter table public.user_devices enable row level security;

drop policy if exists "Users can read own notification preferences" on public.notification_preferences;
drop policy if exists "Users can add own notification preferences" on public.notification_preferences;
drop policy if exists "Users can update own notification preferences" on public.notification_preferences;
create policy "Users can read own notification preferences"
on public.notification_preferences for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add own notification preferences"
on public.notification_preferences for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update own notification preferences"
on public.notification_preferences for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "Users can read own reminders" on public.reminders;
drop policy if exists "Users can add own reminders" on public.reminders;
drop policy if exists "Users can update own reminders" on public.reminders;
drop policy if exists "Users can delete own reminders" on public.reminders;
create policy "Users can read own reminders"
on public.reminders for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add own reminders"
on public.reminders for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update own reminders"
on public.reminders for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
create policy "Users can delete own reminders"
on public.reminders for delete to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "Users can read own alerts" on public.alerts;
drop policy if exists "Users can add own alerts" on public.alerts;
drop policy if exists "Users can update own alerts" on public.alerts;
create policy "Users can read own alerts"
on public.alerts for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add own alerts"
on public.alerts for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update own alerts"
on public.alerts for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

revoke all on table public.notification_preferences from anon;
revoke all on table public.reminders from anon;
revoke all on table public.alerts from anon;
revoke all on table public.user_devices from anon, authenticated;

grant select, insert, update on table public.notification_preferences to authenticated;
grant select, insert, update, delete on table public.reminders to authenticated;
grant select on table public.alerts to authenticated;
grant insert (
  user_id,
  type,
  kind,
  title,
  message,
  budget_id,
  category_limit_id,
  savings_goal_id,
  reminder_id,
  source_data,
  dedupe_key,
  scheduled_for
) on table public.alerts to authenticated;
revoke update on table public.alerts from authenticated;
grant update (read_at, dismissed_at) on table public.alerts to authenticated;

grant select, insert, update, delete on table public.notification_preferences to service_role;
grant select, insert, update, delete on table public.reminders to service_role;
grant select, insert, update, delete on table public.alerts to service_role;
grant select, insert, update, delete on table public.user_devices to service_role;
-- ============================================================
-- Financial Data Export and Backup
-- Logical ERD: USER 1:N DATA_EXPORT 1:N EXPORT_CONTENT; USER 1:N BACKUP.
-- ============================================================

alter table public.profiles
  add column if not exists auto_backup_enabled boolean not null default true;

create table if not exists public.data_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  format text not null check (format in ('csv', 'pdf')),
  status text not null check (status in ('pending', 'processing', 'completed', 'failed')),
  file_name text not null check (char_length(btrim(file_name)) between 1 and 255),
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  date_from date not null,
  date_to date not null,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint data_exports_date_range_check check (date_from <= date_to)
);

create table if not exists public.export_contents (
  export_id uuid not null references public.data_exports (id) on delete cascade,
  content_type text not null
    check (content_type in ('transaction', 'budget', 'savings', 'report')),
  primary key (export_id, content_type)
);

create table if not exists public.backups (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  backup_type text not null check (backup_type in ('manual', 'automatic')),
  status text not null check (status in ('pending', 'processing', 'completed', 'failed')),
  file_name text not null check (char_length(btrim(file_name)) between 1 and 255),
  storage_path text check (
    storage_path is null or char_length(storage_path) between 1 and 512
  ),
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  checksum_sha256 text check (
    checksum_sha256 is null or checksum_sha256 ~ '^[a-f0-9]{64}$'
  ),
  schema_version integer not null default 1 check (schema_version > 0),
  last_restore_status text check (
    last_restore_status is null
    or last_restore_status in ('pending', 'processing', 'completed', 'failed')
  ),
  last_restored_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists data_exports_user_created_idx
  on public.data_exports (user_id, created_at desc);
create index if not exists data_exports_user_period_idx
  on public.data_exports (user_id, date_from, date_to);
create index if not exists backups_user_created_idx
  on public.backups (user_id, created_at desc);
create index if not exists backups_user_automatic_idx
  on public.backups (user_id, backup_type, status, completed_at desc);

alter table public.data_exports enable row level security;
alter table public.export_contents enable row level security;
alter table public.backups enable row level security;

revoke all on table public.data_exports, public.export_contents, public.backups from anon;
grant select, insert, update, delete
  on table public.data_exports, public.export_contents, public.backups
  to authenticated;

drop policy if exists "Users can read own data exports" on public.data_exports;
create policy "Users can read own data exports" on public.data_exports
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can create own data exports" on public.data_exports;
create policy "Users can create own data exports" on public.data_exports
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Users can update own data exports" on public.data_exports;
create policy "Users can update own data exports" on public.data_exports
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can delete own data exports" on public.data_exports;
create policy "Users can delete own data exports" on public.data_exports
  for delete to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "Users can read own export contents" on public.export_contents;
create policy "Users can read own export contents" on public.export_contents
  for select to authenticated using (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );
drop policy if exists "Users can create own export contents" on public.export_contents;
create policy "Users can create own export contents" on public.export_contents
  for insert to authenticated with check (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );
drop policy if exists "Users can update own export contents" on public.export_contents;
create policy "Users can update own export contents" on public.export_contents
  for update to authenticated
  using (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );
drop policy if exists "Users can delete own export contents" on public.export_contents;
create policy "Users can delete own export contents" on public.export_contents
  for delete to authenticated using (
    exists (
      select 1 from public.data_exports e
      where e.id = export_id and e.user_id = (select auth.uid())
    )
  );

drop policy if exists "Users can read own backups" on public.backups;
create policy "Users can read own backups" on public.backups
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can create own backups" on public.backups;
create policy "Users can create own backups" on public.backups
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Users can update own backups" on public.backups;
create policy "Users can update own backups" on public.backups
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can delete own backups" on public.backups;
create policy "Users can delete own backups" on public.backups
  for delete to authenticated using ((select auth.uid()) = user_id);

insert into storage.buckets (
  id, name, public, file_size_limit, allowed_mime_types
)
values (
  'financial-backups',
  'financial-backups',
  false,
  10485760,
  array['application/json']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read own financial backups" on storage.objects;
create policy "Users can read own financial backups" on storage.objects
  for select to authenticated using (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can upload own financial backups" on storage.objects;
create policy "Users can upload own financial backups" on storage.objects
  for insert to authenticated with check (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can update own financial backups" on storage.objects;
create policy "Users can update own financial backups" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  )
  with check (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
drop policy if exists "Users can delete own financial backups" on storage.objects;
create policy "Users can delete own financial backups" on storage.objects
  for delete to authenticated using (
    bucket_id = 'financial-backups'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

create or replace function public.restore_financial_backup_v1(
  payload jsonb,
  backup_record_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  owner_id uuid := (select auth.uid());
  profile_data jsonb := payload -> 'data' -> 'profile';
begin
  if owner_id is null then raise exception 'Authentication required.'; end if;
  if coalesce((payload ->> 'schemaVersion')::integer, 0) <> 1 then
    raise exception 'Unsupported backup schema.';
  end if;
  if payload ->> 'userId' <> owner_id::text then raise exception 'Backup owner mismatch.'; end if;
  if not exists (
    select 1 from public.backups b
    where b.id = backup_record_id and b.user_id = owner_id and b.status = 'completed'
  ) then raise exception 'Completed backup not found.'; end if;

  update public.backups set last_restore_status = 'processing'
  where id = backup_record_id and user_id = owner_id;

  delete from public.alerts where user_id = owner_id;
  delete from public.reminders where user_id = owner_id;
  delete from public.notification_preferences where user_id = owner_id;
  delete from public.transactions where user_id = owner_id;
  delete from public.budgets where user_id = owner_id;
  delete from public.monthly_budgets where user_id = owner_id;
  delete from public.savings_contributions
  where goal_id in (select id from public.savings_goals where user_id = owner_id);
  delete from public.savings_goals where user_id = owner_id;
  delete from public.reports where user_id = owner_id;
  delete from public.categories where user_id = owner_id;

  if profile_data is not null and profile_data <> 'null'::jsonb then
    update public.profiles
    set email = coalesce(profile_data ->> 'email', email),
        full_name = profile_data ->> 'full_name',
        avatar_url = profile_data ->> 'avatar_url',
        monthly_allowance = nullif(profile_data ->> 'monthly_allowance', '')::numeric,
        university = coalesce(profile_data ->> 'university', university),
        year_of_study = profile_data ->> 'year_of_study',
        income_source = profile_data ->> 'income_source',
        financial_status = profile_data ->> 'financial_status',
        coaching_style = profile_data ->> 'coaching_style',
        onboarding_completed = coalesce((profile_data ->> 'onboarding_completed')::boolean, onboarding_completed),
        spending_records_consent = coalesce(
          (profile_data ->> 'spending_records_consent')::public.spending_records_consent,
          spending_records_consent
        ),
        updated_at = now()
    where id = owner_id;
  end if;

  insert into public.categories (id, name, type, icon, user_id, color)
  overriding system value
  select id, name, type, icon, owner_id, color
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb))
    as x(id bigint, name text, type text, icon text, user_id uuid, color text);

  insert into public.monthly_budgets (id, user_id, month, limit_amount, created_at, updated_at)
  select id, owner_id, month, limit_amount, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb))
    as x(id uuid, user_id uuid, month date, limit_amount numeric, created_at timestamptz, updated_at timestamptz);

  insert into public.budgets (id, user_id, category_id, amount, month, created_at, updated_at)
  overriding system value
  select id, owner_id, category_id, amount, month, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb))
    as x(id bigint, user_id uuid, category_id bigint, amount numeric, month date, created_at timestamptz, updated_at timestamptz);

  insert into public.savings_goals (id, user_id, name, target_amount, current_amount, deadline, created_at, updated_at)
  select id, owner_id, name, target_amount, 0, deadline, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb))
    as x(id uuid, user_id uuid, name text, target_amount numeric, current_amount numeric, deadline date, created_at timestamptz, updated_at timestamptz);

  insert into public.savings_contributions (id, goal_id, amount, contributed_on, note, created_at)
  overriding system value
  select id, goal_id, amount, contributed_on, note, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb))
    as x(id bigint, goal_id uuid, amount numeric, contributed_on date, note text, created_at timestamptz);

  insert into public.transactions (
    id, user_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, created_at, updated_at
  )
  select id, owner_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb))
    as x(id uuid, user_id uuid, category_id bigint, amount numeric, transaction_date date,
      description text, source text, receipt_image_path text, created_at timestamptz, updated_at timestamptz);

  insert into public.reports (id, user_id, period, type, generated_at)
  overriding system value
  select id, owner_id, period, type, generated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb))
    as x(id bigint, user_id uuid, period text, type text, generated_at timestamptz);

  insert into public.notification_preferences (
    user_id, budget_enabled, savings_enabled, savings_lead_days, savings_reminder_time,
    savings_milestones_enabled, spending_enabled, spending_frequency, spending_weekday,
    spending_reminder_time, bills_enabled, default_bill_lead_days,
    default_bill_reminder_time, timezone, created_at, updated_at
  )
  select owner_id, budget_enabled, savings_enabled, savings_lead_days, savings_reminder_time,
    savings_milestones_enabled, spending_enabled, spending_frequency, spending_weekday,
    spending_reminder_time, bills_enabled, default_bill_lead_days,
    default_bill_reminder_time, timezone, created_at, updated_at
  from jsonb_to_record(coalesce(payload -> 'data' -> 'notificationPreferences', '{}'::jsonb))
    as x(user_id uuid, budget_enabled boolean, savings_enabled boolean, savings_lead_days smallint,
      savings_reminder_time time, savings_milestones_enabled boolean, spending_enabled boolean,
      spending_frequency text, spending_weekday smallint, spending_reminder_time time,
      bills_enabled boolean, default_bill_lead_days smallint, default_bill_reminder_time time,
      timezone text, created_at timestamptz, updated_at timestamptz)
  where payload -> 'data' -> 'notificationPreferences' is not null
    and payload -> 'data' -> 'notificationPreferences' <> 'null'::jsonb;

  insert into public.reminders (
    id, user_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at, created_at, updated_at
  )
  select id, owner_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb))
    as x(id uuid, user_id uuid, type text, title text, amount numeric, due_at timestamptz,
      lead_days smallint, recurrence text, recurrence_anchor_day smallint, enabled boolean,
      next_trigger_at timestamptz, last_triggered_at timestamptz, created_at timestamptz, updated_at timestamptz);

  insert into public.alerts (
    id, user_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for, delivered_at,
    read_at, dismissed_at, delivery_status, delivery_error, delivery_attempt_count,
    delivery_claimed_at, next_delivery_attempt_at, delivery_receipts, created_at
  )
  select id, owner_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for, delivered_at,
    read_at, dismissed_at, delivery_status, delivery_error, delivery_attempt_count,
    delivery_claimed_at, next_delivery_attempt_at, delivery_receipts, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
    as x(id uuid, user_id uuid, type text, kind text, title text, message text,
      budget_id uuid, category_limit_id bigint, savings_goal_id uuid, reminder_id uuid,
      source_data jsonb, dedupe_key text, scheduled_for timestamptz, delivered_at timestamptz,
      read_at timestamptz, dismissed_at timestamptz, delivery_status text, delivery_error text,
      delivery_attempt_count smallint, delivery_claimed_at timestamptz,
      next_delivery_attempt_at timestamptz, delivery_receipts jsonb, created_at timestamptz);

  perform setval(pg_get_serial_sequence('public.categories', 'id'),
    greatest(coalesce((select max(id) from public.categories), 1), 1), true);
  perform setval(pg_get_serial_sequence('public.budgets', 'id'),
    greatest(coalesce((select max(id) from public.budgets), 1), 1), true);
  perform setval(pg_get_serial_sequence('public.savings_contributions', 'id'),
    greatest(coalesce((select max(id) from public.savings_contributions), 1), 1), true);
  perform setval(pg_get_serial_sequence('public.reports', 'id'),
    greatest(coalesce((select max(id) from public.reports), 1), 1), true);

  update public.backups
  set last_restore_status = 'completed', last_restored_at = now()
  where id = backup_record_id and user_id = owner_id;

  return jsonb_build_object(
    'profile', case when profile_data is null or profile_data = 'null'::jsonb then 0 else 1 end,
    'customCategories', jsonb_array_length(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb)),
    'transactions', jsonb_array_length(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb)),
    'monthlyBudgets', jsonb_array_length(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb)),
    'categoryLimits', jsonb_array_length(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb)),
    'savingsGoals', jsonb_array_length(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb)),
    'savingsContributions', jsonb_array_length(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb)),
    'reports', jsonb_array_length(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb)),
    'notificationPreferences', case when payload -> 'data' -> 'notificationPreferences' is null
      or payload -> 'data' -> 'notificationPreferences' = 'null'::jsonb then 0 else 1 end,
    'reminders', jsonb_array_length(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb)),
    'alerts', jsonb_array_length(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
  );
end;
$$;

revoke execute on function public.restore_financial_backup_v1(jsonb, uuid) from public;
revoke execute on function public.restore_financial_backup_v1(jsonb, uuid) from anon;
grant execute on function public.restore_financial_backup_v1(jsonb, uuid) to authenticated;

-- ============================================================
-- AI Financial Coaching: shared RAG knowledge and chat history
-- ============================================================
create extension if not exists vector;

create table if not exists public.knowledge_documents (
  id bigint generated always as identity primary key,
  title text,
  content text not null,
  source text,
  embedding vector(1024) not null,
  page_number integer,
  chunk_index integer,
  content_hash text,
  created_at timestamptz not null default now(),
  constraint knowledge_documents_page_number_check check (page_number is null or page_number > 0),
  constraint knowledge_documents_chunk_index_check check (chunk_index is null or chunk_index >= 0)
);

alter table public.knowledge_documents add column if not exists page_number integer;
alter table public.knowledge_documents add column if not exists chunk_index integer;
alter table public.knowledge_documents add column if not exists content_hash text;
create unique index if not exists knowledge_documents_content_hash_idx
  on public.knowledge_documents (content_hash);
create index if not exists knowledge_documents_embedding_idx
  on public.knowledge_documents using hnsw (embedding vector_cosine_ops);

drop function if exists public.match_knowledge_documents(vector, integer);

create or replace function public.match_knowledge_documents(
  query_embedding vector(1024),
  match_count integer default 5
)
returns table (
  id bigint,
  title text,
  content text,
  source text,
  page_number integer,
  chunk_index integer,
  similarity double precision
)
language sql
stable
set search_path = pg_catalog, extensions, public
as $$
  select document.id, document.title, document.content, document.source,
    document.page_number, document.chunk_index,
    1 - (document.embedding <=> query_embedding) as similarity
  from public.knowledge_documents as document
  order by document.embedding <=> query_embedding
  limit greatest(1, least(match_count, 10));
$$;

alter table public.knowledge_documents enable row level security;
drop policy if exists "Authenticated users can read knowledge" on public.knowledge_documents;
revoke all on table public.knowledge_documents from anon, authenticated;
revoke select on table public.knowledge_documents from anon, authenticated;
grant select, insert, update, delete on table public.knowledge_documents to service_role;
grant usage, select on sequence public.knowledge_documents_id_seq to service_role;
revoke execute on function public.match_knowledge_documents(vector, integer) from public;
revoke execute on function public.match_knowledge_documents(vector, integer) from anon, authenticated;
grant execute on function public.match_knowledge_documents(vector, integer) to service_role;

create table if not exists public.coaching_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz not null default now(),
  constraint coaching_sessions_title_check check (char_length(btrim(title)) between 1 and 80)
);

create table if not exists public.coaching_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.coaching_sessions (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null,
  content text not null,
  reply_to_message_id uuid references public.coaching_messages (id) on delete set null,
  status text not null default 'completed',
  error_code text,
  model text,
  prompt_tokens integer,
  completion_tokens integer,
  created_at timestamptz not null default now(),
  constraint coaching_messages_role_check check (role in ('user', 'assistant')),
  constraint coaching_messages_status_check check (status in ('completed', 'failed')),
  constraint coaching_messages_content_check check (char_length(btrim(content)) between 1 and 8000),
  constraint coaching_messages_reply_shape_check check (
    (role = 'user' and reply_to_message_id is null)
    or (role = 'assistant' and reply_to_message_id is not null)
  ),
  constraint coaching_messages_prompt_tokens_check check (prompt_tokens is null or prompt_tokens >= 0),
  constraint coaching_messages_completion_tokens_check check (completion_tokens is null or completion_tokens >= 0),
  unique (reply_to_message_id)
);

create table if not exists public.coaching_retrievals (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  assistant_message_id uuid not null references public.coaching_messages (id) on delete cascade,
  knowledge_document_id bigint references public.knowledge_documents (id) on delete set null,
  rank smallint not null,
  similarity double precision not null,
  title text,
  source text,
  created_at timestamptz not null default now(),
  constraint coaching_retrievals_rank_check check (rank between 1 and 10),
  constraint coaching_retrievals_similarity_check check (similarity between -1 and 1),
  unique (assistant_message_id, knowledge_document_id)
);

create index if not exists coaching_sessions_user_last_message_idx
  on public.coaching_sessions (user_id, last_message_at desc);
create index if not exists coaching_messages_session_created_idx
  on public.coaching_messages (session_id, created_at asc);
create index if not exists coaching_messages_user_created_idx
  on public.coaching_messages (user_id, created_at desc) where role = 'user';
create index if not exists coaching_retrievals_message_rank_idx
  on public.coaching_retrievals (assistant_message_id, rank asc);

alter table public.coaching_sessions enable row level security;
alter table public.coaching_messages enable row level security;
alter table public.coaching_retrievals enable row level security;
grant select, insert, update, delete on table public.coaching_sessions to authenticated;
grant select, insert on table public.coaching_messages to authenticated;
grant select on table public.coaching_retrievals to authenticated;
grant select, insert, update, delete on table public.coaching_sessions to service_role;
grant select, insert, update, delete on table public.coaching_messages to service_role;
grant select, insert, update, delete on table public.coaching_retrievals to service_role;
grant usage, select on sequence public.coaching_retrievals_id_seq to service_role;

drop policy if exists "Users can read own coaching sessions" on public.coaching_sessions;
create policy "Users can read own coaching sessions" on public.coaching_sessions
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can create own coaching sessions" on public.coaching_sessions;
create policy "Users can create own coaching sessions" on public.coaching_sessions
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "Users can update own coaching sessions" on public.coaching_sessions;
create policy "Users can update own coaching sessions" on public.coaching_sessions
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can delete own coaching sessions" on public.coaching_sessions;
create policy "Users can delete own coaching sessions" on public.coaching_sessions
  for delete to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can read own coaching messages" on public.coaching_messages;
create policy "Users can read own coaching messages" on public.coaching_messages
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "Users can send own coaching messages" on public.coaching_messages;
create policy "Users can send own coaching messages" on public.coaching_messages
  for insert to authenticated
  with check ((select auth.uid()) = user_id and role = 'user');
drop policy if exists "Users can read own coaching retrievals" on public.coaching_retrievals;
create policy "Users can read own coaching retrievals" on public.coaching_retrievals
  for select to authenticated using ((select auth.uid()) = user_id);

drop trigger if exists coaching_sessions_set_updated_at on public.coaching_sessions;
create trigger coaching_sessions_set_updated_at
before update on public.coaching_sessions
for each row execute function private.set_updated_at();
