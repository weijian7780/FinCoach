
-- A report whose custom category was deleted must not block backups, while
-- unresolvable categories on FK-backed rows are still rejected.
-- Needs public.test_assert, public.categories and the backup validator migrations.
do $$
declare
  owner uuid := '00000000-0000-0000-0000-000000000001';
  gone bigint := (select coalesce(max(id),0)+100000 from public.categories);
  base jsonb := jsonb_build_object('profile',null,'notificationPreferences',null,'userCategories','[]'::jsonb,
    'customCategories','[]'::jsonb,'transactions','[]'::jsonb,'monthlyBudgets','[]'::jsonb,'categoryLimits','[]'::jsonb,
    'savingsGoals','[]'::jsonb,'savingsContributions','[]'::jsonb,'reports','[]'::jsonb,'reminders','[]'::jsonb,'alerts','[]'::jsonb);
  rejected boolean;
begin
  perform private.validate_financial_backup_data(
    base || jsonb_build_object('reports',jsonb_build_array(jsonb_build_object('id',1,'user_id',owner,'category_id',gone))), owner);
  perform public.test_assert(true,'report with a deleted category passes backup validation');

  begin
    perform private.validate_financial_backup_data(
      base || jsonb_build_object('categoryLimits',jsonb_build_array(jsonb_build_object('id',1,'user_id',owner,'category_id',gone))), owner);
    rejected := false;
  exception when raise_exception then
    rejected := sqlerrm = 'Category absent from owned snapshot.';
  end;
  perform public.test_assert(rejected,'category limit with a missing category is still rejected');
end$$;
