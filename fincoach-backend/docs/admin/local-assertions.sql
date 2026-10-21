\set ON_ERROR_STOP on
-- Old chunk IDs and page numbers survive backfill.
do $$begin
 if not exists(select 1 from public.knowledge_documents where id=1 and page_number=7 and revision_id is not null) then raise exception 'Legacy citation lost';end if;
 if not exists(select 1 from public.match_knowledge_documents(array_fill(1::real,array[1024])::vector,5) where id=1) then raise exception 'Legacy retrieval lost';end if;
end$$;
update public.account_access set role='admin' where user_id='00000000-0000-0000-0000-000000000001';
-- Spoofing metadata never grants an administrative role.
update auth.users set raw_user_meta_data='{"role":"admin"}' where id='00000000-0000-0000-0000-000000000002';
do $$begin if (select role from public.account_access where user_id='00000000-0000-0000-0000-000000000002')<>'student' then raise exception 'Metadata escalation';end if;end$$;
set role authenticated;
set request.jwt.claim.sub='00000000-0000-0000-0000-000000000002';
do $$begin
 if (select count(*) from public.transactions)<>1 then raise exception 'Owner RLS broken';end if;
 if (select count(*) from storage.objects)<>1 then raise exception 'Storage owner RLS broken';end if;
 if (select count(user_id) from public.account_access)<>1 then raise exception 'Account privacy broken';end if;
 begin perform public.admin_claim_knowledge_revision();raise exception 'Student RPC permitted';exception when insufficient_privilege then null;end;
 begin perform private.restore_financial_backup_v1('{}',null);raise exception 'Private restore exposed';exception when insufficient_privilege then null;end;
end$$;
reset role;
set role service_role;
select public.admin_set_account_status('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','suspended','local test','active');
do $$begin
 begin perform public.admin_set_account_status('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','suspended','local test','active');raise exception 'Admin suspended';exception when others then if sqlerrm not like '%ADMIN_FORBIDDEN%' then raise;end if;end;
 begin perform public.admin_set_account_status('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000003','suspended','local test','active');raise exception 'Student actor accepted';exception when insufficient_privilege then null;end;
end$$;
reset role;
set role authenticated;
do $$begin
 if exists(select 1 from public.transactions) or exists(select 1 from storage.objects) then raise exception 'Suspension read bypass';end if;
 begin insert into public.transactions(user_id,amount) values(auth.uid(),5);raise exception 'Suspension write bypass';exception when insufficient_privilege then null;end;
 begin perform public.restore_financial_backup_v1('{}',null);raise exception 'Restore bypass';exception when insufficient_privilege then null;end;
end$$;
reset role;
set role service_role;
select public.admin_set_account_status('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','active','restore local test','suspended');
reset role;
set role authenticated;
select public.restore_financial_backup_v1('{}',null);
reset role;
-- Publication, rollback, lease ownership and optimistic conflicts.
set role service_role;
do $$declare saved jsonb; sid uuid; rid uuid; draft uuid; claimed jsonb; chunks jsonb; before_count bigint; begin
 saved:=public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',null,'Local knowledge','Malaysian financial literacy test','["https://example.org/source"]',current_date,null,null);
 sid:=(saved->>'source_id')::uuid;rid:=(saved->>'revision_id')::uuid;
 perform public.admin_knowledge_action('00000000-0000-0000-0000-000000000001',sid,rid,'prepare',rid);
 claimed:=public.admin_claim_knowledge_revision();
 chunks:=jsonb_build_array(jsonb_build_object('title','Local knowledge','content','Malaysian financial literacy test','source',claimed->>'source_key','chunk_index',0,'content_hash','local-hash','embedding',to_jsonb(array_fill(1::real,array[1024]))));
 begin perform public.admin_finish_knowledge_revision(rid,gen_random_uuid(),chunks);raise exception 'Wrong lease permitted';exception when others then if sqlerrm not like '%ADMIN_CONFLICT%' then raise;end if;end;
 select count(*) into before_count from public.knowledge_documents;
 begin perform public.admin_finish_knowledge_revision(rid,(claimed->>'lease_token')::uuid,chunks||jsonb_build_array(chunks->0));raise exception 'Partial invalid chunks accepted';exception when others then if sqlerrm not like '%ADMIN_INVALID%' then raise;end if;end;
 if (select count(*) from public.knowledge_documents)<>before_count then raise exception 'Partial ingestion committed';end if;
 perform public.admin_finish_knowledge_revision(rid,(claimed->>'lease_token')::uuid,chunks);
 if exists(select 1 from public.published_knowledge_documents where revision_id=rid) then raise exception 'Unpublished ready content leaked';end if;
 perform public.admin_knowledge_action('00000000-0000-0000-0000-000000000001',sid,rid,'publish',rid);
 if not exists(select 1 from public.match_knowledge_documents_hybrid('literacy',array_fill(1::real,array[1024])::vector,5) m join public.knowledge_documents d on d.id=m.id where d.revision_id=rid) then raise exception 'Published content absent';end if;
 saved:=public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',sid,'Edited draft','Draft must remain private','["https://example.org/source"]',current_date,null,rid);draft:=(saved->>'revision_id')::uuid;
 if not exists(select 1 from public.published_knowledge_documents where revision_id=rid) then raise exception 'Draft hid published version';end if;
 begin perform public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',sid,'Stale','stale','["https://example.org"]',current_date,null,rid);raise exception 'CAS overwrite allowed';exception when others then if sqlerrm not like '%ADMIN_CONFLICT%' then raise;end if;end;
 perform public.admin_knowledge_action('00000000-0000-0000-0000-000000000001',sid,null,'archive',draft);
 if exists(select 1 from public.published_knowledge_documents where revision_id=rid) then raise exception 'Archive leaked';end if;
 if exists(select 1 from public.match_knowledge_documents(array_fill(1::real,array[1024])::vector,5) m join public.knowledge_documents d on d.id=m.id where d.revision_id=rid) then raise exception 'Dense archive leaked';end if;
 if exists(select 1 from public.match_knowledge_documents_hybrid('literacy',array_fill(1::real,array[1024])::vector,5) m join public.knowledge_documents d on d.id=m.id where d.revision_id=rid) then raise exception 'Hybrid archive leaked';end if;
 perform public.admin_knowledge_action('00000000-0000-0000-0000-000000000001',sid,rid,'restore',draft);
 if not exists(select 1 from public.published_knowledge_documents where revision_id=rid) then raise exception 'Restore absent';end if;
 if (select count(*) from public.admin_audit_logs)<7 then raise exception 'Audit events missing';end if;
end$$;
reset role;
select 'LOCAL ADMIN DATABASE ASSERTIONS PASSED' as result;
-- Expired lease recovery: old worker cannot renew or finish after takeover.
set role service_role;
do $$declare saved jsonb;sid uuid;rid uuid;old_lease uuid;reclaimed jsonb;begin
 saved:=public.admin_save_knowledge_revision('00000000-0000-0000-0000-000000000001',null,'Lease test','Lease test content','["https://example.org"]',current_date,null,null);
 sid:=(saved->>'source_id')::uuid;rid:=(saved->>'revision_id')::uuid;
 perform public.admin_knowledge_action('00000000-0000-0000-0000-000000000001',sid,rid,'prepare',rid);
 reclaimed:=public.admin_claim_knowledge_revision();old_lease:=(reclaimed->>'lease_token')::uuid;
 update public.knowledge_revisions set lease_until=now()-interval '1 minute' where id=rid;
 reclaimed:=public.admin_claim_knowledge_revision();
 if (reclaimed->>'id')::uuid<>rid or (reclaimed->>'lease_token')::uuid=old_lease then raise exception 'Lease not recovered';end if;
 begin perform public.admin_renew_knowledge_lease(rid,old_lease);raise exception 'Old worker retained lease';exception when others then if sqlerrm not like '%ADMIN_CONFLICT%' then raise;end if;end;
 update public.knowledge_revisions set lease_until=now()-interval '1 minute',attempts=3 where id=rid;
 perform public.admin_claim_knowledge_revision();
 if (select status from public.knowledge_revisions where id=rid)<>'failed' then raise exception 'Unbounded processing retries';end if;
end$$;
reset role;
select 'LEASE RECOVERY ASSERTIONS PASSED' as result;
-- The visibility cache must track archive, restore and pointer removal.
do $$declare s public.knowledge_sources;begin
 select * into s from public.knowledge_sources where source_key='legacy.md';
 update public.knowledge_sources set published_revision_id=null where id=s.id;
 if exists(select 1 from public.knowledge_documents where revision_id=s.published_revision_id and is_published) then raise exception 'Cleared publication pointer left visible chunks';end if;
 update public.knowledge_sources set published_revision_id=s.published_revision_id where id=s.id;
 if not exists(select 1 from public.knowledge_documents where revision_id=s.published_revision_id and is_published) then raise exception 'Pointer restoration not synchronized';end if;
 update public.knowledge_sources set archived=true where id=s.id;
 if exists(select 1 from public.knowledge_documents where revision_id=s.published_revision_id and is_published) then raise exception 'Archive not synchronized';end if;
 update public.knowledge_sources set archived=false where id=s.id;
end$$;
select 'PUBLICATION INDEX MEMBERSHIP ASSERTIONS PASSED' as result;
