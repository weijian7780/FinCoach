-- Atomic financial edits, complete receipt data, and canonical admin names.
begin;
alter table public.transactions add column if not exists receipt_items jsonb not null default '[]'::jsonb;
-- Validate imported backups and direct API writes as well as the review screen.
create or replace function private.valid_receipt_items(items jsonb) returns boolean
language plpgsql immutable security invoker set search_path='' as $$
declare item jsonb;
begin
  if items is null or jsonb_typeof(items)<>'array' then return false; end if;
  for item in select value from jsonb_array_elements(items) loop
    if jsonb_typeof(item)<>'object' or jsonb_typeof(item->'description') is distinct from 'string'
      or length(btrim(item->>'description'))=0 or jsonb_typeof(item->'amount') is distinct from 'number' then return false; end if;
    if (item->>'amount')::numeric<=0 then return false; end if;
    if item ? 'modifiers' then
      if jsonb_typeof(item->'modifiers')<>'array' then return false; end if;
      if exists(select 1 from jsonb_array_elements(item->'modifiers') m where jsonb_typeof(m)<>'string') then return false; end if;
    end if;
  end loop;
  return true;
end $$;
revoke all on function private.valid_receipt_items(jsonb) from public,anon;
grant execute on function private.valid_receipt_items(jsonb) to authenticated,service_role;
alter table public.transactions add constraint transactions_receipt_items_valid check (private.valid_receipt_items(receipt_items));

create or replace function public.replace_tracked_categories(p_user_id uuid, p_category_ids bigint[])
returns void language plpgsql security invoker set search_path='' as $$
begin
  if auth.uid() is distinct from p_user_id then raise exception 'Not authorized' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended('tracked:' || p_user_id::text, 0));
  if p_category_ids is null or exists (
    select 1 from unnest(p_category_ids) as selected(category_id) left join public.categories c on c.id=selected.category_id
    where c.id is null or (c.user_id is not null and c.user_id <> p_user_id)
  ) then raise exception 'Invalid tracked category'; end if;
  delete from public.user_categories where user_id=p_user_id and not (category_id=any(p_category_ids));
  insert into public.user_categories(user_id,category_id)
    select p_user_id,id from (select distinct unnest(p_category_ids) id) selected
    on conflict(user_id,category_id) do nothing;
end $$;
revoke all on function public.replace_tracked_categories(uuid,bigint[]) from public,anon;
grant execute on function public.replace_tracked_categories(uuid,bigint[]) to authenticated;

create or replace function public.save_budget_month(p_user_id uuid, p_month date, p_overall numeric, p_allocations jsonb)
returns void language plpgsql security invoker set search_path='' as $$
declare item record; old_total numeric;
begin
  if auth.uid() is distinct from p_user_id then raise exception 'Not authorized' using errcode='42501'; end if;
  if p_month is null or extract(day from p_month) <> 1 or p_overall is null or p_overall <= 0
     or p_overall <> round(p_overall,2) or p_overall::text in ('NaN','Infinity','-Infinity')
     or p_allocations is null or jsonb_typeof(p_allocations) <> 'array' then raise exception 'Invalid budget'; end if;
  perform pg_advisory_xact_lock(hashtextextended('budget:' || p_user_id::text || ':' || p_month::text,0));
  if exists(select 1 from jsonb_to_recordset(p_allocations) as x(category_id bigint,amount numeric)
    left join public.categories c on c.id=x.category_id
    where c.id is null or c.type <> 'expense' or (c.user_id is not null and c.user_id<>p_user_id)
      or x.amount is null or x.amount<=0 or x.amount<>round(x.amount,2) or x.amount::text in ('NaN','Infinity','-Infinity'))
    or (select count(*) <> count(distinct category_id) from jsonb_to_recordset(p_allocations) as x(category_id bigint))
    or (select coalesce(sum(amount),0)>p_overall from jsonb_to_recordset(p_allocations) as x(amount numeric))
  then raise exception 'Invalid category allocations'; end if;
  select limit_amount into old_total from public.monthly_budgets where user_id=p_user_id and month=p_month for update;
  -- Expand first, reduce allocations before increases, and shrink the parent last.
  if old_total is null then
    insert into public.monthly_budgets(user_id,month,limit_amount) values(p_user_id,p_month,p_overall);
  elsif p_overall > old_total then
    update public.monthly_budgets set limit_amount=p_overall where user_id=p_user_id and month=p_month;
  end if;
  delete from public.budgets where user_id=p_user_id and month=p_month
    and category_id not in (select category_id from jsonb_to_recordset(p_allocations) as x(category_id bigint));
  for item in select x.category_id,x.amount from jsonb_to_recordset(p_allocations) as x(category_id bigint,amount numeric)
    left join public.budgets b on b.user_id=p_user_id and b.month=p_month and b.category_id=x.category_id
    order by x.amount-coalesce(b.amount,0),x.category_id
  loop
    -- UPDATE avoids the BEFORE INSERT trigger checking an existing allocation twice.
    update public.budgets set amount=item.amount where user_id=p_user_id and month=p_month and category_id=item.category_id;
    if not found then insert into public.budgets(user_id,month,category_id,amount) values(p_user_id,p_month,item.category_id,item.amount); end if;
  end loop;
  update public.monthly_budgets set limit_amount=p_overall where user_id=p_user_id and month=p_month;
end $$;
revoke all on function public.save_budget_month(uuid,date,numeric,jsonb) from public,anon;
grant execute on function public.save_budget_month(uuid,date,numeric,jsonb) to authenticated;

-- Preserve receipt items through both v1 and v2 restore; legacy backups use [].
do $$
declare definition text;
begin
  definition := replace(pg_get_functiondef('private.restore_financial_backup_v1(jsonb,uuid)'::regprocedure),chr(13),'');
  if position('source, receipt_image_path, created_at, updated_at' in definition)=0 then
    raise exception 'Unexpected backup restore definition; receipt field patch requires review';
  end if;
  definition := replace(definition,'source, receipt_image_path, created_at, updated_at','source, receipt_image_path, receipt_items, created_at, updated_at');
  definition := replace(definition,'select id, owner_id, category_id, amount, transaction_date, description,' || chr(10) || '    source, receipt_image_path, receipt_items, created_at, updated_at',
    'select id, owner_id, category_id, amount, transaction_date, description,' || chr(10) || '    source, receipt_image_path, coalesce(receipt_items, ''[]''::jsonb), created_at, updated_at');
  definition := replace(definition,'receipt_image_path text, created_at timestamptz','receipt_image_path text, receipt_items jsonb, created_at timestamptz');
  if position('coalesce(receipt_items, ''[]''::jsonb)' in definition)=0 then
    raise exception 'Receipt restore default was not installed';
  end if;
  execute definition;
end $$;

create or replace function private.sync_account_access() returns trigger language plpgsql security definer set search_path='' as $$
begin
  insert into public.account_access(user_id,email,display_name,created_at,last_sign_in_at)
  values(new.id,new.email,coalesce((select coalesce(full_name,'') from public.profiles where id=new.id),new.raw_user_meta_data->>'display_name',new.raw_user_meta_data->>'full_name',''),new.created_at,new.last_sign_in_at)
  on conflict(user_id) do update set email=excluded.email,display_name=excluded.display_name,last_sign_in_at=excluded.last_sign_in_at;
  return new;
end $$;
revoke all on function private.sync_account_access() from public,anon,authenticated;
create or replace function private.sync_profile_account_name() returns trigger language plpgsql security definer set search_path='' as $$
begin
  update public.account_access set display_name=coalesce(new.full_name,''),updated_at=now() where user_id=new.id;
  return new;
end $$;
revoke all on function private.sync_profile_account_name() from public,anon,authenticated;
create trigger fincoach_profile_name_sync after insert or update of full_name on public.profiles
for each row execute function private.sync_profile_account_name();
update public.account_access a set display_name=coalesce(p.full_name,''),updated_at=now() from public.profiles p
where a.user_id=p.id and a.display_name is distinct from coalesce(p.full_name,'');
commit;
