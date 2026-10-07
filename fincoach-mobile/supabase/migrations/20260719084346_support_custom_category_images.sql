alter table public.categories
  add column if not exists icon_image_path text;

comment on column public.categories.icon_image_path is
  'Optional user-owned image path in the public category-icons Storage bucket.';

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'category-icons',
  'category-icons',
  true,
  2097152,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Category icons are publicly readable" on storage.objects;
create policy "Category icons are publicly readable" on storage.objects
  for select using (bucket_id = 'category-icons');

drop policy if exists "Users can upload own category icons" on storage.objects;
create policy "Users can upload own category icons" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'category-icons'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "Users can update own category icons" on storage.objects;
create policy "Users can update own category icons" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'category-icons'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  )
  with check (
    bucket_id = 'category-icons'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "Users can delete own category icons" on storage.objects;
create policy "Users can delete own category icons" on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'category-icons'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

-- Keep custom image paths when the existing version-1 financial backup RPC
-- restores custom categories. The replacement is derived from the installed
-- function so unrelated restore logic remains unchanged.
do $migration$
declare
  function_definition text;
begin
  if to_regprocedure('public.restore_financial_backup_v1(jsonb,uuid)') is null then
    return;
  end if;

  select pg_get_functiondef(
    'public.restore_financial_backup_v1(jsonb,uuid)'::regprocedure
  )
  into function_definition;

  if position('icon_image_path' in function_definition) > 0 then
    return;
  end if;

  if position(
       'insert into public.categories (id, name, type, icon, user_id, color)'
       in function_definition
     ) = 0
     or position(
       'select id, name, type, icon, owner_id, color'
       in function_definition
     ) = 0
     or position(
       'as x(id bigint, name text, type text, icon text, user_id uuid, color text)'
       in function_definition
     ) = 0 then
    raise exception 'Could not update restore_financial_backup_v1 for category image paths.';
  end if;

  function_definition := replace(
    function_definition,
    'insert into public.categories (id, name, type, icon, user_id, color)',
    'insert into public.categories (id, name, type, icon, icon_image_path, user_id, color)'
  );
  function_definition := replace(
    function_definition,
    'select id, name, type, icon, owner_id, color',
    'select id, name, type, icon, icon_image_path, owner_id, color'
  );
  function_definition := replace(
    function_definition,
    'as x(id bigint, name text, type text, icon text, user_id uuid, color text)',
    'as x(id bigint, name text, type text, icon text, icon_image_path text, user_id uuid, color text)'
  );

  execute function_definition;
end;
$migration$;
