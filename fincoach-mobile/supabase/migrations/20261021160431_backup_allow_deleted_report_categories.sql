-- A report's category_id is a historical label with no foreign key (the
-- report title and PDF keep the category name), so deleting a custom category
-- may leave it dangling. Requiring it to resolve blocked every later backup with
-- "Category absent from owned snapshot.". Reports are no longer checked; rows
-- that restore inserts against real FKs (transactions, category limits,
-- tracked categories) still are. Only the category-reference loop changes.
create or replace function private.validate_financial_backup_data(data jsonb, owner_id uuid)
returns void language plpgsql security definer set search_path='' as $$
declare section text; row jsonb; category_id bigint; field text; target_section text;
begin
  if jsonb_typeof(data) is distinct from 'object' then raise exception 'Invalid financial backup data.'; end if;
  foreach section in array array['customCategories','transactions','monthlyBudgets','categoryLimits','savingsGoals','savingsContributions','reports','reminders','alerts'] loop
    if jsonb_typeof(data->section) is distinct from 'array' then raise exception 'Incomplete backup section: %',section; end if;
    if exists(select 1 from jsonb_array_elements(data->section) r where jsonb_typeof(r) <> 'object' or
      (section <> 'savingsContributions' and r->>'user_id' is distinct from owner_id::text)) then raise exception 'Backup row owner mismatch.'; end if;
    if exists(select 1 from jsonb_array_elements(data->section) r group by r->>'id' having count(*) > 1 or r->>'id' is null) then raise exception 'Invalid duplicate backup IDs.'; end if;
  end loop;
  if data->'profile' <> 'null'::jsonb and data->'profile'->>'id' is distinct from owner_id::text then raise exception 'Profile owner mismatch.'; end if;
  if data->'notificationPreferences' <> 'null'::jsonb and data->'notificationPreferences'->>'user_id' is distinct from owner_id::text then raise exception 'Preferences owner mismatch.'; end if;
  if data ? 'userCategories' then
    if jsonb_typeof(data->'userCategories') is distinct from 'array' then raise exception 'Invalid category selections.'; end if;
    if exists(select 1 from jsonb_array_elements(data->'userCategories') r where r->>'user_id' is distinct from owner_id::text) then raise exception 'Category selection owner mismatch.'; end if;
  end if;
  -- Category references must be either captured own categories or shared lookups.
  -- Reports are excluded: their category_id has no FK and may outlive the category.
  for row in select r from jsonb_array_elements((data->'transactions') || (data->'categoryLimits') || coalesce(data->'userCategories','[]'::jsonb)) r loop
    if row->>'category_id' is not null then
      category_id := (row->>'category_id')::bigint;
      if not exists(select 1 from jsonb_array_elements(data->'customCategories') c where (c->>'id')::bigint=category_id)
        and not exists(select 1 from public.categories c where c.id=category_id and c.user_id is null) then raise exception 'Category absent from owned snapshot.'; end if;
    end if;
  end loop;
  if exists(select 1 from jsonb_array_elements(data->'savingsContributions') c where not exists(
    select 1 from jsonb_array_elements(data->'savingsGoals') g where g->>'id'=c->>'goal_id')) then raise exception 'Contribution goal absent from snapshot.'; end if;
  if exists(select 1 from jsonb_array_elements(data->'savingsGoals') g where coalesce((g->>'current_amount')::numeric,0) <>
    (select coalesce(sum((c->>'amount')::numeric),0) from jsonb_array_elements(data->'savingsContributions') c where c->>'goal_id'=g->>'id')) then
    raise exception 'Incomplete backup: savings balance does not match contributions.'; end if;
  for row in select r from jsonb_array_elements(data->'alerts') r loop
    foreach field in array array['budget_id','category_limit_id','savings_goal_id','reminder_id'] loop
      target_section := case field when 'budget_id' then 'monthlyBudgets' when 'category_limit_id' then 'categoryLimits' when 'savings_goal_id' then 'savingsGoals' else 'reminders' end;
      if row->>field is not null and not exists(select 1 from jsonb_array_elements(data->target_section) r where r->>'id'=row->>field) then raise exception 'Alert reference absent from snapshot.'; end if;
    end loop;
  end loop;
  for row in select r from jsonb_array_elements(data->'transactions') r where r->>'receipt_image_path' is not null
    union all select jsonb_build_object('receipt_image_path',r->>'storage_path') from jsonb_array_elements(data->'reports') r where r->>'storage_path' is not null
    union all select jsonb_build_object('receipt_image_path',r->>'icon_image_path') from jsonb_array_elements(data->'customCategories') r where r->>'icon_image_path' is not null loop
    if split_part(row->>'receipt_image_path','/',1) <> owner_id::text or row->>'receipt_image_path' ~ '(^|/)\.\.(/|$)' then raise exception 'Attachment owner mismatch.'; end if;
  end loop;
end $$;
revoke all on function private.validate_financial_backup_data(jsonb,uuid) from public,anon,authenticated;
