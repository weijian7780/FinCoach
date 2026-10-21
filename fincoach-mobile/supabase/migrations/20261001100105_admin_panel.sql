-- Admin management: apply only after isolated validation and a database backup.
-- Existing chunk IDs remain unchanged so historical retrieval citations survive.
begin;
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table public.account_access (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null default 'student' check (role in ('student','admin')),
  status text not null default 'active' check (status in ('active','suspended')),
  email text, display_name text,
  created_at timestamptz not null default now(), last_sign_in_at timestamptz,
  updated_at timestamptz not null default now()
);
insert into public.account_access(user_id,email,display_name,created_at,last_sign_in_at)
select id,email,coalesce(raw_user_meta_data->>'display_name',raw_user_meta_data->>'full_name',''),created_at,last_sign_in_at from auth.users;
alter table public.account_access enable row level security;
create policy account_access_self on public.account_access for select to authenticated using (user_id=auth.uid());
revoke all on public.account_access from public,anon,authenticated;
grant select(user_id,role,status) on public.account_access to authenticated;
grant all on public.account_access to service_role;

create function private.sync_account_access() returns trigger language plpgsql security definer set search_path='' as $$
begin
  -- User-editable metadata never sets role or suspension status.
  insert into public.account_access(user_id,email,display_name,created_at,last_sign_in_at)
  values(new.id,new.email,coalesce(new.raw_user_meta_data->>'display_name',new.raw_user_meta_data->>'full_name',''),new.created_at,new.last_sign_in_at)
  on conflict(user_id) do update set email=excluded.email,display_name=excluded.display_name,last_sign_in_at=excluded.last_sign_in_at;
  return new;
end $$;
revoke all on function private.sync_account_access() from public,anon,authenticated;
create trigger fincoach_account_sync after insert or update on auth.users for each row execute function private.sync_account_access();

create function private.is_active_account() returns boolean language sql stable security definer set search_path='' as $$
  select exists(select 1 from public.account_access where user_id=auth.uid() and status='active');
$$;
grant usage on schema private to authenticated;
revoke all on function private.is_active_account() from public,anon;
grant execute on function private.is_active_account() to authenticated;

-- Restrictive checks intersect every existing owner-scoped policy. They cannot
-- create a new permission to read another student's records.
do $$ declare t text; begin
  foreach t in array array['profiles','financial_profiles','transactions','transaction_items','receipts','receipt_items','categories','user_categories','budgets','monthly_budgets','category_limits','savings_goals','savings_contributions','data_exports','export_contents','backups','reports','notification_preferences','reminders','alerts','user_devices','coaching_sessions','coaching_messages','coaching_retrievals'] loop
    if to_regclass('public.'||t) is not null then
      execute format('create policy account_must_be_active on public.%I as restrictive for all to authenticated using (private.is_active_account()) with check (private.is_active_account())',t);
    end if;
  end loop;
end $$;
create policy account_must_be_active on storage.objects as restrictive for all to authenticated
using (private.is_active_account()) with check(private.is_active_account());

-- A SECURITY DEFINER restore RPC bypasses RLS. Preserve its implementation in
-- an unexposed schema and put the access check ahead of that privileged call.
do $$ begin
  if to_regprocedure('public.restore_financial_backup_v1(jsonb,uuid)') is not null then
    alter function public.restore_financial_backup_v1(jsonb,uuid) set schema private;
    revoke all on function private.restore_financial_backup_v1(jsonb,uuid) from public,anon,authenticated;
  end if;
end $$;
create function public.restore_financial_backup_v1(payload jsonb,backup_record_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  if not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  return private.restore_financial_backup_v1(payload,backup_record_id);
end $$;
revoke all on function public.restore_financial_backup_v1(jsonb,uuid) from public,anon;
grant execute on function public.restore_financial_backup_v1(jsonb,uuid) to authenticated;

create table public.knowledge_sources (
  id uuid primary key default gen_random_uuid(), source_key text not null unique,
  title text not null, archived boolean not null default false,
  published_revision_id uuid, latest_revision_id uuid,
  created_at timestamptz not null default now(),updated_at timestamptz not null default now()
);
create table public.knowledge_revisions (
  id uuid primary key default gen_random_uuid(), source_id uuid not null references public.knowledge_sources(id),
  title text not null, content text not null, source_urls jsonb not null default '[]', checked_at date,
  file_path text, status text not null default 'draft' check(status in ('draft','queued','processing','ready','published','failed')),
  created_by uuid references auth.users(id),created_at timestamptz not null default now(),
  lease_token uuid,lease_until timestamptz,attempts integer not null default 0,
  chunk_count integer not null default 0,error_message text,
  unique(source_id,id)
);
alter table public.knowledge_sources add foreign key(id,latest_revision_id) references public.knowledge_revisions(source_id,id) deferrable initially deferred;
alter table public.knowledge_sources add foreign key(id,published_revision_id) references public.knowledge_revisions(source_id,id) deferrable initially deferred;
create table public.admin_audit_logs (
  id bigint generated always as identity primary key,actor_id uuid references auth.users(id) on delete set null,
  action text not null,target_type text not null,target_id text not null,details jsonb not null default '{}',created_at timestamptz not null default now()
);
alter table public.knowledge_documents add column revision_id uuid references public.knowledge_revisions(id);
-- Derived visibility is maintained atomically from the source pointer. Keeping
-- hidden historical vectors out of the ANN graph prevents candidate starvation.
alter table public.knowledge_documents add column is_published boolean not null default false;
-- Import existing sources as published revisions, preserving all original rows,
-- page references, hashes and IDs. Unknown check dates are kept unknown.
do $$ declare r record; sid uuid; rid uuid; begin
  for r in select coalesce(source,'legacy-unknown.md') as source_key,min(title) as title,string_agg(content,E'\n\n' order by page_number nulls first,chunk_index nulls first,id) as content,count(*) as chunks from public.knowledge_documents group by coalesce(source,'legacy-unknown.md') loop
    insert into public.knowledge_sources(source_key,title) values(r.source_key,coalesce(r.title,r.source_key)) returning id into sid;
    insert into public.knowledge_revisions(source_id,title,content,status,chunk_count) values(sid,coalesce(r.title,r.source_key),r.content,'published',r.chunks) returning id into rid;
    update public.knowledge_documents set revision_id=rid where coalesce(source,'legacy-unknown.md')=r.source_key;
    update public.knowledge_sources set latest_revision_id=rid,published_revision_id=rid where id=sid;
  end loop;
end $$;
alter table public.knowledge_documents alter column revision_id set not null;
set constraints all immediate;
drop index if exists public.knowledge_documents_content_hash_idx;
create index knowledge_documents_revision_idx on public.knowledge_documents(revision_id);
update public.knowledge_documents kd set is_published=true
from public.knowledge_sources s where s.published_revision_id=kd.revision_id and not s.archived;
create function private.sync_knowledge_publication() returns trigger language plpgsql set search_path='' as $$begin
  update public.knowledge_documents kd set is_published=coalesce(not new.archived and kd.revision_id=new.published_revision_id,false)
  from public.knowledge_revisions r where r.id=kd.revision_id and r.source_id=new.id
    and kd.is_published is distinct from coalesce(not new.archived and kd.revision_id=new.published_revision_id,false);
  return new;
end$$;
revoke all on function private.sync_knowledge_publication() from public,anon,authenticated;
create trigger fincoach_knowledge_publication after update of published_revision_id,archived on public.knowledge_sources
for each row execute function private.sync_knowledge_publication();
-- The active corpus gets both ANN and lexical indexes; retained revisions stay
-- available for citation lookups by ID without entering new retrieval results.
drop index if exists public.knowledge_documents_embedding_idx;
create index knowledge_documents_embedding_idx on public.knowledge_documents using hnsw(embedding vector_cosine_ops) where is_published;
drop index if exists public.knowledge_documents_fts_idx;
create index knowledge_documents_fts_idx on public.knowledge_documents using gin((
  setweight(to_tsvector('simple',coalesce(title,'')),'A') ||
  setweight(to_tsvector('simple',coalesce(source,'')),'B') ||
  setweight(to_tsvector('simple',content),'C')
)) where is_published;
create index knowledge_revisions_queue_idx on public.knowledge_revisions(status,lease_until,created_at);
do $$ declare t text; begin
  foreach t in array array['knowledge_sources','knowledge_revisions','admin_audit_logs'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
grant usage,select on sequence public.admin_audit_logs_id_seq to service_role;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('knowledge-originals','knowledge-originals',false,10485760,array['text/markdown','text/plain','application/pdf']);

create function private.require_admin(p_actor uuid) returns void language plpgsql set search_path='' as $$
begin
  if not exists(select 1 from public.account_access where user_id=p_actor and role='admin' and status='active') then raise exception 'ADMIN_FORBIDDEN' using errcode='42501'; end if;
end $$;
revoke all on function private.require_admin(uuid) from public,anon,authenticated;
grant usage on schema private to service_role;
grant execute on function private.require_admin(uuid) to service_role;

create function public.admin_set_account_status(p_actor uuid,p_user uuid,p_status text,p_reason text,p_expected text)
returns jsonb language plpgsql set search_path='' as $$ declare a public.account_access; begin
  perform private.require_admin(p_actor);
  if p_status not in ('active','suspended') or length(trim(p_reason)) not between 1 and 300 then raise exception 'ADMIN_INVALID'; end if;
  select * into a from public.account_access where user_id=p_user for update;
  if not found or a.role='admin' then raise exception 'ADMIN_FORBIDDEN'; end if;
  if a.status is distinct from p_expected then raise exception 'ADMIN_CONFLICT'; end if;
  update public.account_access set status=p_status,updated_at=now() where user_id=p_user;
  insert into public.admin_audit_logs(actor_id,action,target_type,target_id,details) values(p_actor,'account.'||p_status,'account',p_user::text,jsonb_build_object('reason',trim(p_reason),'previous_status',a.status));
  return jsonb_build_object('status',p_status);
end $$;

create function public.admin_save_knowledge_revision(p_actor uuid,p_source uuid,p_title text,p_content text,p_urls jsonb,p_checked date,p_file_path text,p_expected uuid)
returns jsonb language plpgsql set search_path='' as $$ declare s public.knowledge_sources; rid uuid; old_path text; begin
  perform private.require_admin(p_actor);
  if length(trim(p_title)) not between 1 and 200 or length(trim(p_content)) not between 1 and 200000 or p_checked is null or p_checked>(now() at time zone 'Asia/Kuala_Lumpur')::date or jsonb_typeof(p_urls)<>'array' or jsonb_array_length(p_urls) not between 1 and 20 then raise exception 'ADMIN_INVALID'; end if;
  if exists(select 1 from jsonb_array_elements_text(p_urls) u where u !~ '^https?://[^ /]+') then raise exception 'ADMIN_INVALID'; end if;
  if p_file_path is not null and split_part(p_file_path,'/',1)<>p_actor::text then raise exception 'ADMIN_FORBIDDEN'; end if;
  if p_source is null then
    if p_expected is not null then raise exception 'ADMIN_CONFLICT'; end if;
    insert into public.knowledge_sources(source_key,title) values('uploaded_'||gen_random_uuid()::text||'.md',trim(p_title)) returning * into s;
  else
    select * into s from public.knowledge_sources where id=p_source for update;
    if not found then raise exception 'ADMIN_INVALID'; end if;
    if s.latest_revision_id is distinct from p_expected then raise exception 'ADMIN_CONFLICT'; end if;
    select file_path into old_path from public.knowledge_revisions where id=s.latest_revision_id;
  end if;
  insert into public.knowledge_revisions(source_id,title,content,source_urls,checked_at,file_path,created_by)
  values(s.id,trim(p_title),trim(p_content),p_urls,p_checked,coalesce(p_file_path,old_path),p_actor) returning id into rid;
  update public.knowledge_sources set latest_revision_id=rid,updated_at=now() where id=s.id;
  insert into public.admin_audit_logs(actor_id,action,target_type,target_id,details) values(p_actor,'knowledge.draft','knowledge_source',s.id::text,jsonb_build_object('revision_id',rid));
  return jsonb_build_object('source_id',s.id,'revision_id',rid);
end $$;

create function public.admin_knowledge_action(p_actor uuid,p_source uuid,p_revision uuid,p_action text,p_expected uuid)
returns jsonb language plpgsql set search_path='' as $$ declare s public.knowledge_sources; r public.knowledge_revisions; begin
  perform private.require_admin(p_actor);
  select * into s from public.knowledge_sources where id=p_source for update;
  if not found then raise exception 'ADMIN_INVALID'; end if;
  if s.latest_revision_id is distinct from p_expected then raise exception 'ADMIN_CONFLICT'; end if;
  if p_action='archive' then
    update public.knowledge_sources set archived=true,updated_at=now() where id=s.id;
  else
    select * into r from public.knowledge_revisions where id=p_revision and source_id=s.id for update;
    if not found then raise exception 'ADMIN_INVALID'; end if;
    if p_action='prepare' then
      if r.id<>s.latest_revision_id or r.status not in ('draft','failed') then raise exception 'ADMIN_CONFLICT'; end if;
      update public.knowledge_revisions set status='queued',attempts=0,error_message=null,lease_token=null,lease_until=null where id=r.id;
    elsif p_action in ('publish','restore') then
      if r.status not in ('ready','published') or r.chunk_count<1 or r.chunk_count<>(select count(*) from public.knowledge_documents where revision_id=r.id) then raise exception 'ADMIN_CONFLICT'; end if;
      if p_action='publish' and r.id<>s.latest_revision_id then raise exception 'ADMIN_CONFLICT'; end if;
      update public.knowledge_revisions set status='ready' where id=s.published_revision_id and id<>r.id;
      update public.knowledge_revisions set status='published' where id=r.id;
      update public.knowledge_sources set published_revision_id=r.id,title=r.title,archived=false,updated_at=now() where id=s.id;
    else raise exception 'ADMIN_INVALID'; end if;
  end if;
  insert into public.admin_audit_logs(actor_id,action,target_type,target_id,details) values(p_actor,'knowledge.'||p_action,'knowledge_source',s.id::text,jsonb_build_object('revision_id',p_revision));
  return jsonb_build_object('source_id',s.id,'action',p_action);
end $$;

create function public.admin_claim_knowledge_revision() returns jsonb language plpgsql set search_path='' as $$ declare r public.knowledge_revisions; begin
  update public.knowledge_revisions set status='failed',error_message='Processing retries exhausted.',lease_token=null,lease_until=null where status='processing' and lease_until<now() and attempts>=3;
  select * into r from public.knowledge_revisions where status='queued' or (status='processing' and lease_until<now() and attempts<3) order by created_at for update skip locked limit 1;
  if not found then return null; end if;
  update public.knowledge_revisions set status='processing',lease_token=gen_random_uuid(),lease_until=now()+interval '10 minutes',attempts=attempts+1 where id=r.id returning * into r;
  return to_jsonb(r)||jsonb_build_object('source_key',(select source_key from public.knowledge_sources where id=r.source_id));
end $$;
create function public.admin_renew_knowledge_lease(p_revision uuid,p_lease uuid) returns void language plpgsql set search_path='' as $$ begin
  update public.knowledge_revisions set lease_until=now()+interval '10 minutes' where id=p_revision and status='processing' and lease_token=p_lease and lease_until>now();
  if not found then raise exception 'ADMIN_CONFLICT'; end if;
end $$;
create function public.admin_finish_knowledge_revision(p_revision uuid,p_lease uuid,p_chunks jsonb) returns void language plpgsql set search_path=pg_catalog,extensions,public as $$ declare r public.knowledge_revisions; c jsonb; sk text; idx integer:=0; begin
  select * into r from public.knowledge_revisions where id=p_revision for update;
  if not found or r.status<>'processing' or r.lease_token is distinct from p_lease or r.lease_until<=now() then raise exception 'ADMIN_CONFLICT'; end if;
  if jsonb_typeof(p_chunks)<>'array' or jsonb_array_length(p_chunks) not between 1 and 200 then raise exception 'ADMIN_INVALID'; end if;
  select source_key into sk from public.knowledge_sources where id=r.source_id;
  delete from public.knowledge_documents where revision_id=r.id;
  for c in select value from jsonb_array_elements(p_chunks) loop
    if c->>'source' is distinct from sk or (c->>'chunk_index')::integer is distinct from idx or jsonb_array_length(c->'embedding')<>1024 or length(c->>'content')<1 then raise exception 'ADMIN_INVALID'; end if;
    insert into public.knowledge_documents(title,content,source,embedding,page_number,chunk_index,content_hash,revision_id)
    values(r.title,c->>'content',sk,(c->'embedding')::text::vector(1024),null,idx,c->>'content_hash',r.id);
    idx:=idx+1;
  end loop;
  update public.knowledge_revisions set status='ready',chunk_count=idx,lease_token=null,lease_until=null,error_message=null where id=r.id;
end $$;
create function public.admin_fail_knowledge_revision(p_revision uuid,p_lease uuid) returns void language plpgsql set search_path='' as $$ begin
  update public.knowledge_revisions set status='failed',error_message='Document processing failed. Retry preparation.',lease_token=null,lease_until=null where id=p_revision and status='processing' and lease_token=p_lease;
end $$;
create function public.admin_recoverable_alerts(p_now timestamptz,p_limit integer default 100)
returns jsonb language plpgsql set search_path='' as $$declare result jsonb;begin
  -- Exclude suspended owners BEFORE the limit so their retained pending alerts
  -- cannot starve active users. Restoration automatically re-enables recovery.
  select coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) into result from (
    select a.id,a.created_at,a.delivery_status,a.next_delivery_attempt_at
    from public.alerts a join public.account_access ac on ac.user_id=a.user_id and ac.status='active'
    where (a.delivery_status='pending' and a.created_at<=p_now-interval '2 minutes')
       or (a.delivery_status='retryable' and a.next_delivery_attempt_at<=p_now)
    order by case when a.delivery_status='pending' then a.created_at else a.next_delivery_attempt_at end,a.id
    limit greatest(1,least(p_limit,100))
  ) q;
  return result;
end $$;
-- All admin RPCs are callable only by the trusted backend; actor IDs come from
-- verified bearer sessions, never from browser-supplied request fields.
do $$ declare f record; begin
  for f in select oid::regprocedure as signature from pg_proc where pronamespace='public'::regnamespace and proname like 'admin_%' loop
    execute format('revoke all on function %s from public,anon,authenticated',f.signature);
    execute format('grant execute on function %s to service_role',f.signature);
  end loop;
end $$;

-- Filter before dense/lexical ranks and limits, using a shared invoker view.
create view public.published_knowledge_documents with(security_invoker=true) as
select kd.* from public.knowledge_documents kd where kd.is_published;
revoke all on public.published_knowledge_documents from public,anon,authenticated;
grant select on public.published_knowledge_documents to service_role;
do $$ declare f record; definition text; begin
  for f in select oid from pg_proc where pronamespace='public'::regnamespace and proname in ('match_knowledge_documents','match_knowledge_documents_hybrid') loop
    definition:=pg_get_functiondef(f.oid);
    if position('public.knowledge_documents' in definition)=0 then raise exception 'Unexpected retrieval definition; migration requires review'; end if;
    execute replace(definition,'public.knowledge_documents','public.published_knowledge_documents');
  end loop;
end $$;
commit;
