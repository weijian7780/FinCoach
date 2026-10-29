-- Preserve existing legacy knowledge without inventing links or original files.
-- Only this function body changes; table/column/key definitions are untouched.
CREATE OR REPLACE FUNCTION public.admin_save_knowledge_revision(p_actor uuid, p_source uuid, p_title text, p_content text, p_urls jsonb, p_checked date, p_file_path text, p_expected uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ declare s public.knowledge_sources; rid uuid; old_path text; old_urls jsonb; legacy_without_provenance boolean := false; begin
  perform private.require_admin(p_actor);
  if length(trim(p_title)) not between 1 and 200 or length(trim(p_content)) not between 1 and 200000 or p_checked>(now() at time zone 'Asia/Kuala_Lumpur')::date or jsonb_typeof(p_urls)<>'array' or jsonb_array_length(p_urls) not between 0 and 20 then raise exception 'ADMIN_INVALID'; end if;
  if exists(select 1 from jsonb_array_elements_text(p_urls) u where u !~ '^https?://[^ /]+') then raise exception 'ADMIN_INVALID'; end if;
  if p_file_path is not null and split_part(p_file_path,'/',1)<>p_actor::text then raise exception 'ADMIN_FORBIDDEN'; end if;
  if p_source is null then
    if p_expected is not null then raise exception 'ADMIN_CONFLICT'; end if;
    insert into public.knowledge_sources(source_key,title) values('uploaded_'||gen_random_uuid()::text||'.md',trim(p_title)) returning * into s;
  else
    select * into s from public.knowledge_sources where id=p_source for update;
    if not found then raise exception 'ADMIN_INVALID'; end if;
    if s.latest_revision_id is distinct from p_expected then raise exception 'ADMIN_CONFLICT'; end if;
    select file_path,source_urls into old_path,old_urls from public.knowledge_revisions where id=s.latest_revision_id;
    -- Only a server-loaded current revision can establish the legacy exception.
    -- New sources and existing sources with recorded provenance remain strict.
    legacy_without_provenance := FOUND AND old_path IS NULL AND old_urls = '[]'::jsonb;
  end if;
  if jsonb_array_length(p_urls)=0 and coalesce(p_file_path,old_path) is null and not legacy_without_provenance then raise exception 'ADMIN_INVALID'; end if;
  insert into public.knowledge_revisions(source_id,title,content,source_urls,checked_at,file_path,created_by)
  values(s.id,trim(p_title),trim(p_content),p_urls,p_checked,coalesce(p_file_path,old_path),p_actor) returning id into rid;
  update public.knowledge_sources set latest_revision_id=rid,updated_at=now() where id=s.id;
  insert into public.admin_audit_logs(actor_id,action,target_type,target_id,details) values(p_actor,'knowledge.draft','knowledge_source',s.id::text,jsonb_build_object('revision_id',rid));
  return jsonb_build_object('source_id',s.id,'revision_id',rid);
end $function$;
