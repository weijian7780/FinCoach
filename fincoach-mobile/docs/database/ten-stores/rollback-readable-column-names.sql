-- Readable physical column names; existing view/API column names are preserved.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
SET LOCAL check_function_bodies=false;
LOCK TABLE public."account_records",public."alert_records",public."budget_records",public."coaching_records",public."export_backup_records",public."knowledge_records",public."profiles",public."report_records",public."savings_records",public."transaction_records" IN ACCESS EXCLUSIVE MODE;
CREATE TEMP TABLE rename_before(name text, rows bigint, digest text) ON COMMIT DROP;
INSERT INTO rename_before SELECT 'private.coaching_processing_leases', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM private.coaching_processing_leases x) z;
INSERT INTO rename_before SELECT 'private.financial_backup_snapshots', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM private.financial_backup_snapshots x) z;
INSERT INTO rename_before SELECT 'public.account_access', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.account_access x) z;
INSERT INTO rename_before SELECT 'public.admin_audit_logs', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.admin_audit_logs x) z;
INSERT INTO rename_before SELECT 'public.alerts', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.alerts x) z;
INSERT INTO rename_before SELECT 'public.backups', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.backups x) z;
INSERT INTO rename_before SELECT 'public.budgets', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.budgets x) z;
INSERT INTO rename_before SELECT 'public.categories', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.categories x) z;
INSERT INTO rename_before SELECT 'public.coaching_messages', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.coaching_messages x) z;
INSERT INTO rename_before SELECT 'public.coaching_retrievals', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.coaching_retrievals x) z;
INSERT INTO rename_before SELECT 'public.coaching_sessions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.coaching_sessions x) z;
INSERT INTO rename_before SELECT 'public.data_exports', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.data_exports x) z;
INSERT INTO rename_before SELECT 'public.export_contents', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.export_contents x) z;
INSERT INTO rename_before SELECT 'public.knowledge_documents', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.knowledge_documents x) z;
INSERT INTO rename_before SELECT 'public.knowledge_revisions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.knowledge_revisions x) z;
INSERT INTO rename_before SELECT 'public.knowledge_sources', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.knowledge_sources x) z;
INSERT INTO rename_before SELECT 'public.monthly_budgets', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.monthly_budgets x) z;
INSERT INTO rename_before SELECT 'public.notification_preferences', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.notification_preferences x) z;
INSERT INTO rename_before SELECT 'public.profiles', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.profiles x) z;
INSERT INTO rename_before SELECT 'public.reminders', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.reminders x) z;
INSERT INTO rename_before SELECT 'public.report_attempts', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.report_attempts x) z;
INSERT INTO rename_before SELECT 'public.reports', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.reports x) z;
INSERT INTO rename_before SELECT 'public.savings_contributions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.savings_contributions x) z;
INSERT INTO rename_before SELECT 'public.savings_goals', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.savings_goals x) z;
INSERT INTO rename_before SELECT 'public.transactions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.transactions x) z;
INSERT INTO rename_before SELECT 'public.user_categories', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.user_categories x) z;
INSERT INTO rename_before SELECT 'public.user_devices', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.user_devices x) z;
CREATE TEMP TABLE rename_acl ON COMMIT DROP AS SELECT c.oid,c.relacl,c.relrowsecurity,c.relforcerowsecurity,a.attnum,a.attacl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid WHERE n.nspname IN ('public','private') AND a.attnum>0 AND NOT a.attisdropped;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.account_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','account_user_id','account_role','account_status','account_email','account_display_name','account_created_at','account_last_sign_in_at','account_updated_at','audit_id','audit_actor_id','audit_action','audit_target_type','audit_target_id','audit_details','audit_created_at','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in account_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.alert_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','alert_id','alert_user_id','alert_type','alert_kind','alert_title','alert_message','alert_budget_id','alert_category_limit_id','alert_savings_goal_id','alert_reminder_id','alert_source_data','alert_dedupe_key','alert_scheduled_for','alert_delivered_at','alert_read_at','alert_dismissed_at','alert_delivery_status','alert_delivery_error','alert_delivery_attempt_count','alert_delivery_claimed_at','alert_next_delivery_attempt_at','alert_delivery_receipts','alert_created_at','reminder_id','reminder_user_id','reminder_type','reminder_title','reminder_amount','reminder_due_at','reminder_lead_days','reminder_recurrence','reminder_recurrence_anchor_day','reminder_enabled','reminder_next_trigger_at','reminder_last_triggered_at','reminder_created_at','reminder_updated_at','preference_user_id','preference_budget_enabled','preference_savings_enabled','preference_savings_lead_days','preference_savings_reminder_time','preference_savings_milestones_enabled','preference_spending_enabled','preference_spending_frequency','preference_spending_weekday','preference_spending_reminder_time','preference_bills_enabled','preference_default_bill_lead_days','preference_default_bill_reminder_time','preference_timezone','preference_created_at','preference_updated_at','device_id','device_user_id','device_expo_push_token','device_platform','device_name','device_active','device_last_seen_at','device_last_error','device_created_at','device_updated_at','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in alert_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.budget_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','monthly_budget_id','monthly_budget_user_id','monthly_budget_month','monthly_budget_limit_amount','monthly_budget_created_at','monthly_budget_updated_at','category_limit_id','category_limit_user_id','category_limit_category_id','category_limit_amount','category_limit_month','category_limit_created_at','category_limit_updated_at','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in budget_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.coaching_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','session_id','session_user_id','session_title','session_created_at','session_updated_at','session_last_message_at','message_id','message_session_id','message_user_id','message_role','message_content','message_reply_to_message_id','message_status','message_error_code','message_model','message_prompt_tokens','message_completion_tokens','message_created_at','message_feedback','message_ui_payload','retrieval_id','retrieval_user_id','retrieval_assistant_message_id','retrieval_knowledge_document_id','retrieval_rank','retrieval_similarity','retrieval_title','retrieval_source','retrieval_created_at','processing_message_id','processing_token','processing_expires_at','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in coaching_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.export_backup_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','export_id','export_user_id','export_format','export_status','export_file_name','export_file_size_bytes','export_date_from','export_date_to','export_completed_at','export_created_at','export_content_export_id','export_content_content_type','backup_id','backup_user_id','backup_type','backup_status','backup_file_name','backup_storage_path','backup_file_size_bytes','backup_checksum_sha256','backup_schema_version','backup_last_restore_status','backup_last_restored_at','backup_completed_at','backup_created_at','backup_data_counts','backup_attachment_count','backup_cleanup_warning','snapshot_backup_id','snapshot_user_id','snapshot_data','snapshot_document','snapshot_created_at','record_type','owner_user_id']::text[] THEN RAISE EXCEPTION 'Unexpected columns in export_backup_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.knowledge_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','source_id','source_key','source_title','source_archived','source_published_revision_id','source_latest_revision_id','source_created_at','source_updated_at','revision_id','revision_source_id','revision_title','revision_content','revision_source_urls','revision_checked_at','revision_file_path','revision_status','revision_created_by','revision_created_at','revision_lease_token','revision_lease_until','revision_attempts','revision_chunk_count','revision_error_message','chunk_id','chunk_title','chunk_content','chunk_source','chunk_embedding','chunk_created_at','chunk_page_number','chunk_index','chunk_content_hash','chunk_revision_id','chunk_is_published','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in knowledge_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.profiles'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','email','full_name','avatar_url','onboarding_completed','spending_records_consent','university','student_id','monthly_income','monthly_budget','spending_categories','created_at','updated_at','monthly_allowance','year_of_study','income_source','financial_status','coaching_style','auto_backup_enabled']::text[] THEN RAISE EXCEPTION 'Unexpected columns in profiles'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.report_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','report_id','report_user_id','report_period','report_type','report_generated_at','report_title','report_file_name','report_storage_path','report_key','report_start_date','report_end_date','report_category_id','report_attempt_attempt_id','report_attempt_user_id','report_attempt_message_id','report_attempt_action_id','report_attempt_storage_path','report_attempt_period','report_attempt_report_type','report_attempt_start_date','report_attempt_end_date','report_attempt_category_id','report_attempt_category_name','report_attempt_arguments','report_attempt_status','report_attempt_report_id','report_attempt_lease_expires_at','report_attempt_lease_owner','report_attempt_lease_renewed_at','report_attempt_lease_renewal_count','report_attempt_created_at','report_attempt_updated_at','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in report_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.savings_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','goal_id','goal_user_id','goal_name','goal_target_amount','goal_current_amount','goal_created_at','goal_updated_at','goal_deadline','contribution_id','contribution_goal_id','contribution_amount','contribution_contributed_on','contribution_note','contribution_created_at','record_type','owner_user_id']::text[] THEN RAISE EXCEPTION 'Unexpected columns in savings_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.transaction_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['record_id','transaction_id','transaction_user_id','transaction_category_id','transaction_amount','transaction_date','transaction_description','transaction_source','transaction_receipt_image_path','transaction_created_at','transaction_updated_at','transaction_receipt_items','category_id','category_name','category_type','category_icon','category_user_id','category_color','category_icon_image_path','selected_category_user_id','selected_category_category_id','selected_category_created_at','record_type']::text[] THEN RAISE EXCEPTION 'Unexpected columns in transaction_records'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r24_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r24_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  if not exists (
    select 1
    from public.categories c
    where c.id = new."transaction_category_id"
      and (c.user_id is null or c.user_id = new."transaction_user_id")
      and c.type in (''expense'', ''income'')
  ) then
    raise exception ''Transaction category is not available to this user.''
      using errcode = ''23503'';
  end if;

  new."transaction_source" = btrim(new."transaction_source");
  new."transaction_description" = nullif(btrim(coalesce(new."transaction_description", '''')), '''');
  new."transaction_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r24_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r26_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r26_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  new."device_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r26_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r22_owner()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r22_owner()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
BEGIN
  IF NEW."contribution_goal_id" IS NOT NULL THEN
    SELECT user_id INTO NEW.owner_user_id FROM "public"."savings_goals" WHERE "id"=NEW."contribution_goal_id";
  END IF;
  RETURN NEW;
END $function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r22_owner()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r13_owner()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r13_owner()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
BEGIN
  IF NEW."export_content_export_id" IS NOT NULL THEN
    SELECT user_id INTO NEW.owner_user_id FROM "public"."data_exports" WHERE "id"=NEW."export_content_export_id";
  END IF;
  RETURN NEW;
END $function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r13_owner()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r05_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r05_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''''
AS $function$
declare
  webhook_url text;
  webhook_secret text;
begin
  select decrypted_secret into webhook_url
  from vault.decrypted_secrets
  where name = ''alert_webhook_url''
  limit 1;

  select decrypted_secret into webhook_secret
  from vault.decrypted_secrets
  where name = ''alert_webhook_secret''
  limit 1;

  if webhook_url is null or webhook_secret is null then
    return new;
  end if;

  perform net.http_post(
    url := webhook_url,
    headers := jsonb_build_object(
      ''Content-Type'', ''application/json'',
      ''x-fincoach-webhook-secret'', webhook_secret
    ),
    body := jsonb_build_object(''alertId'', new."alert_id"),
    timeout_milliseconds := 5000
  );

  return new;
exception
  when others then
    raise warning ''Alert delivery webhook could not be queued (SQLSTATE %).'', sqlstate;
    return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r05_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r07_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r07_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
declare
  parent_limit numeric(12, 2);
  allocated numeric(12, 2);
begin
  if ''budgets'' = ''budgets'' then
    select mb.limit_amount
    into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new."category_limit_user_id" and mb.month = new."category_limit_month";

    if parent_limit is null then
      raise exception ''Create the overall monthly budget before adding category limits.''
        using errcode = ''23514'';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."category_limit_user_id"
      and b.month = new."category_limit_month"
      and b.id <> coalesce(new."category_limit_id", -1);

    if allocated + new."category_limit_amount" > parent_limit then
      raise exception ''Category limits cannot exceed the overall monthly budget.''
        using errcode = ''23514'';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."category_limit_user_id" and b.month = new."category_limit_month";

    if allocated > new.limit_amount then
      raise exception ''Overall monthly budget cannot be lower than allocated category limits.''
        using errcode = ''23514'';
    end if;
  end if;

  new."category_limit_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r07_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r11_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r11_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  new."session_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r11_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r16_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r16_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$begin

  update public.knowledge_documents kd set is_published=coalesce(not new."source_archived" and kd.revision_id=new."source_published_revision_id",false)

  from public.knowledge_revisions r where r.id=kd.revision_id and r.source_id=new."source_id"

    and kd.is_published is distinct from coalesce(not new."source_archived" and kd.revision_id=new."source_published_revision_id",false);

  return new;

end$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r16_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r17_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r17_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
declare
  parent_limit numeric(12, 2);
  allocated numeric(12, 2);
begin
  if ''monthly_budgets'' = ''budgets'' then
    select mb.limit_amount
    into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new."monthly_budget_user_id" and mb.month = new."monthly_budget_month";

    if parent_limit is null then
      raise exception ''Create the overall monthly budget before adding category limits.''
        using errcode = ''23514'';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."monthly_budget_user_id"
      and b.month = new."monthly_budget_month"
      and b.id <> coalesce(new."monthly_budget_id", -1);

    if allocated + new.amount > parent_limit then
      raise exception ''Category limits cannot exceed the overall monthly budget.''
        using errcode = ''23514'';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."monthly_budget_user_id" and b.month = new."monthly_budget_month";

    if allocated > new."monthly_budget_limit_amount" then
      raise exception ''Overall monthly budget cannot be lower than allocated category limits.''
        using errcode = ''23514'';
    end if;
  end if;

  new."monthly_budget_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r17_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r18_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r18_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  new."preference_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r18_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r19_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r19_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  new."reminder_title" = btrim(new."reminder_title");
  if new."reminder_recurrence_anchor_day" is null then
    new."reminder_recurrence_anchor_day" = extract(day from new."reminder_due_at")::smallint;
  end if;
  if new."reminder_enabled" then
    new."reminder_next_trigger_at" = new."reminder_due_at" - make_interval(days => new."reminder_lead_days");
  else
    new."reminder_next_trigger_at" = null;
  end if;
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r19_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r19_trigger_1()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r19_trigger_1()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  new."reminder_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r19_trigger_1()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r22_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r22_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''''
AS $function$
declare
  affected_goal_id uuid;
  authenticated_user_id uuid := (select auth.uid());
  goal_owner_id uuid;
  goal_target numeric(12, 2);
  contribution_total numeric(12, 2);
begin
IF TG_OP=''DELETE'' THEN IF OLD."contribution_id" IS NULL THEN RETURN OLD; END IF; ELSE IF NEW."contribution_id" IS NULL THEN RETURN NEW; END IF; END IF;

  affected_goal_id := case when tg_op = ''DELETE'' then old."contribution_goal_id" else new."contribution_goal_id" end;

  select g.user_id, g.target_amount
  into goal_owner_id, goal_target
  from public.savings_goals as g
  where g.id = affected_goal_id
  for update;

  -- A parent can already be gone during ON DELETE CASCADE.
  if not found then
    return null;
  end if;

  if authenticated_user_id is not null and goal_owner_id <> authenticated_user_id then
    raise exception ''Savings goal ownership check failed.'';
  end if;

  select coalesce(sum(c.amount), 0)
  into contribution_total
  from public.savings_contributions as c
  where c.goal_id = affected_goal_id;

  if contribution_total > goal_target then
    raise exception ''Contribution exceeds the remaining savings target.'';
  end if;

  update public.savings_goals
  set current_amount = contribution_total,
      updated_at = now()
  where id = affected_goal_id;

  return null;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r22_trigger_0()'; END IF; END $check$;
ALTER TABLE public.account_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.account_records RENAME COLUMN "account_user_id" TO "r03_user_id";
ALTER TABLE public.account_records RENAME COLUMN "account_role" TO "r03_role";
ALTER TABLE public.account_records RENAME COLUMN "account_status" TO "r03_status";
ALTER TABLE public.account_records RENAME COLUMN "account_email" TO "r03_email";
ALTER TABLE public.account_records RENAME COLUMN "account_display_name" TO "r03_display_name";
ALTER TABLE public.account_records RENAME COLUMN "account_created_at" TO "r03_created_at";
ALTER TABLE public.account_records RENAME COLUMN "account_last_sign_in_at" TO "r03_last_sign_in_at";
ALTER TABLE public.account_records RENAME COLUMN "account_updated_at" TO "r03_updated_at";
ALTER TABLE public.account_records RENAME COLUMN "audit_id" TO "r04_id";
ALTER TABLE public.account_records RENAME COLUMN "audit_actor_id" TO "r04_actor_id";
ALTER TABLE public.account_records RENAME COLUMN "audit_action" TO "r04_action";
ALTER TABLE public.account_records RENAME COLUMN "audit_target_type" TO "r04_target_type";
ALTER TABLE public.account_records RENAME COLUMN "audit_target_id" TO "r04_target_id";
ALTER TABLE public.account_records RENAME COLUMN "audit_details" TO "r04_details";
ALTER TABLE public.account_records RENAME COLUMN "audit_created_at" TO "r04_created_at";
ALTER TABLE public.account_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.alert_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_id" TO "r05_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_user_id" TO "r05_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_type" TO "r05_type";
ALTER TABLE public.alert_records RENAME COLUMN "alert_kind" TO "r05_kind";
ALTER TABLE public.alert_records RENAME COLUMN "alert_title" TO "r05_title";
ALTER TABLE public.alert_records RENAME COLUMN "alert_message" TO "r05_message";
ALTER TABLE public.alert_records RENAME COLUMN "alert_budget_id" TO "r05_budget_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_category_limit_id" TO "r05_category_limit_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_savings_goal_id" TO "r05_savings_goal_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_reminder_id" TO "r05_reminder_id";
ALTER TABLE public.alert_records RENAME COLUMN "alert_source_data" TO "r05_source_data";
ALTER TABLE public.alert_records RENAME COLUMN "alert_dedupe_key" TO "r05_dedupe_key";
ALTER TABLE public.alert_records RENAME COLUMN "alert_scheduled_for" TO "r05_scheduled_for";
ALTER TABLE public.alert_records RENAME COLUMN "alert_delivered_at" TO "r05_delivered_at";
ALTER TABLE public.alert_records RENAME COLUMN "alert_read_at" TO "r05_read_at";
ALTER TABLE public.alert_records RENAME COLUMN "alert_dismissed_at" TO "r05_dismissed_at";
ALTER TABLE public.alert_records RENAME COLUMN "alert_delivery_status" TO "r05_delivery_status";
ALTER TABLE public.alert_records RENAME COLUMN "alert_delivery_error" TO "r05_delivery_error";
ALTER TABLE public.alert_records RENAME COLUMN "alert_delivery_attempt_count" TO "r05_delivery_attempt_count";
ALTER TABLE public.alert_records RENAME COLUMN "alert_delivery_claimed_at" TO "r05_delivery_claimed_at";
ALTER TABLE public.alert_records RENAME COLUMN "alert_next_delivery_attempt_at" TO "r05_next_delivery_attempt_at";
ALTER TABLE public.alert_records RENAME COLUMN "alert_delivery_receipts" TO "r05_delivery_receipts";
ALTER TABLE public.alert_records RENAME COLUMN "alert_created_at" TO "r05_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_id" TO "r19_id";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_user_id" TO "r19_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_type" TO "r19_type";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_title" TO "r19_title";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_amount" TO "r19_amount";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_due_at" TO "r19_due_at";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_lead_days" TO "r19_lead_days";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_recurrence" TO "r19_recurrence";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_recurrence_anchor_day" TO "r19_recurrence_anchor_day";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_enabled" TO "r19_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_next_trigger_at" TO "r19_next_trigger_at";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_last_triggered_at" TO "r19_last_triggered_at";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_created_at" TO "r19_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "reminder_updated_at" TO "r19_updated_at";
ALTER TABLE public.alert_records RENAME COLUMN "preference_user_id" TO "r18_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "preference_budget_enabled" TO "r18_budget_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "preference_savings_enabled" TO "r18_savings_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "preference_savings_lead_days" TO "r18_savings_lead_days";
ALTER TABLE public.alert_records RENAME COLUMN "preference_savings_reminder_time" TO "r18_savings_reminder_time";
ALTER TABLE public.alert_records RENAME COLUMN "preference_savings_milestones_enabled" TO "r18_savings_milestones_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "preference_spending_enabled" TO "r18_spending_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "preference_spending_frequency" TO "r18_spending_frequency";
ALTER TABLE public.alert_records RENAME COLUMN "preference_spending_weekday" TO "r18_spending_weekday";
ALTER TABLE public.alert_records RENAME COLUMN "preference_spending_reminder_time" TO "r18_spending_reminder_time";
ALTER TABLE public.alert_records RENAME COLUMN "preference_bills_enabled" TO "r18_bills_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "preference_default_bill_lead_days" TO "r18_default_bill_lead_days";
ALTER TABLE public.alert_records RENAME COLUMN "preference_default_bill_reminder_time" TO "r18_default_bill_reminder_time";
ALTER TABLE public.alert_records RENAME COLUMN "preference_timezone" TO "r18_timezone";
ALTER TABLE public.alert_records RENAME COLUMN "preference_created_at" TO "r18_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "preference_updated_at" TO "r18_updated_at";
ALTER TABLE public.alert_records RENAME COLUMN "device_id" TO "r26_id";
ALTER TABLE public.alert_records RENAME COLUMN "device_user_id" TO "r26_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "device_expo_push_token" TO "r26_expo_push_token";
ALTER TABLE public.alert_records RENAME COLUMN "device_platform" TO "r26_platform";
ALTER TABLE public.alert_records RENAME COLUMN "device_name" TO "r26_device_name";
ALTER TABLE public.alert_records RENAME COLUMN "device_active" TO "r26_active";
ALTER TABLE public.alert_records RENAME COLUMN "device_last_seen_at" TO "r26_last_seen_at";
ALTER TABLE public.alert_records RENAME COLUMN "device_last_error" TO "r26_last_error";
ALTER TABLE public.alert_records RENAME COLUMN "device_created_at" TO "r26_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "device_updated_at" TO "r26_updated_at";
ALTER TABLE public.alert_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.budget_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.budget_records RENAME COLUMN "monthly_budget_id" TO "r17_id";
ALTER TABLE public.budget_records RENAME COLUMN "monthly_budget_user_id" TO "r17_user_id";
ALTER TABLE public.budget_records RENAME COLUMN "monthly_budget_month" TO "r17_month";
ALTER TABLE public.budget_records RENAME COLUMN "monthly_budget_limit_amount" TO "r17_limit_amount";
ALTER TABLE public.budget_records RENAME COLUMN "monthly_budget_created_at" TO "r17_created_at";
ALTER TABLE public.budget_records RENAME COLUMN "monthly_budget_updated_at" TO "r17_updated_at";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_id" TO "r07_id";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_user_id" TO "r07_user_id";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_category_id" TO "r07_category_id";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_amount" TO "r07_amount";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_month" TO "r07_month";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_created_at" TO "r07_created_at";
ALTER TABLE public.budget_records RENAME COLUMN "category_limit_updated_at" TO "r07_updated_at";
ALTER TABLE public.budget_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.coaching_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.coaching_records RENAME COLUMN "session_id" TO "r11_id";
ALTER TABLE public.coaching_records RENAME COLUMN "session_user_id" TO "r11_user_id";
ALTER TABLE public.coaching_records RENAME COLUMN "session_title" TO "r11_title";
ALTER TABLE public.coaching_records RENAME COLUMN "session_created_at" TO "r11_created_at";
ALTER TABLE public.coaching_records RENAME COLUMN "session_updated_at" TO "r11_updated_at";
ALTER TABLE public.coaching_records RENAME COLUMN "session_last_message_at" TO "r11_last_message_at";
ALTER TABLE public.coaching_records RENAME COLUMN "message_id" TO "r09_id";
ALTER TABLE public.coaching_records RENAME COLUMN "message_session_id" TO "r09_session_id";
ALTER TABLE public.coaching_records RENAME COLUMN "message_user_id" TO "r09_user_id";
ALTER TABLE public.coaching_records RENAME COLUMN "message_role" TO "r09_role";
ALTER TABLE public.coaching_records RENAME COLUMN "message_content" TO "r09_content";
ALTER TABLE public.coaching_records RENAME COLUMN "message_reply_to_message_id" TO "r09_reply_to_message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "message_status" TO "r09_status";
ALTER TABLE public.coaching_records RENAME COLUMN "message_error_code" TO "r09_error_code";
ALTER TABLE public.coaching_records RENAME COLUMN "message_model" TO "r09_model";
ALTER TABLE public.coaching_records RENAME COLUMN "message_prompt_tokens" TO "r09_prompt_tokens";
ALTER TABLE public.coaching_records RENAME COLUMN "message_completion_tokens" TO "r09_completion_tokens";
ALTER TABLE public.coaching_records RENAME COLUMN "message_created_at" TO "r09_created_at";
ALTER TABLE public.coaching_records RENAME COLUMN "message_feedback" TO "r09_feedback";
ALTER TABLE public.coaching_records RENAME COLUMN "message_ui_payload" TO "r09_ui_payload";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_id" TO "r10_id";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_user_id" TO "r10_user_id";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_assistant_message_id" TO "r10_assistant_message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_knowledge_document_id" TO "r10_knowledge_document_id";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_rank" TO "r10_rank";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_similarity" TO "r10_similarity";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_title" TO "r10_title";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_source" TO "r10_source";
ALTER TABLE public.coaching_records RENAME COLUMN "retrieval_created_at" TO "r10_created_at";
ALTER TABLE public.coaching_records RENAME COLUMN "processing_message_id" TO "r01_message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "processing_token" TO "r01_token";
ALTER TABLE public.coaching_records RENAME COLUMN "processing_expires_at" TO "r01_expires_at";
ALTER TABLE public.coaching_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.export_backup_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_id" TO "r12_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_user_id" TO "r12_user_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_format" TO "r12_format";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_status" TO "r12_status";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_file_name" TO "r12_file_name";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_file_size_bytes" TO "r12_file_size_bytes";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_date_from" TO "r12_date_from";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_date_to" TO "r12_date_to";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_completed_at" TO "r12_completed_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_created_at" TO "r12_created_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_content_export_id" TO "r13_export_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "export_content_content_type" TO "r13_content_type";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_id" TO "r06_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_user_id" TO "r06_user_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_type" TO "r06_backup_type";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_status" TO "r06_status";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_file_name" TO "r06_file_name";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_storage_path" TO "r06_storage_path";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_file_size_bytes" TO "r06_file_size_bytes";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_checksum_sha256" TO "r06_checksum_sha256";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_schema_version" TO "r06_schema_version";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_last_restore_status" TO "r06_last_restore_status";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_last_restored_at" TO "r06_last_restored_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_completed_at" TO "r06_completed_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_created_at" TO "r06_created_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_data_counts" TO "r06_data_counts";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_attachment_count" TO "r06_attachment_count";
ALTER TABLE public.export_backup_records RENAME COLUMN "backup_cleanup_warning" TO "r06_cleanup_warning";
ALTER TABLE public.export_backup_records RENAME COLUMN "snapshot_backup_id" TO "r02_backup_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "snapshot_user_id" TO "r02_user_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "snapshot_data" TO "r02_data";
ALTER TABLE public.export_backup_records RENAME COLUMN "snapshot_document" TO "r02_document";
ALTER TABLE public.export_backup_records RENAME COLUMN "snapshot_created_at" TO "r02_created_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.export_backup_records RENAME COLUMN "owner_user_id" TO "_owner_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_id" TO "r16_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_key" TO "r16_source_key";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_title" TO "r16_title";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_archived" TO "r16_archived";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_published_revision_id" TO "r16_published_revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_latest_revision_id" TO "r16_latest_revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_created_at" TO "r16_created_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "source_updated_at" TO "r16_updated_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_id" TO "r15_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_source_id" TO "r15_source_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_title" TO "r15_title";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_content" TO "r15_content";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_source_urls" TO "r15_source_urls";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_checked_at" TO "r15_checked_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_file_path" TO "r15_file_path";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_status" TO "r15_status";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_created_by" TO "r15_created_by";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_created_at" TO "r15_created_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_lease_token" TO "r15_lease_token";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_lease_until" TO "r15_lease_until";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_attempts" TO "r15_attempts";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_chunk_count" TO "r15_chunk_count";
ALTER TABLE public.knowledge_records RENAME COLUMN "revision_error_message" TO "r15_error_message";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_id" TO "r14_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_title" TO "r14_title";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_content" TO "r14_content";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_source" TO "r14_source";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_embedding" TO "r14_embedding";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_created_at" TO "r14_created_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_page_number" TO "r14_page_number";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_index" TO "r14_chunk_index";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_content_hash" TO "r14_content_hash";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_revision_id" TO "r14_revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "chunk_is_published" TO "r14_is_published";
ALTER TABLE public.knowledge_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.report_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.report_records RENAME COLUMN "report_id" TO "r21_id";
ALTER TABLE public.report_records RENAME COLUMN "report_user_id" TO "r21_user_id";
ALTER TABLE public.report_records RENAME COLUMN "report_period" TO "r21_period";
ALTER TABLE public.report_records RENAME COLUMN "report_type" TO "r21_type";
ALTER TABLE public.report_records RENAME COLUMN "report_generated_at" TO "r21_generated_at";
ALTER TABLE public.report_records RENAME COLUMN "report_title" TO "r21_title";
ALTER TABLE public.report_records RENAME COLUMN "report_file_name" TO "r21_file_name";
ALTER TABLE public.report_records RENAME COLUMN "report_storage_path" TO "r21_storage_path";
ALTER TABLE public.report_records RENAME COLUMN "report_key" TO "r21_report_key";
ALTER TABLE public.report_records RENAME COLUMN "report_start_date" TO "r21_start_date";
ALTER TABLE public.report_records RENAME COLUMN "report_end_date" TO "r21_end_date";
ALTER TABLE public.report_records RENAME COLUMN "report_category_id" TO "r21_category_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_attempt_id" TO "r20_attempt_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_user_id" TO "r20_user_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_message_id" TO "r20_message_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_action_id" TO "r20_action_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_storage_path" TO "r20_storage_path";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_period" TO "r20_period";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_report_type" TO "r20_report_type";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_start_date" TO "r20_start_date";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_end_date" TO "r20_end_date";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_category_id" TO "r20_category_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_category_name" TO "r20_category_name";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_arguments" TO "r20_arguments";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_status" TO "r20_status";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_report_id" TO "r20_report_id";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_lease_expires_at" TO "r20_lease_expires_at";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_lease_owner" TO "r20_lease_owner";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_lease_renewed_at" TO "r20_lease_renewed_at";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_lease_renewal_count" TO "r20_lease_renewal_count";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_created_at" TO "r20_created_at";
ALTER TABLE public.report_records RENAME COLUMN "report_attempt_updated_at" TO "r20_updated_at";
ALTER TABLE public.report_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.savings_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.savings_records RENAME COLUMN "goal_id" TO "r23_id";
ALTER TABLE public.savings_records RENAME COLUMN "goal_user_id" TO "r23_user_id";
ALTER TABLE public.savings_records RENAME COLUMN "goal_name" TO "r23_name";
ALTER TABLE public.savings_records RENAME COLUMN "goal_target_amount" TO "r23_target_amount";
ALTER TABLE public.savings_records RENAME COLUMN "goal_current_amount" TO "r23_current_amount";
ALTER TABLE public.savings_records RENAME COLUMN "goal_created_at" TO "r23_created_at";
ALTER TABLE public.savings_records RENAME COLUMN "goal_updated_at" TO "r23_updated_at";
ALTER TABLE public.savings_records RENAME COLUMN "goal_deadline" TO "r23_deadline";
ALTER TABLE public.savings_records RENAME COLUMN "contribution_id" TO "r22_id";
ALTER TABLE public.savings_records RENAME COLUMN "contribution_goal_id" TO "r22_goal_id";
ALTER TABLE public.savings_records RENAME COLUMN "contribution_amount" TO "r22_amount";
ALTER TABLE public.savings_records RENAME COLUMN "contribution_contributed_on" TO "r22_contributed_on";
ALTER TABLE public.savings_records RENAME COLUMN "contribution_note" TO "r22_note";
ALTER TABLE public.savings_records RENAME COLUMN "contribution_created_at" TO "r22_created_at";
ALTER TABLE public.savings_records RENAME COLUMN "record_type" TO "_record_kind";
ALTER TABLE public.savings_records RENAME COLUMN "owner_user_id" TO "_owner_id";
ALTER TABLE public.transaction_records RENAME COLUMN "record_id" TO "_row_id";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_id" TO "r24_id";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_user_id" TO "r24_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_category_id" TO "r24_category_id";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_amount" TO "r24_amount";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_date" TO "r24_transaction_date";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_description" TO "r24_description";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_source" TO "r24_source";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_receipt_image_path" TO "r24_receipt_image_path";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_created_at" TO "r24_created_at";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_updated_at" TO "r24_updated_at";
ALTER TABLE public.transaction_records RENAME COLUMN "transaction_receipt_items" TO "r24_receipt_items";
ALTER TABLE public.transaction_records RENAME COLUMN "category_id" TO "r08_id";
ALTER TABLE public.transaction_records RENAME COLUMN "category_name" TO "r08_name";
ALTER TABLE public.transaction_records RENAME COLUMN "category_type" TO "r08_type";
ALTER TABLE public.transaction_records RENAME COLUMN "category_icon" TO "r08_icon";
ALTER TABLE public.transaction_records RENAME COLUMN "category_user_id" TO "r08_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "category_color" TO "r08_color";
ALTER TABLE public.transaction_records RENAME COLUMN "category_icon_image_path" TO "r08_icon_image_path";
ALTER TABLE public.transaction_records RENAME COLUMN "selected_category_user_id" TO "r25_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "selected_category_category_id" TO "r25_category_id";
ALTER TABLE public.transaction_records RENAME COLUMN "selected_category_created_at" TO "r25_created_at";
ALTER TABLE public.transaction_records RENAME COLUMN "record_type" TO "_record_kind";
CREATE OR REPLACE FUNCTION private.trial_r24_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if not exists (
    select 1
    from public.categories c
    where c.id = new."r24_category_id"
      and (c.user_id is null or c.user_id = new."r24_user_id")
      and c.type in ('expense', 'income')
  ) then
    raise exception 'Transaction category is not available to this user.'
      using errcode = '23503';
  end if;

  new."r24_source" = btrim(new."r24_source");
  new."r24_description" = nullif(btrim(coalesce(new."r24_description", '')), '');
  new."r24_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r26_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new."r26_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r22_owner()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
  IF NEW."r22_goal_id" IS NOT NULL THEN
    SELECT user_id INTO NEW._owner_id FROM "public"."savings_goals" WHERE "id"=NEW."r22_goal_id";
  END IF;
  RETURN NEW;
END $function$
;
CREATE OR REPLACE FUNCTION private.trial_r13_owner()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
  IF NEW."r13_export_id" IS NOT NULL THEN
    SELECT user_id INTO NEW._owner_id FROM "public"."data_exports" WHERE "id"=NEW."r13_export_id";
  END IF;
  RETURN NEW;
END $function$
;
CREATE OR REPLACE FUNCTION private.trial_r05_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  webhook_url text;
  webhook_secret text;
begin
  select decrypted_secret into webhook_url
  from vault.decrypted_secrets
  where name = 'alert_webhook_url'
  limit 1;

  select decrypted_secret into webhook_secret
  from vault.decrypted_secrets
  where name = 'alert_webhook_secret'
  limit 1;

  if webhook_url is null or webhook_secret is null then
    return new;
  end if;

  perform net.http_post(
    url := webhook_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-fincoach-webhook-secret', webhook_secret
    ),
    body := jsonb_build_object('alertId', new."r05_id"),
    timeout_milliseconds := 5000
  );

  return new;
exception
  when others then
    raise warning 'Alert delivery webhook could not be queued (SQLSTATE %).', sqlstate;
    return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r07_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  parent_limit numeric(12, 2);
  allocated numeric(12, 2);
begin
  if 'budgets' = 'budgets' then
    select mb.limit_amount
    into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new."r07_user_id" and mb.month = new."r07_month";

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r07_user_id"
      and b.month = new."r07_month"
      and b.id <> coalesce(new."r07_id", -1);

    if allocated + new."r07_amount" > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r07_user_id" and b.month = new."r07_month";

    if allocated > new.limit_amount then
      raise exception 'Overall monthly budget cannot be lower than allocated category limits.'
        using errcode = '23514';
    end if;
  end if;

  new."r07_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r11_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new."r11_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r16_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$begin

  update public.knowledge_documents kd set is_published=coalesce(not new."r16_archived" and kd.revision_id=new."r16_published_revision_id",false)

  from public.knowledge_revisions r where r.id=kd.revision_id and r.source_id=new."r16_id"

    and kd.is_published is distinct from coalesce(not new."r16_archived" and kd.revision_id=new."r16_published_revision_id",false);

  return new;

end$function$
;
CREATE OR REPLACE FUNCTION private.trial_r17_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  parent_limit numeric(12, 2);
  allocated numeric(12, 2);
begin
  if 'monthly_budgets' = 'budgets' then
    select mb.limit_amount
    into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new."r17_user_id" and mb.month = new."r17_month";

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r17_user_id"
      and b.month = new."r17_month"
      and b.id <> coalesce(new."r17_id", -1);

    if allocated + new.amount > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r17_user_id" and b.month = new."r17_month";

    if allocated > new."r17_limit_amount" then
      raise exception 'Overall monthly budget cannot be lower than allocated category limits.'
        using errcode = '23514';
    end if;
  end if;

  new."r17_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r18_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new."r18_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r19_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new."r19_title" = btrim(new."r19_title");
  if new."r19_recurrence_anchor_day" is null then
    new."r19_recurrence_anchor_day" = extract(day from new."r19_due_at")::smallint;
  end if;
  if new."r19_enabled" then
    new."r19_next_trigger_at" = new."r19_due_at" - make_interval(days => new."r19_lead_days");
  else
    new."r19_next_trigger_at" = null;
  end if;
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r19_trigger_1()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new."r19_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r22_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  affected_goal_id uuid;
  authenticated_user_id uuid := (select auth.uid());
  goal_owner_id uuid;
  goal_target numeric(12, 2);
  contribution_total numeric(12, 2);
begin
IF TG_OP='DELETE' THEN IF OLD."r22_id" IS NULL THEN RETURN OLD; END IF; ELSE IF NEW."r22_id" IS NULL THEN RETURN NEW; END IF; END IF;

  affected_goal_id := case when tg_op = 'DELETE' then old."r22_goal_id" else new."r22_goal_id" end;

  select g.user_id, g.target_amount
  into goal_owner_id, goal_target
  from public.savings_goals as g
  where g.id = affected_goal_id
  for update;

  -- A parent can already be gone during ON DELETE CASCADE.
  if not found then
    return null;
  end if;

  if authenticated_user_id is not null and goal_owner_id <> authenticated_user_id then
    raise exception 'Savings goal ownership check failed.';
  end if;

  select coalesce(sum(c.amount), 0)
  into contribution_total
  from public.savings_contributions as c
  where c.goal_id = affected_goal_id;

  if contribution_total > goal_target then
    raise exception 'Contribution exceeds the remaining savings target.';
  end if;

  update public.savings_goals
  set current_amount = contribution_total,
      updated_at = now()
  where id = affected_goal_id;

  return null;
end;
$function$
;
CREATE TEMP TABLE rename_after(LIKE rename_before) ON COMMIT DROP;
INSERT INTO rename_after SELECT 'private.coaching_processing_leases', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM private.coaching_processing_leases x) z;
INSERT INTO rename_after SELECT 'private.financial_backup_snapshots', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM private.financial_backup_snapshots x) z;
INSERT INTO rename_after SELECT 'public.account_access', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.account_access x) z;
INSERT INTO rename_after SELECT 'public.admin_audit_logs', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.admin_audit_logs x) z;
INSERT INTO rename_after SELECT 'public.alerts', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.alerts x) z;
INSERT INTO rename_after SELECT 'public.backups', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.backups x) z;
INSERT INTO rename_after SELECT 'public.budgets', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.budgets x) z;
INSERT INTO rename_after SELECT 'public.categories', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.categories x) z;
INSERT INTO rename_after SELECT 'public.coaching_messages', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.coaching_messages x) z;
INSERT INTO rename_after SELECT 'public.coaching_retrievals', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.coaching_retrievals x) z;
INSERT INTO rename_after SELECT 'public.coaching_sessions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.coaching_sessions x) z;
INSERT INTO rename_after SELECT 'public.data_exports', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.data_exports x) z;
INSERT INTO rename_after SELECT 'public.export_contents', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.export_contents x) z;
INSERT INTO rename_after SELECT 'public.knowledge_documents', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.knowledge_documents x) z;
INSERT INTO rename_after SELECT 'public.knowledge_revisions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.knowledge_revisions x) z;
INSERT INTO rename_after SELECT 'public.knowledge_sources', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.knowledge_sources x) z;
INSERT INTO rename_after SELECT 'public.monthly_budgets', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.monthly_budgets x) z;
INSERT INTO rename_after SELECT 'public.notification_preferences', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.notification_preferences x) z;
INSERT INTO rename_after SELECT 'public.profiles', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.profiles x) z;
INSERT INTO rename_after SELECT 'public.reminders', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.reminders x) z;
INSERT INTO rename_after SELECT 'public.report_attempts', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.report_attempts x) z;
INSERT INTO rename_after SELECT 'public.reports', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.reports x) z;
INSERT INTO rename_after SELECT 'public.savings_contributions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.savings_contributions x) z;
INSERT INTO rename_after SELECT 'public.savings_goals', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.savings_goals x) z;
INSERT INTO rename_after SELECT 'public.transactions', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.transactions x) z;
INSERT INTO rename_after SELECT 'public.user_categories', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.user_categories x) z;
INSERT INTO rename_after SELECT 'public.user_devices', count(*), md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(x) row FROM public.user_devices x) z;
DO $check$ BEGIN IF EXISTS ((SELECT * FROM rename_before EXCEPT SELECT * FROM rename_after) UNION ALL (SELECT * FROM rename_after EXCEPT SELECT * FROM rename_before)) THEN RAISE EXCEPTION 'Data fidelity mismatch'; END IF; END $check$;
DO $check$ BEGIN IF EXISTS (SELECT 1 FROM rename_acl b JOIN pg_class c ON c.oid=b.oid JOIN pg_attribute a ON a.attrelid=b.oid AND a.attnum=b.attnum WHERE b.relacl IS DISTINCT FROM c.relacl OR b.attacl IS DISTINCT FROM a.attacl OR b.relrowsecurity<>c.relrowsecurity OR b.relforcerowsecurity<>c.relforcerowsecurity) THEN RAISE EXCEPTION 'Privileges or RLS changed'; END IF; END $check$;
NOTIFY pgrst, 'reload schema';
COMMIT;
