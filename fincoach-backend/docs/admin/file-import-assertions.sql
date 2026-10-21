begin;
set local role service_role;
do $$ declare saved jsonb; failed boolean := false; begin
  saved := public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',null,'File import QA','Build an emergency fund.','[]',null,'00000000-0000-0000-0000-000000000001/test/original.txt',null);
  if not exists(select 1 from public.knowledge_revisions where id=(saved->>'revision_id')::uuid and checked_at is null and source_urls='[]'::jsonb and file_path is not null) then raise exception 'File provenance lost'; end if;
  perform public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',(saved->>'source_id')::uuid,'Edited file','Edited content.','[]',null,null,(saved->>'revision_id')::uuid);
  begin
    perform public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',null,'No source','Content','[]',null,null,null);
  exception when others then failed := true; end;
  if not failed then raise exception 'Missing provenance was accepted'; end if;
  saved := public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',null,'Link import QA','Real webpage content.','["https://example.org/guide"]',null,null,null);
  if saved->>'revision_id' is null then raise exception 'Link import failed'; end if;
end $$;
rollback;
