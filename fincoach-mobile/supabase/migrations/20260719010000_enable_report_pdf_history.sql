-- Store generated financial reports as private PDF files.
-- Old report rows contained metadata only, so they cannot be opened and are removed.

alter table public.reports
  add column if not exists title text,
  add column if not exists file_name text,
  add column if not exists storage_path text,
  add column if not exists report_key text,
  add column if not exists start_date date,
  add column if not exists end_date date,
  add column if not exists category_id bigint;

delete from public.reports where storage_path is null;

alter table public.reports
  drop constraint if exists reports_user_report_key_key;
alter table public.reports
  add constraint reports_user_report_key_key
  unique (user_id, report_key);

alter table public.reports
  drop constraint if exists reports_pdf_metadata_check;
alter table public.reports
  add constraint reports_pdf_metadata_check check (
    report_key is null
    or (
      title is not null
      and file_name is not null
      and storage_path is not null
      and char_length(btrim(title)) between 1 and 160
      and char_length(btrim(file_name)) between 5 and 255
      and file_name like '%.pdf'
      and char_length(btrim(storage_path)) between 5 and 512
      and storage_path like user_id::text || '/%'
      and start_date is not null
      and end_date is not null
      and start_date <= end_date
    )
  ) not valid;

grant select, insert, update on table public.reports to authenticated;
revoke delete on table public.reports from authenticated;

drop policy if exists "Users can update own reports" on public.reports;
create policy "Users can update own reports"
  on public.reports
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

insert into storage.buckets (
  id, name, public, file_size_limit, allowed_mime_types
)
values (
  'financial-reports',
  'financial-reports',
  false,
  10485760,
  array['application/pdf']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read own financial reports" on storage.objects;
create policy "Users can read own financial reports"
  on storage.objects
  for select to authenticated
  using (
    bucket_id = 'financial-reports'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "Users can upload own financial reports" on storage.objects;
create policy "Users can upload own financial reports"
  on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'financial-reports'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "Users can update own financial reports" on storage.objects;
create policy "Users can update own financial reports"
  on storage.objects
  for update to authenticated
  using (
    bucket_id = 'financial-reports'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  )
  with check (
    bucket_id = 'financial-reports'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "Users can delete own financial reports" on storage.objects;
create policy "Users can delete own financial reports"
  on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'financial-reports'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );
