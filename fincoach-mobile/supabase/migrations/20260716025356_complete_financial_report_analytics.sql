+-- Complete Financial Report and Analytics report-history storage.
-- Analytics are calculated from owner-scoped source records in the mobile client.
-- This table stores only immutable generation metadata required by the ERD.

create table if not exists public.reports (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  period text not null,
  type text not null,
  generated_at timestamptz not null default now()
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
create policy "Users can read own reports"
  on public.reports
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can create own reports" on public.reports;
create policy "Users can create own reports"
  on public.reports
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
