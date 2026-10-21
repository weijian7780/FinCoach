"""Generate the reviewed migration from the existing restore implementation.
No database connection or credentials. The CLI created the migration filename.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'supabase/migrations/20261010151101_complete_financial_backup_v2.sql'
old = (ROOT / 'supabase/migrations/20261007235407_preserve_backup_restore_reports_categories.sql').read_text()
old = old.replace("    set email = coalesce(profile_data ->> 'email', email),\n        full_name", "    set full_name")
old = re.sub(r"        spending_records_consent = coalesce\(.*?\n        updated_at = now\(\)", "        updated_at = now()", old, flags=re.S)
old = re.sub(r"  perform setval\(.*?\n  update public.backups", "  -- Restored IDs were previously generated; never rewind shared sequences.\n  update public.backups", old, flags=re.S)
old = old.replace("  if owner_id is null then raise exception 'Authentication required.'; end if;", "  if owner_id is null or not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;\n  perform pg_advisory_xact_lock(hashtextextended(owner_id::text, 20261010));\n  perform private.validate_financial_backup_data(payload -> 'data', owner_id);")

prefix = r'''
-- Complete snapshots, immutable attachment manifests and safe financial restore.
-- No existing financial rows are changed by this migration.
alter table public.backups add column if not exists data_counts jsonb;
alter table public.backups add column if not exists attachment_count integer not null default 0 check (attachment_count >= 0);
alter table public.backups add column if not exists cleanup_warning text;

create table private.financial_backup_snapshots (
  backup_id uuid primary key references public.backups(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  data jsonb not null,
  document jsonb,
  created_at timestamptz not null default now()
);
alter table private.financial_backup_snapshots enable row level security;
revoke all on private.financial_backup_snapshots from public, anon, authenticated;

-- Same JSON aggregate can return all rows without PostgREST's table row cap.
create or replace function public.financial_backup_snapshot_v2(backup_record_id uuid default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare owner_id uuid := auth.uid(); result jsonb;
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text, 20261010));
  if backup_record_id is not null and not exists (
    select 1 from public.backups where id=backup_record_id and user_id=owner_id and status in ('pending','processing')
  ) then raise exception 'Pending owned backup not found.'; end if;
  -- All subqueries share the snapshot of THIS ONE statement.
  select jsonb_build_object(
    'profile', (select to_jsonb(p) from public.profiles p where p.id=owner_id),
    'customCategories', (select coalesce(jsonb_agg(to_jsonb(c) order by c.id),'[]'::jsonb) from public.categories c where c.user_id=owner_id),
    'userCategories', (select coalesce(jsonb_agg(to_jsonb(c) order by c.category_id),'[]'::jsonb) from public.user_categories c where c.user_id=owner_id),
    'transactions', (select coalesce(jsonb_agg(to_jsonb(t) order by t.id),'[]'::jsonb) from public.transactions t where t.user_id=owner_id),
    'monthlyBudgets', (select coalesce(jsonb_agg(to_jsonb(b) order by b.id),'[]'::jsonb) from public.monthly_budgets b where b.user_id=owner_id),
    'categoryLimits', (select coalesce(jsonb_agg(to_jsonb(b) order by b.id),'[]'::jsonb) from public.budgets b where b.user_id=owner_id),
    'savingsGoals', (select coalesce(jsonb_agg(to_jsonb(g) order by g.id),'[]'::jsonb) from public.savings_goals g where g.user_id=owner_id),
    'savingsContributions', (select coalesce(jsonb_agg(to_jsonb(c) order by c.id),'[]'::jsonb) from public.savings_contributions c join public.savings_goals g on g.id=c.goal_id where g.user_id=owner_id),
    'reports', (select coalesce(jsonb_agg(to_jsonb(r) order by r.id),'[]'::jsonb) from public.reports r where r.user_id=owner_id),
    'notificationPreferences', (select to_jsonb(p) from public.notification_preferences p where p.user_id=owner_id),
    'reminders', (select coalesce(jsonb_agg(to_jsonb(r) order by r.id),'[]'::jsonb) from public.reminders r where r.user_id=owner_id),
    'alerts', (select coalesce(jsonb_agg(to_jsonb(a) order by a.id),'[]'::jsonb) from public.alerts a where a.user_id=owner_id)
  ) into result;
  if backup_record_id is not null then
    insert into private.financial_backup_snapshots(backup_id,user_id,data) values(backup_record_id,owner_id,result);
  end if;
  return result;
end $$;
revoke all on function public.financial_backup_snapshot_v2(uuid) from public,anon;
grant execute on function public.financial_backup_snapshot_v2(uuid) to authenticated;

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
  for row in select r from jsonb_array_elements((data->'transactions') || (data->'categoryLimits') || (data->'reports') || coalesce(data->'userCategories','[]'::jsonb)) r loop
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

create or replace function public.complete_financial_backup_v2(backup_record_id uuid, document jsonb, object_path text, object_size bigint, checksum text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare owner_id uuid:=auth.uid(); saved jsonb; section text; expected integer; asset jsonb; refs jsonb; result public.backups;
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text,20261010));
  select data into saved from private.financial_backup_snapshots where backup_id=backup_record_id and user_id=owner_id and financial_backup_snapshots.document is null for update;
  if saved is null or document->>'userId' <> owner_id::text or (document->>'schemaVersion')::integer <> 2 or document->'data' is distinct from saved then raise exception 'Backup does not match the complete server snapshot.'; end if;
  perform private.validate_financial_backup_data(saved,owner_id);
  foreach section in array array['profile','customCategories','userCategories','transactions','monthlyBudgets','categoryLimits','savingsGoals','savingsContributions','reports','notificationPreferences','reminders','alerts'] loop
    expected:=case when jsonb_typeof(saved->section)='array' then jsonb_array_length(saved->section) when saved->section='null'::jsonb then 0 else 1 end;
    if (document->'counts'->>section)::integer is distinct from expected then raise exception 'Backup section count mismatch.'; end if;
  end loop;
  if jsonb_typeof(document->'attachments') is distinct from 'array' then raise exception 'Attachment manifest required.'; end if;
  select coalesce(jsonb_agg(distinct x),'[]'::jsonb) into refs from (
    select jsonb_build_object('bucket','receipts','path',r->>'receipt_image_path') x from jsonb_array_elements(saved->'transactions') r where r->>'receipt_image_path' is not null
    union all select jsonb_build_object('bucket','financial-reports','path',r->>'storage_path') from jsonb_array_elements(saved->'reports') r where r->>'storage_path' is not null
    union all select jsonb_build_object('bucket','category-icons','path',r->>'icon_image_path') from jsonb_array_elements(saved->'customCategories') r where r->>'icon_image_path' is not null
  ) r;
  if jsonb_array_length(document->'attachments') <> jsonb_array_length(refs) then raise exception 'Attachment coverage mismatch.'; end if;
  for asset in select a from jsonb_array_elements(document->'attachments') a loop
    if not exists(select 1 from jsonb_array_elements(refs) r where r->>'bucket'=asset->>'bucket' and r->>'path'=asset->>'path')
      or position(owner_id::text||'/assets/'||backup_record_id::text||'/' in asset->>'backupPath') <> 1
      or asset->>'backupPath' ~ '(^|/)\.\.(/|$)' or asset->>'checksumSha256' !~ '^[a-f0-9]{64}$'
      or not exists(select 1 from storage.objects o where o.bucket_id='financial-backups' and o.name=asset->>'backupPath' and (o.metadata->>'size')::bigint=(asset->>'size')::bigint) then raise exception 'Invalid or missing attachment copy.'; end if;
  end loop;
  if exists(select 1 from jsonb_array_elements(document->'attachments') a group by a->>'bucket',a->>'path' having count(*)>1) then raise exception 'Duplicate attachment manifest.'; end if;
  if split_part(object_path,'/',1) <> owner_id::text or checksum !~ '^[a-f0-9]{64}$' or not exists(
    select 1 from storage.objects where bucket_id='financial-backups' and name=object_path and (metadata->>'size')::bigint=object_size) then raise exception 'Invalid backup object metadata.'; end if;
  update private.financial_backup_snapshots set document=complete_financial_backup_v2.document where backup_id=backup_record_id;
  update public.backups set status='completed',schema_version=2,storage_path=object_path,file_size_bytes=object_size,
    checksum_sha256=checksum,data_counts=document->'counts',attachment_count=jsonb_array_length(document->'attachments'),completed_at=now(),cleanup_warning=null
    where id=backup_record_id and user_id=owner_id and status='processing' returning * into result;
  if result.id is null then raise exception 'Processing backup not found.'; end if;
  return to_jsonb(result);
end $$;
revoke all on function public.complete_financial_backup_v2(uuid,jsonb,text,bigint,text) from public,anon;
grant execute on function public.complete_financial_backup_v2(uuid,jsonb,text,bigint,text) to authenticated;

-- All files remain private; supported attachment MIME types are allowed in the
-- existing backup bucket, with the existing per-file size limit.
update storage.buckets set allowed_mime_types=array['application/json','application/pdf','image/png','image/jpeg','image/webp'] where id='financial-backups';
create policy "Users can clean own restored report files" on storage.objects for delete to authenticated
using(bucket_id='financial-reports' and (storage.foldername(name))[1]=auth.uid()::text and (storage.foldername(name))[2]='restored');
'''

suffix = r'''
create or replace function public.restore_financial_backup_v2(payload jsonb, backup_record_id uuid, restored_paths jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare owner_id uuid:=auth.uid(); saved jsonb; data jsonb; mapping jsonb; asset jsonb; section text; field text;
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text,20261010));
  select s.document into saved from private.financial_backup_snapshots s join public.backups b on b.id=s.backup_id
    where s.backup_id=backup_record_id and s.user_id=owner_id and b.status='completed' and b.schema_version=2 for update of b;
  -- Client-controlled financial rows never enter the privileged restore.
  if saved is null or payload is distinct from saved then raise exception 'Backup differs from the verified server snapshot.'; end if;
  if jsonb_typeof(restored_paths) is distinct from 'array' or jsonb_array_length(restored_paths) <> jsonb_array_length(saved->'attachments') then raise exception 'Incomplete recovered attachments.'; end if;
  data:=saved->'data';
  for asset in select a from jsonb_array_elements(saved->'attachments') a loop
    select r into mapping from jsonb_array_elements(restored_paths) r where r->>'bucket'=asset->>'bucket' and r->>'path'=asset->>'path';
    if mapping is null or position(owner_id::text||'/restored/'||backup_record_id::text||'/' in mapping->>'restoredPath') <> 1
      or mapping->>'restoredPath' ~ '(^|/)\.\.(/|$)' or not exists(
      select 1 from storage.objects o where o.bucket_id=asset->>'bucket' and o.name=mapping->>'restoredPath' and (o.metadata->>'size')::bigint=(asset->>'size')::bigint
    ) then raise exception 'Recovered attachment absent or invalid.'; end if;
    section:=case asset->>'bucket' when 'receipts' then 'transactions' when 'financial-reports' then 'reports' else 'customCategories' end;
    field:=case asset->>'bucket' when 'receipts' then 'receipt_image_path' when 'financial-reports' then 'storage_path' else 'icon_image_path' end;
    data:=jsonb_set(data,array[section],(select coalesce(jsonb_agg(case when r->>field=asset->>'path' then jsonb_set(r,array[field],to_jsonb(mapping->>'restoredPath')) else r end),'[]'::jsonb) from jsonb_array_elements(data->section) r));
  end loop;
  perform private.validate_financial_backup_data(data,owner_id);
  return private.restore_financial_backup_v1(jsonb_build_object('schemaVersion',1,'userId',owner_id,'data',data),backup_record_id);
end $$;
revoke all on function public.restore_financial_backup_v2(jsonb,uuid,jsonb) from public,anon;
grant execute on function public.restore_financial_backup_v2(jsonb,uuid,jsonb) to authenticated;
'''
prefix = re.sub(r'order by ([a-z]+)\.id\)', r'order by \1.id::text)', prefix)
prefix = prefix.replace('order by c.category_id)', 'order by c.category_id::text)')
TARGET.write_text(prefix + '\n' + old + '\n' + suffix)
print(f'Generated {TARGET.name}: {len((prefix+old+suffix).splitlines())} lines')
