-- Report-attempt protocol: one leased claim per generation, a server-derived
-- immutable PDF path, and history rows written only by the completing call.
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
insert into public.coaching_sessions(id,user_id,title) values('00000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000001','Report attempt checks'),('00000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000002','Second student reports');
create table public.test_report_actions(n integer primary key,action_id uuid,message_id uuid,payload jsonb);
insert into public.test_report_actions
select n,('00000000-0000-0000-0000-'||lpad((2100+n)::text,12,'0'))::uuid,('00000000-0000-0000-0000-'||lpad((1100+n)::text,12,'0'))::uuid,
 jsonb_build_object('type','action','action_type','generate_report','action_id',('00000000-0000-0000-0000-'||lpad((2100+n)::text,12,'0'))::uuid,'status','pending','arguments',
  case n when 5 then jsonb_build_object('period','custom','start_date','2029-03-01','end_date','2029-03-31','category_name','FYP Dining')
   when 6 then jsonb_build_object('period','custom','start_date','2029-04-01','end_date','2029-04-30','category_name','Ghost Category')
   when 13 then jsonb_build_object('period','custom','start_date','2029-05-01','end_date','2029-05-31','category_name','Private Dining')
   else jsonb_build_object('period','last_month','start_date','2029-01-01','end_date','2029-01-31','category_name',null) end)
from generate_series(1,13) n;
grant select on public.test_report_actions to service_role;
insert into public.coaching_messages(id,user_id,session_id,role,content)
select ('00000000-0000-0000-0000-'||lpad((3100+n)::text,12,'0'))::uuid,'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000011','user','Generate a synthetic report'
from generate_series(1,13) n;
insert into public.coaching_messages(id,user_id,session_id,role,content,reply_to_message_id,ui_payload)
select message_id,'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000011','assistant','Confirm synthetic report?',('00000000-0000-0000-0000-'||lpad((3100+n)::text,12,'0'))::uuid,payload from public.test_report_actions;
insert into public.coaching_messages(id,user_id,session_id,role,content) values
 ('00000000-0000-0000-0000-000000003200','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000012','user','Generate my synthetic report');
insert into public.coaching_messages(id,user_id,session_id,role,content,reply_to_message_id,ui_payload) values
 ('00000000-0000-0000-0000-000000001200','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000012','assistant','Confirm your report?','00000000-0000-0000-0000-000000003200','{"type":"action","action_type":"generate_report","action_id":"00000000-0000-0000-0000-000000002200","status":"pending","arguments":{"period":"last_month","start_date":"2029-01-01","end_date":"2029-01-31","category_name":null}}');
insert into public.categories(id,user_id,name,type,icon,color) overriding system value values
 (90011,'00000000-0000-0000-0000-000000000001','FYP Dining','expense','restaurant','#000000'),
 (90012,'00000000-0000-0000-0000-000000000002','Private Dining','expense','restaurant','#000000');
-- Storage fixtures: the completing call only publishes an object whose owner,
-- id, version and updated_at still match what the backend downloaded.
create function public.test_reserve_report_object(p_user_id uuid,p_path text) returns jsonb language plpgsql as $$
declare stored storage.objects; begin
  insert into storage.objects(bucket_id,name,owner_id,metadata,updated_at)
  values('financial-reports',p_path,p_user_id::text,jsonb_build_object('size',512,'mimetype','application/pdf'),clock_timestamp())
  on conflict(bucket_id,name) do update set owner_id=excluded.owner_id,metadata=excluded.metadata,updated_at=excluded.updated_at
  returning * into stored;
  return jsonb_build_object('path',stored.name,'object_id',stored.id,'version',stored.version,'updated_at',stored.updated_at,'size',512);
end$$;
create function public.test_report_storage(p_path text) returns jsonb language sql stable as $$
  select jsonb_build_object('path',o.name,'object_id',o.id,'version',o.version,'updated_at',o.updated_at,'size',(o.metadata->>'size')::bigint)
  from storage.objects o where o.bucket_id='financial-reports' and o.name=p_path$$;
create function public.test_report_json(p_title text,p_file_name text) returns jsonb language sql immutable as $$
  select jsonb_build_object('title',p_title,'file_name',p_file_name,'generated_at','2030-02-01T00:00:00Z')$$;
select public.test_assert(has_table_privilege('authenticated','public.report_attempts','select'),'the owner can read attempts through RLS');
select public.test_assert(not has_table_privilege('authenticated','public.report_attempts','insert') and not has_table_privilege('authenticated','public.report_attempts','update') and not has_table_privilege('authenticated','public.report_attempts','delete'),'mobile cannot write attempt rows directly');
select public.test_assert(to_regprocedure('public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb,uuid,jsonb)') is null,'the old report-capable transition signature is gone');
select public.test_assert(not has_function_privilege('authenticated','public.claim_coach_report_attempt(uuid,uuid,uuid,uuid)','execute'),'mobile cannot claim a report attempt directly');
select public.test_assert(not has_function_privilege('authenticated','public.complete_coach_report_attempt(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb)','execute'),'mobile cannot complete a report attempt directly');
set role service_role;
-- The second student has their own live attempt for the isolation checks below.
do $$declare claimed jsonb; begin
  claimed:=public.claim_coach_report_attempt('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000001200','00000000-0000-0000-0000-000000002200','00000000-0000-0000-0000-000000000801');
  perform public.test_assert(claimed->'attempt'->>'status'='active' and claimed->'message'->'ui_payload'->>'status'='approved','the second student claims their own attempt');
end$$;

-- Claim boundaries, actual missing-object rejection, and atomic history replay.
do $$declare u uuid:='00000000-0000-0000-0000-000000000001'; item record;
  t uuid:='00000000-0000-0000-0000-000000000701'; claimed jsonb; path text; proof jsonb; saved public.reports;
begin
  select * into item from public.test_report_actions where n=1;
  begin
    perform public.claim_coach_report_attempt(u,item.message_id,item.action_id,null);
    raise exception 'missing update-required';
  exception when sqlstate 'P0101' then null; end;
  perform public.test_assert((select ui_payload->>'status'='pending' from public.coaching_messages where id=item.message_id),'old client refused before mutation');
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,t);
  path:=claimed->'attempt'->>'storage_path';
  perform public.test_assert(claimed->'attempt'->>'attempt_id'=t::text,'claim returns the exact requested attempt');
  begin
    perform public.claim_coach_report_attempt(u,item.message_id,item.action_id,'00000000-0000-0000-0000-000000000702');
    raise exception 'missing competing claim conflict';
  exception when sqlstate 'P0102' then null; end;
  perform public.test_assert((select status='active' from public.report_attempts where attempt_id=t),'competing device cannot replace a live lease');
  proof:=jsonb_build_object('path',path,'object_id',gen_random_uuid(),'version','v1','updated_at',now(),'size',512);
  begin
    perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('Missing PDF','report.pdf'),proof);
    raise exception 'missing PDF accepted';
  exception when sqlstate 'P0105' then null; end;
  perform public.test_assert(not exists(select 1 from public.reports where storage_path=path),'no missing-PDF history');
  proof:=public.test_reserve_report_object(u,path);
  perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('January report','report.pdf'),proof);
  perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('January report','report.pdf'),proof);
  select * into saved from public.reports where storage_path=path;
  perform public.test_assert(saved.period='2029-01' and saved.start_date='2029-01-01' and saved.category_id is null,'history uses the frozen selection');
  perform public.test_assert((select count(*)=1 from public.reports where storage_path=path),'lost completion replay produces one history row');
end$$;

-- Expired upload recovery and takeover fencing; renewal cannot revive an expired lease.
do $$declare u uuid:='00000000-0000-0000-0000-000000000001'; item record; claimed jsonb;
  t uuid:='00000000-0000-0000-0000-000000000703'; replacement uuid:='00000000-0000-0000-0000-000000000704'; proof jsonb;
begin
  select * into item from public.test_report_actions where n=2;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,t);
  proof:=public.test_reserve_report_object(u,claimed->'attempt'->>'storage_path');
  update public.report_attempts set lease_expires_at=now()-interval '1 second' where attempt_id=t;
  begin
    perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('Expired','expired.pdf'),proof);
    raise exception 'expired completion accepted';
  exception when sqlstate 'P0103' then null; end;
  begin
    perform public.renew_report_attempt(u,item.message_id,t); raise exception 'expired renewal accepted';
  exception when sqlstate 'P0002' then null; end;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,t);
  perform public.test_assert(claimed->'attempt'->>'storage_path'=proof->>'path','same attempt reacquires its uploaded PDF after restart');
  perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('Recovered','recovered.pdf'),proof);
  select * into item from public.test_report_actions where n=3;
  t:='00000000-0000-0000-0000-000000000705';
  perform public.claim_coach_report_attempt(u,item.message_id,item.action_id,t);
  update public.report_attempts set lease_expires_at=now()-interval '1 second' where attempt_id=t;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,replacement);
  perform public.test_assert((select status='superseded' from public.report_attempts where attempt_id=t),'expired takeover fences old renderer');
  begin
    perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,false,'{}');
    raise exception 'stale renderer cancelled replacement';
  exception when sqlstate 'P0103' then null; end;
  perform public.test_assert((select status='active' from public.report_attempts where attempt_id=replacement),'replacement survives stale failure');
end$$;

reset role;
-- Cancel invalidates the attempt; category snapshot and ownership stay fixed.
do $$declare u uuid:='00000000-0000-0000-0000-000000000001'; item record; claimed jsonb; original jsonb;
  t uuid:='00000000-0000-0000-0000-000000000706';
begin
  select * into item from public.test_report_actions where n=4;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,t);
  original:=claimed->'message'->'ui_payload';
  perform public.commit_coach_action(u,item.message_id,original,original||'{"status":"cancelled"}');
  perform public.test_assert((select status='cancelled' from public.report_attempts where attempt_id=t),'cancel invalidates renderer');
  begin
    perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('Late','late.pdf'),'{}');
    raise exception 'late cancelled completion accepted';
  exception when raise_exception then
    if SQLERRM<>'The report action has not been approved.' then raise; end if;
  end;
  select * into item from public.test_report_actions where n=5;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,'00000000-0000-0000-0000-000000000707');
  perform public.test_assert((claimed->'attempt'->>'category_id')::bigint=90011,'category id is fixed at claim');
  update public.categories set name='Renamed Dining' where id=90011;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,'00000000-0000-0000-0000-000000000707');
  perform public.test_assert(claimed->'attempt'->>'category_name'='FYP Dining','resume preserves snapshot after rename');
  select * into item from public.test_report_actions where n=6;
  begin
    perform public.claim_coach_report_attempt(u,item.message_id,item.action_id,gen_random_uuid());
    raise exception 'missing category accepted';
  exception when sqlstate 'P0003' then null; end;
  select * into item from public.test_report_actions where n=13;
  begin
    perform public.claim_coach_report_attempt(u,item.message_id,item.action_id,gen_random_uuid());
    raise exception 'foreign category accepted';
  exception when sqlstate 'P0003' then null; end;
  begin
    perform public.claim_coach_report_attempt('00000000-0000-0000-0000-000000000002',item.message_id,item.action_id,gen_random_uuid());
    raise exception 'foreign action accepted';
  exception when sqlstate 'P0002' then null; end;
end$$;

set role service_role;
-- Wrong owner, MIME, byte size and object-version changes are refused under lock.
do $$declare u uuid:='00000000-0000-0000-0000-000000000001'; item record; claimed jsonb; proof jsonb; path text;
  t uuid:='00000000-0000-0000-0000-000000000708'; kind text;
begin
  select * into item from public.test_report_actions where n=7;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,t); path:=claimed->'attempt'->>'storage_path';
  foreach kind in array array['owner','mime','empty','version','size','missing'] loop
    proof:=public.test_reserve_report_object(u,path);
    if kind='owner' then update storage.objects set owner_id='foreign' where name=path;
    elsif kind='mime' then update storage.objects set metadata=metadata||'{"mimetype":"application/pdf-invalid"}' where name=path;
    elsif kind='empty' then update storage.objects set metadata=metadata||'{"size":0}' where name=path;
    elsif kind='version' then update storage.objects set version='changed' where name=path;
    elsif kind='size' then proof:=proof||'{"size":511}';
    else delete from storage.objects where name=path; end if;
    begin
      perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('Invalid','invalid.pdf'),proof);
      raise exception 'invalid object accepted: %',kind;
    exception when sqlstate 'P0105' then null; end;
  end loop;
  perform public.test_assert(not exists(select 1 from public.reports where storage_path=path),'invalid artifacts never publish history');
end$$;
reset role;

-- Inject a failure AFTER history insertion: the attempt and action roll back too.
create function public.test_report_rollback() returns trigger language plpgsql as $$begin
  if new.id='00000000-0000-0000-0000-000000001108' and new.ui_payload->>'status'='executed' then
    raise exception 'injected report rollback'; end if; return new; end$$;
create trigger test_report_rollback before update on public.coaching_messages for each row execute function public.test_report_rollback();
set role service_role;
do $$declare u uuid:='00000000-0000-0000-0000-000000000001'; item record; claimed jsonb; proof jsonb;
  t uuid:='00000000-0000-0000-0000-000000000709';
begin
  select * into item from public.test_report_actions where n=8;
  claimed:=public.claim_coach_report_attempt(u,item.message_id,item.action_id,t);
  proof:=public.test_reserve_report_object(u,claimed->'attempt'->>'storage_path');
  begin
    perform public.complete_coach_report_attempt(u,item.message_id,item.action_id,t,true,public.test_report_json('Rollback','rollback.pdf'),proof);
    raise exception 'rollback not injected';
  exception when raise_exception then if SQLERRM<>'injected report rollback' then raise; end if; end;
  perform public.test_assert(not exists(select 1 from public.reports where storage_path=proof->>'path'),'rollback removes history insert');
  perform public.test_assert((select status='active' and report_id is null from public.report_attempts where attempt_id=t),'rollback retains active attempt');
  perform public.test_assert((select ui_payload->>'status'='approved' from public.coaching_messages where id=item.message_id),'rollback retains approved action');
end$$;
reset role;

-- Service-only concurrency helper. One claim winner publishes; competing fresh
-- attempts return P0102 and cannot steal its lease. Cancellation shares the lock.
create function public.test_racing_report_attempt(confirm boolean, message_uuid uuid, client_no integer)
returns void language plpgsql as $$declare u uuid:='00000000-0000-0000-0000-000000000001'; action_uuid uuid;
  claimed jsonb; original jsonb; t uuid; proof jsonb;
begin
  select (ui_payload->>'action_id')::uuid into action_uuid from public.coaching_messages where id=message_uuid;
  if confirm then
    begin
      claimed:=public.claim_coach_report_attempt(u,message_uuid,action_uuid,gen_random_uuid());
      if claimed->'message'->'ui_payload'->>'status'='executed' then return; end if;
      t:=(claimed->'attempt'->>'attempt_id')::uuid;
      proof:=public.test_reserve_report_object(u,claimed->'attempt'->>'storage_path');
      perform public.complete_coach_report_attempt(u,message_uuid,action_uuid,t,true,public.test_report_json('Concurrent','concurrent.pdf'),proof);
    exception when sqlstate 'P0102' then null;
      when raise_exception then if SQLERRM not in ('This report action was cancelled. Ask for a new report.','The report action has not been approved.') then raise; end if;
    end;
  else
    select ui_payload into original from public.coaching_messages where id=message_uuid;
    if original->>'status' in ('executed','cancelled') then return; end if;
    begin perform public.commit_coach_action(u,message_uuid,original,original||'{"status":"cancelled"}');
    exception when raise_exception then if SQLERRM<>'Action state changed. Reload and try again.' then raise; end if; end;
  end if;
end$$;

-- Reserved coaching artifacts cannot be modified by clients; the original
-- manual and restored namespaces retain their owner-scoped CRUD behavior.
set role authenticated;
do $$declare path text:='00000000-0000-0000-0000-000000000001/coach/00000000-0000-0000-0000-000000000709.pdf'; affected integer;
begin
  update storage.objects set metadata='{}' where name=path;
  get diagnostics affected=row_count;
  perform public.test_assert(affected=0,'client cannot overwrite a reserved PDF');
  delete from storage.objects where name=path;
  get diagnostics affected=row_count;
  perform public.test_assert(affected=0,'client cannot delete a reserved PDF');
  begin
    insert into storage.objects(bucket_id,name) values('financial-reports','00000000-0000-0000-0000-000000000001/coach/unclaimed.pdf');
    raise exception 'unclaimed upload accepted';
  exception when insufficient_privilege then null; end;
  insert into storage.objects(bucket_id,name) values
    ('financial-reports','00000000-0000-0000-0000-000000000001/manual-repair.pdf'),
    ('financial-reports','00000000-0000-0000-0000-000000000001/restored/repair.pdf');
  update storage.objects set metadata='{"manual":true}' where name like '%repair.pdf';
  get diagnostics affected=row_count;
  perform public.test_assert(affected=2,'manual and backup-restore objects remain editable');
  delete from storage.objects where name like '%repair.pdf';
  get diagnostics affected=row_count;
  perform public.test_assert(affected=2,'manual and backup-restore objects remain deletable');
end$$;
reset role;

reset role;
-- The sweep excludes active/completed attempts and ALL referenced paths.
do $$declare target public.report_attempts; begin
  select * into target from public.report_attempts where status='cancelled' limit 1;
  perform public.test_assert(exists(select 1 from public.list_abandoned_coach_report_artifacts() where attempt_id=target.attempt_id),'cancelled unreferenced attempts are sweep candidates');
  insert into public.reports(user_id,period,type,title,file_name,storage_path,report_key,start_date,end_date,generated_at)
  values(target.user_id,'2029-01','monthly','Legacy reference','legacy.pdf',target.storage_path,'legacy-reference','2029-01-01','2029-01-31',now());
  perform public.test_assert(not exists(select 1 from public.list_abandoned_coach_report_artifacts() where attempt_id=target.attempt_id),'any existing history reference protects the artifact');
  delete from public.reports where report_key='legacy-reference';
end$$;
