-- Serialize deletion against snapshot/restore before touching Storage.
create or replace function public.begin_financial_backup_delete_v2(backup_record_id uuid)
returns void language plpgsql security definer set search_path = public, pg_temp as $$
declare owner_id uuid := auth.uid();
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Active account required'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text,20261010));
  update public.backups set status='failed',cleanup_warning='Deletion pending'
    where id=backup_record_id and user_id=owner_id;
  if not found then raise exception 'Backup unavailable'; end if;
end $$;
revoke all on function public.begin_financial_backup_delete_v2(uuid) from public, anon;
grant execute on function public.begin_financial_backup_delete_v2(uuid) to authenticated;
