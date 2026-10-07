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
