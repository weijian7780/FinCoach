-- Serialize automatic completion across devices; the first complete backup wins.
create or replace function public.complete_financial_backup_v2(backup_record_id uuid, document jsonb, object_path text, object_size bigint, checksum text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare owner_id uuid:=auth.uid(); saved jsonb; section text; expected integer; asset jsonb; refs jsonb; result public.backups;
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text,20261010));
  select data into saved from private.financial_backup_snapshots where backup_id=backup_record_id and user_id=owner_id and financial_backup_snapshots.document is null for update;
  if saved is null or document->>'userId' <> owner_id::text or (document->>'schemaVersion')::integer <> 2 or document->'data' is distinct from saved then raise exception 'Backup does not match the complete server snapshot.'; end if;
  if exists(select 1 from public.backups where id=backup_record_id and backup_type='automatic') and exists(
    select 1 from public.backups where user_id=owner_id and backup_type='automatic' and status='completed'
      and id<>backup_record_id and completed_at >= now()-interval '24 hours'
  ) then raise exception 'A recent automatic backup already exists.'; end if;
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
