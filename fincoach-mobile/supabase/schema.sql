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

-- ---------- categories : ERD CATEGORY (shared lookup, no USR_ID) ----------
create table if not exists public.categories (
  id bigint generated always as identity primary key,
  name text not null unique,           -- CATEGORY Name
  type text not null default 'expense' check (type in ('expense', 'income')), -- CATEGORY Type
  icon text                            -- CATEGORY Icon (MaterialIcons name)
);

alter table public.categories enable row level security;
grant select on table public.categories to authenticated;

drop policy if exists "Authenticated users can read categories" on public.categories;
create policy "Authenticated users can read categories" on public.categories
  for select to authenticated using (true);

insert into public.categories (name, type, icon) values
  ('Food', 'expense', 'restaurant'),
  ('Transport', 'expense', 'directions-car'),
  ('Rent', 'expense', 'home'),
  ('Entertainment', 'expense', 'movie'),
  ('Education', 'expense', 'school'),
  ('Others', 'expense', 'more-horiz')
on conflict (name) do nothing;

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

-- ---------- budgets : ERD BUDGET (per category, per month) ----------
create table if not exists public.budgets (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  category_id bigint not null references public.categories (id) on delete cascade,
  amount numeric(12, 2) not null,
  month date not null,                 -- first day of the budget month
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, category_id, month)
);

alter table public.budgets enable row level security;
grant select, insert, update, delete on table public.budgets to authenticated;

drop policy if exists "Users manage own budgets" on public.budgets;
create policy "Users manage own budgets" on public.budgets
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------- savings_goals : ERD SAVINGS_GOAL (many per user) ----------
create table if not exists public.savings_goals (
  id bigint generated always as identity primary key,
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

-- ---------- reports : ERD REPORT (log of generated reports, many per user) ----------
-- Metadata only (period / type / when generated); written when a report is generated
-- or exported. The live Reports screen computes from transactions and does not need this.
create table if not exists public.reports (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  period text not null,                            -- REPORT_Period (e.g. '2026-06')
  type text not null,                              -- REPORT_Type (e.g. 'monthly', 'category', 'export')
  generated_at timestamptz not null default now()  -- REPORT_GeneratedDate
);

alter table public.reports enable row level security;
grant select, insert, delete on table public.reports to authenticated;

drop policy if exists "Users manage own reports" on public.reports;
create policy "Users manage own reports" on public.reports
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

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
