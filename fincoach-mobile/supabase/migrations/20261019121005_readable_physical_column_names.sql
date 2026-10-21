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
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.account_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r03_user_id','r03_role','r03_status','r03_email','r03_display_name','r03_created_at','r03_last_sign_in_at','r03_updated_at','r04_id','r04_actor_id','r04_action','r04_target_type','r04_target_id','r04_details','r04_created_at','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in account_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.alert_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r05_id','r05_user_id','r05_type','r05_kind','r05_title','r05_message','r05_budget_id','r05_category_limit_id','r05_savings_goal_id','r05_reminder_id','r05_source_data','r05_dedupe_key','r05_scheduled_for','r05_delivered_at','r05_read_at','r05_dismissed_at','r05_delivery_status','r05_delivery_error','r05_delivery_attempt_count','r05_delivery_claimed_at','r05_next_delivery_attempt_at','r05_delivery_receipts','r05_created_at','r19_id','r19_user_id','r19_type','r19_title','r19_amount','r19_due_at','r19_lead_days','r19_recurrence','r19_recurrence_anchor_day','r19_enabled','r19_next_trigger_at','r19_last_triggered_at','r19_created_at','r19_updated_at','r18_user_id','r18_budget_enabled','r18_savings_enabled','r18_savings_lead_days','r18_savings_reminder_time','r18_savings_milestones_enabled','r18_spending_enabled','r18_spending_frequency','r18_spending_weekday','r18_spending_reminder_time','r18_bills_enabled','r18_default_bill_lead_days','r18_default_bill_reminder_time','r18_timezone','r18_created_at','r18_updated_at','r26_id','r26_user_id','r26_expo_push_token','r26_platform','r26_device_name','r26_active','r26_last_seen_at','r26_last_error','r26_created_at','r26_updated_at','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in alert_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.budget_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r17_id','r17_user_id','r17_month','r17_limit_amount','r17_created_at','r17_updated_at','r07_id','r07_user_id','r07_category_id','r07_amount','r07_month','r07_created_at','r07_updated_at','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in budget_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.coaching_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r11_id','r11_user_id','r11_title','r11_created_at','r11_updated_at','r11_last_message_at','r09_id','r09_session_id','r09_user_id','r09_role','r09_content','r09_reply_to_message_id','r09_status','r09_error_code','r09_model','r09_prompt_tokens','r09_completion_tokens','r09_created_at','r09_feedback','r09_ui_payload','r10_id','r10_user_id','r10_assistant_message_id','r10_knowledge_document_id','r10_rank','r10_similarity','r10_title','r10_source','r10_created_at','r01_message_id','r01_token','r01_expires_at','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in coaching_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.export_backup_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r12_id','r12_user_id','r12_format','r12_status','r12_file_name','r12_file_size_bytes','r12_date_from','r12_date_to','r12_completed_at','r12_created_at','r13_export_id','r13_content_type','r06_id','r06_user_id','r06_backup_type','r06_status','r06_file_name','r06_storage_path','r06_file_size_bytes','r06_checksum_sha256','r06_schema_version','r06_last_restore_status','r06_last_restored_at','r06_completed_at','r06_created_at','r06_data_counts','r06_attachment_count','r06_cleanup_warning','r02_backup_id','r02_user_id','r02_data','r02_document','r02_created_at','_record_kind','_owner_id']::text[] THEN RAISE EXCEPTION 'Unexpected columns in export_backup_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.knowledge_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r16_id','r16_source_key','r16_title','r16_archived','r16_published_revision_id','r16_latest_revision_id','r16_created_at','r16_updated_at','r15_id','r15_source_id','r15_title','r15_content','r15_source_urls','r15_checked_at','r15_file_path','r15_status','r15_created_by','r15_created_at','r15_lease_token','r15_lease_until','r15_attempts','r15_chunk_count','r15_error_message','r14_id','r14_title','r14_content','r14_source','r14_embedding','r14_created_at','r14_page_number','r14_chunk_index','r14_content_hash','r14_revision_id','r14_is_published','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in knowledge_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.profiles'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','email','full_name','avatar_url','onboarding_completed','spending_records_consent','university','student_id','monthly_income','monthly_budget','spending_categories','created_at','updated_at','monthly_allowance','year_of_study','income_source','financial_status','coaching_style','auto_backup_enabled']::text[] THEN RAISE EXCEPTION 'Unexpected columns in profiles'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.report_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r21_id','r21_user_id','r21_period','r21_type','r21_generated_at','r21_title','r21_file_name','r21_storage_path','r21_report_key','r21_start_date','r21_end_date','r21_category_id','r20_attempt_id','r20_user_id','r20_message_id','r20_action_id','r20_storage_path','r20_period','r20_report_type','r20_start_date','r20_end_date','r20_category_id','r20_category_name','r20_arguments','r20_status','r20_report_id','r20_lease_expires_at','r20_lease_owner','r20_lease_renewed_at','r20_lease_renewal_count','r20_created_at','r20_updated_at','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in report_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.savings_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r23_id','r23_user_id','r23_name','r23_target_amount','r23_current_amount','r23_created_at','r23_updated_at','r23_deadline','r22_id','r22_goal_id','r22_amount','r22_contributed_on','r22_note','r22_created_at','_record_kind','_owner_id']::text[] THEN RAISE EXCEPTION 'Unexpected columns in savings_records'; END IF; END $check$;
DO $check$ BEGIN IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.transaction_records'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['_row_id','r24_id','r24_user_id','r24_category_id','r24_amount','r24_transaction_date','r24_description','r24_source','r24_receipt_image_path','r24_created_at','r24_updated_at','r24_receipt_items','r08_id','r08_name','r08_type','r08_icon','r08_user_id','r08_color','r08_icon_image_path','r25_user_id','r25_category_id','r25_created_at','_record_kind']::text[] THEN RAISE EXCEPTION 'Unexpected columns in transaction_records'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r24_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r24_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  if not exists (
    select 1
    from public.categories c
    where c.id = new."r24_category_id"
      and (c.user_id is null or c.user_id = new."r24_user_id")
      and c.type in (''expense'', ''income'')
  ) then
    raise exception ''Transaction category is not available to this user.''
      using errcode = ''23503'';
  end if;

  new."r24_source" = btrim(new."r24_source");
  new."r24_description" = nullif(btrim(coalesce(new."r24_description", '''')), '''');
  new."r24_updated_at" = now();
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
  new."r26_updated_at" = now();
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
  IF NEW."r22_goal_id" IS NOT NULL THEN
    SELECT user_id INTO NEW._owner_id FROM "public"."savings_goals" WHERE "id"=NEW."r22_goal_id";
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
  IF NEW."r13_export_id" IS NOT NULL THEN
    SELECT user_id INTO NEW._owner_id FROM "public"."data_exports" WHERE "id"=NEW."r13_export_id";
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
    body := jsonb_build_object(''alertId'', new."r05_id"),
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
    where mb.user_id = new."r07_user_id" and mb.month = new."r07_month";

    if parent_limit is null then
      raise exception ''Create the overall monthly budget before adding category limits.''
        using errcode = ''23514'';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r07_user_id"
      and b.month = new."r07_month"
      and b.id <> coalesce(new."r07_id", -1);

    if allocated + new."r07_amount" > parent_limit then
      raise exception ''Category limits cannot exceed the overall monthly budget.''
        using errcode = ''23514'';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r07_user_id" and b.month = new."r07_month";

    if allocated > new.limit_amount then
      raise exception ''Overall monthly budget cannot be lower than allocated category limits.''
        using errcode = ''23514'';
    end if;
  end if;

  new."r07_updated_at" = now();
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
  new."r11_updated_at" = now();
  return new;
end;
$function$
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r11_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r16_trigger_0()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r16_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$begin

  update public.knowledge_documents kd set is_published=coalesce(not new."r16_archived" and kd.revision_id=new."r16_published_revision_id",false)

  from public.knowledge_revisions r where r.id=kd.revision_id and r.source_id=new."r16_id"

    and kd.is_published is distinct from coalesce(not new."r16_archived" and kd.revision_id=new."r16_published_revision_id",false);

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
    where mb.user_id = new."r17_user_id" and mb.month = new."r17_month";

    if parent_limit is null then
      raise exception ''Create the overall monthly budget before adding category limits.''
        using errcode = ''23514'';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r17_user_id"
      and b.month = new."r17_month"
      and b.id <> coalesce(new."r17_id", -1);

    if allocated + new.amount > parent_limit then
      raise exception ''Category limits cannot exceed the overall monthly budget.''
        using errcode = ''23514'';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."r17_user_id" and b.month = new."r17_month";

    if allocated > new."r17_limit_amount" then
      raise exception ''Overall monthly budget cannot be lower than allocated category limits.''
        using errcode = ''23514'';
    end if;
  end if;

  new."r17_updated_at" = now();
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
  new."r18_updated_at" = now();
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
',chr(13),'') THEN RAISE EXCEPTION 'Function changed since preflight: private.trial_r19_trigger_0()'; END IF; END $check$;
DO $check$ BEGIN IF replace(pg_get_functiondef('private.trial_r19_trigger_1()'::regprocedure),chr(13),'') IS DISTINCT FROM replace('CREATE OR REPLACE FUNCTION private.trial_r19_trigger_1()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''''
AS $function$
begin
  new."r19_updated_at" = now();
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
IF TG_OP=''DELETE'' THEN IF OLD."r22_id" IS NULL THEN RETURN OLD; END IF; ELSE IF NEW."r22_id" IS NULL THEN RETURN NEW; END IF; END IF;

  affected_goal_id := case when tg_op = ''DELETE'' then old."r22_goal_id" else new."r22_goal_id" end;

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
ALTER TABLE public.account_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.account_records RENAME COLUMN "r03_user_id" TO "account_user_id";
ALTER TABLE public.account_records RENAME COLUMN "r03_role" TO "account_role";
ALTER TABLE public.account_records RENAME COLUMN "r03_status" TO "account_status";
ALTER TABLE public.account_records RENAME COLUMN "r03_email" TO "account_email";
ALTER TABLE public.account_records RENAME COLUMN "r03_display_name" TO "account_display_name";
ALTER TABLE public.account_records RENAME COLUMN "r03_created_at" TO "account_created_at";
ALTER TABLE public.account_records RENAME COLUMN "r03_last_sign_in_at" TO "account_last_sign_in_at";
ALTER TABLE public.account_records RENAME COLUMN "r03_updated_at" TO "account_updated_at";
ALTER TABLE public.account_records RENAME COLUMN "r04_id" TO "audit_id";
ALTER TABLE public.account_records RENAME COLUMN "r04_actor_id" TO "audit_actor_id";
ALTER TABLE public.account_records RENAME COLUMN "r04_action" TO "audit_action";
ALTER TABLE public.account_records RENAME COLUMN "r04_target_type" TO "audit_target_type";
ALTER TABLE public.account_records RENAME COLUMN "r04_target_id" TO "audit_target_id";
ALTER TABLE public.account_records RENAME COLUMN "r04_details" TO "audit_details";
ALTER TABLE public.account_records RENAME COLUMN "r04_created_at" TO "audit_created_at";
ALTER TABLE public.account_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.alert_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_id" TO "alert_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_user_id" TO "alert_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_type" TO "alert_type";
ALTER TABLE public.alert_records RENAME COLUMN "r05_kind" TO "alert_kind";
ALTER TABLE public.alert_records RENAME COLUMN "r05_title" TO "alert_title";
ALTER TABLE public.alert_records RENAME COLUMN "r05_message" TO "alert_message";
ALTER TABLE public.alert_records RENAME COLUMN "r05_budget_id" TO "alert_budget_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_category_limit_id" TO "alert_category_limit_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_savings_goal_id" TO "alert_savings_goal_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_reminder_id" TO "alert_reminder_id";
ALTER TABLE public.alert_records RENAME COLUMN "r05_source_data" TO "alert_source_data";
ALTER TABLE public.alert_records RENAME COLUMN "r05_dedupe_key" TO "alert_dedupe_key";
ALTER TABLE public.alert_records RENAME COLUMN "r05_scheduled_for" TO "alert_scheduled_for";
ALTER TABLE public.alert_records RENAME COLUMN "r05_delivered_at" TO "alert_delivered_at";
ALTER TABLE public.alert_records RENAME COLUMN "r05_read_at" TO "alert_read_at";
ALTER TABLE public.alert_records RENAME COLUMN "r05_dismissed_at" TO "alert_dismissed_at";
ALTER TABLE public.alert_records RENAME COLUMN "r05_delivery_status" TO "alert_delivery_status";
ALTER TABLE public.alert_records RENAME COLUMN "r05_delivery_error" TO "alert_delivery_error";
ALTER TABLE public.alert_records RENAME COLUMN "r05_delivery_attempt_count" TO "alert_delivery_attempt_count";
ALTER TABLE public.alert_records RENAME COLUMN "r05_delivery_claimed_at" TO "alert_delivery_claimed_at";
ALTER TABLE public.alert_records RENAME COLUMN "r05_next_delivery_attempt_at" TO "alert_next_delivery_attempt_at";
ALTER TABLE public.alert_records RENAME COLUMN "r05_delivery_receipts" TO "alert_delivery_receipts";
ALTER TABLE public.alert_records RENAME COLUMN "r05_created_at" TO "alert_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "r19_id" TO "reminder_id";
ALTER TABLE public.alert_records RENAME COLUMN "r19_user_id" TO "reminder_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "r19_type" TO "reminder_type";
ALTER TABLE public.alert_records RENAME COLUMN "r19_title" TO "reminder_title";
ALTER TABLE public.alert_records RENAME COLUMN "r19_amount" TO "reminder_amount";
ALTER TABLE public.alert_records RENAME COLUMN "r19_due_at" TO "reminder_due_at";
ALTER TABLE public.alert_records RENAME COLUMN "r19_lead_days" TO "reminder_lead_days";
ALTER TABLE public.alert_records RENAME COLUMN "r19_recurrence" TO "reminder_recurrence";
ALTER TABLE public.alert_records RENAME COLUMN "r19_recurrence_anchor_day" TO "reminder_recurrence_anchor_day";
ALTER TABLE public.alert_records RENAME COLUMN "r19_enabled" TO "reminder_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "r19_next_trigger_at" TO "reminder_next_trigger_at";
ALTER TABLE public.alert_records RENAME COLUMN "r19_last_triggered_at" TO "reminder_last_triggered_at";
ALTER TABLE public.alert_records RENAME COLUMN "r19_created_at" TO "reminder_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "r19_updated_at" TO "reminder_updated_at";
ALTER TABLE public.alert_records RENAME COLUMN "r18_user_id" TO "preference_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "r18_budget_enabled" TO "preference_budget_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "r18_savings_enabled" TO "preference_savings_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "r18_savings_lead_days" TO "preference_savings_lead_days";
ALTER TABLE public.alert_records RENAME COLUMN "r18_savings_reminder_time" TO "preference_savings_reminder_time";
ALTER TABLE public.alert_records RENAME COLUMN "r18_savings_milestones_enabled" TO "preference_savings_milestones_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "r18_spending_enabled" TO "preference_spending_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "r18_spending_frequency" TO "preference_spending_frequency";
ALTER TABLE public.alert_records RENAME COLUMN "r18_spending_weekday" TO "preference_spending_weekday";
ALTER TABLE public.alert_records RENAME COLUMN "r18_spending_reminder_time" TO "preference_spending_reminder_time";
ALTER TABLE public.alert_records RENAME COLUMN "r18_bills_enabled" TO "preference_bills_enabled";
ALTER TABLE public.alert_records RENAME COLUMN "r18_default_bill_lead_days" TO "preference_default_bill_lead_days";
ALTER TABLE public.alert_records RENAME COLUMN "r18_default_bill_reminder_time" TO "preference_default_bill_reminder_time";
ALTER TABLE public.alert_records RENAME COLUMN "r18_timezone" TO "preference_timezone";
ALTER TABLE public.alert_records RENAME COLUMN "r18_created_at" TO "preference_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "r18_updated_at" TO "preference_updated_at";
ALTER TABLE public.alert_records RENAME COLUMN "r26_id" TO "device_id";
ALTER TABLE public.alert_records RENAME COLUMN "r26_user_id" TO "device_user_id";
ALTER TABLE public.alert_records RENAME COLUMN "r26_expo_push_token" TO "device_expo_push_token";
ALTER TABLE public.alert_records RENAME COLUMN "r26_platform" TO "device_platform";
ALTER TABLE public.alert_records RENAME COLUMN "r26_device_name" TO "device_name";
ALTER TABLE public.alert_records RENAME COLUMN "r26_active" TO "device_active";
ALTER TABLE public.alert_records RENAME COLUMN "r26_last_seen_at" TO "device_last_seen_at";
ALTER TABLE public.alert_records RENAME COLUMN "r26_last_error" TO "device_last_error";
ALTER TABLE public.alert_records RENAME COLUMN "r26_created_at" TO "device_created_at";
ALTER TABLE public.alert_records RENAME COLUMN "r26_updated_at" TO "device_updated_at";
ALTER TABLE public.alert_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.budget_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.budget_records RENAME COLUMN "r17_id" TO "monthly_budget_id";
ALTER TABLE public.budget_records RENAME COLUMN "r17_user_id" TO "monthly_budget_user_id";
ALTER TABLE public.budget_records RENAME COLUMN "r17_month" TO "monthly_budget_month";
ALTER TABLE public.budget_records RENAME COLUMN "r17_limit_amount" TO "monthly_budget_limit_amount";
ALTER TABLE public.budget_records RENAME COLUMN "r17_created_at" TO "monthly_budget_created_at";
ALTER TABLE public.budget_records RENAME COLUMN "r17_updated_at" TO "monthly_budget_updated_at";
ALTER TABLE public.budget_records RENAME COLUMN "r07_id" TO "category_limit_id";
ALTER TABLE public.budget_records RENAME COLUMN "r07_user_id" TO "category_limit_user_id";
ALTER TABLE public.budget_records RENAME COLUMN "r07_category_id" TO "category_limit_category_id";
ALTER TABLE public.budget_records RENAME COLUMN "r07_amount" TO "category_limit_amount";
ALTER TABLE public.budget_records RENAME COLUMN "r07_month" TO "category_limit_month";
ALTER TABLE public.budget_records RENAME COLUMN "r07_created_at" TO "category_limit_created_at";
ALTER TABLE public.budget_records RENAME COLUMN "r07_updated_at" TO "category_limit_updated_at";
ALTER TABLE public.budget_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.coaching_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r11_id" TO "session_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r11_user_id" TO "session_user_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r11_title" TO "session_title";
ALTER TABLE public.coaching_records RENAME COLUMN "r11_created_at" TO "session_created_at";
ALTER TABLE public.coaching_records RENAME COLUMN "r11_updated_at" TO "session_updated_at";
ALTER TABLE public.coaching_records RENAME COLUMN "r11_last_message_at" TO "session_last_message_at";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_id" TO "message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_session_id" TO "message_session_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_user_id" TO "message_user_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_role" TO "message_role";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_content" TO "message_content";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_reply_to_message_id" TO "message_reply_to_message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_status" TO "message_status";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_error_code" TO "message_error_code";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_model" TO "message_model";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_prompt_tokens" TO "message_prompt_tokens";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_completion_tokens" TO "message_completion_tokens";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_created_at" TO "message_created_at";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_feedback" TO "message_feedback";
ALTER TABLE public.coaching_records RENAME COLUMN "r09_ui_payload" TO "message_ui_payload";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_id" TO "retrieval_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_user_id" TO "retrieval_user_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_assistant_message_id" TO "retrieval_assistant_message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_knowledge_document_id" TO "retrieval_knowledge_document_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_rank" TO "retrieval_rank";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_similarity" TO "retrieval_similarity";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_title" TO "retrieval_title";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_source" TO "retrieval_source";
ALTER TABLE public.coaching_records RENAME COLUMN "r10_created_at" TO "retrieval_created_at";
ALTER TABLE public.coaching_records RENAME COLUMN "r01_message_id" TO "processing_message_id";
ALTER TABLE public.coaching_records RENAME COLUMN "r01_token" TO "processing_token";
ALTER TABLE public.coaching_records RENAME COLUMN "r01_expires_at" TO "processing_expires_at";
ALTER TABLE public.coaching_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.export_backup_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_id" TO "export_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_user_id" TO "export_user_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_format" TO "export_format";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_status" TO "export_status";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_file_name" TO "export_file_name";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_file_size_bytes" TO "export_file_size_bytes";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_date_from" TO "export_date_from";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_date_to" TO "export_date_to";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_completed_at" TO "export_completed_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "r12_created_at" TO "export_created_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "r13_export_id" TO "export_content_export_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r13_content_type" TO "export_content_content_type";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_id" TO "backup_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_user_id" TO "backup_user_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_backup_type" TO "backup_type";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_status" TO "backup_status";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_file_name" TO "backup_file_name";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_storage_path" TO "backup_storage_path";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_file_size_bytes" TO "backup_file_size_bytes";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_checksum_sha256" TO "backup_checksum_sha256";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_schema_version" TO "backup_schema_version";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_last_restore_status" TO "backup_last_restore_status";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_last_restored_at" TO "backup_last_restored_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_completed_at" TO "backup_completed_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_created_at" TO "backup_created_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_data_counts" TO "backup_data_counts";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_attachment_count" TO "backup_attachment_count";
ALTER TABLE public.export_backup_records RENAME COLUMN "r06_cleanup_warning" TO "backup_cleanup_warning";
ALTER TABLE public.export_backup_records RENAME COLUMN "r02_backup_id" TO "snapshot_backup_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r02_user_id" TO "snapshot_user_id";
ALTER TABLE public.export_backup_records RENAME COLUMN "r02_data" TO "snapshot_data";
ALTER TABLE public.export_backup_records RENAME COLUMN "r02_document" TO "snapshot_document";
ALTER TABLE public.export_backup_records RENAME COLUMN "r02_created_at" TO "snapshot_created_at";
ALTER TABLE public.export_backup_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.export_backup_records RENAME COLUMN "_owner_id" TO "owner_user_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_id" TO "source_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_source_key" TO "source_key";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_title" TO "source_title";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_archived" TO "source_archived";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_published_revision_id" TO "source_published_revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_latest_revision_id" TO "source_latest_revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_created_at" TO "source_created_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "r16_updated_at" TO "source_updated_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_id" TO "revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_source_id" TO "revision_source_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_title" TO "revision_title";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_content" TO "revision_content";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_source_urls" TO "revision_source_urls";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_checked_at" TO "revision_checked_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_file_path" TO "revision_file_path";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_status" TO "revision_status";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_created_by" TO "revision_created_by";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_created_at" TO "revision_created_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_lease_token" TO "revision_lease_token";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_lease_until" TO "revision_lease_until";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_attempts" TO "revision_attempts";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_chunk_count" TO "revision_chunk_count";
ALTER TABLE public.knowledge_records RENAME COLUMN "r15_error_message" TO "revision_error_message";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_id" TO "chunk_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_title" TO "chunk_title";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_content" TO "chunk_content";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_source" TO "chunk_source";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_embedding" TO "chunk_embedding";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_created_at" TO "chunk_created_at";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_page_number" TO "chunk_page_number";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_chunk_index" TO "chunk_index";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_content_hash" TO "chunk_content_hash";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_revision_id" TO "chunk_revision_id";
ALTER TABLE public.knowledge_records RENAME COLUMN "r14_is_published" TO "chunk_is_published";
ALTER TABLE public.knowledge_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.report_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.report_records RENAME COLUMN "r21_id" TO "report_id";
ALTER TABLE public.report_records RENAME COLUMN "r21_user_id" TO "report_user_id";
ALTER TABLE public.report_records RENAME COLUMN "r21_period" TO "report_period";
ALTER TABLE public.report_records RENAME COLUMN "r21_type" TO "report_type";
ALTER TABLE public.report_records RENAME COLUMN "r21_generated_at" TO "report_generated_at";
ALTER TABLE public.report_records RENAME COLUMN "r21_title" TO "report_title";
ALTER TABLE public.report_records RENAME COLUMN "r21_file_name" TO "report_file_name";
ALTER TABLE public.report_records RENAME COLUMN "r21_storage_path" TO "report_storage_path";
ALTER TABLE public.report_records RENAME COLUMN "r21_report_key" TO "report_key";
ALTER TABLE public.report_records RENAME COLUMN "r21_start_date" TO "report_start_date";
ALTER TABLE public.report_records RENAME COLUMN "r21_end_date" TO "report_end_date";
ALTER TABLE public.report_records RENAME COLUMN "r21_category_id" TO "report_category_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_attempt_id" TO "report_attempt_attempt_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_user_id" TO "report_attempt_user_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_message_id" TO "report_attempt_message_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_action_id" TO "report_attempt_action_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_storage_path" TO "report_attempt_storage_path";
ALTER TABLE public.report_records RENAME COLUMN "r20_period" TO "report_attempt_period";
ALTER TABLE public.report_records RENAME COLUMN "r20_report_type" TO "report_attempt_report_type";
ALTER TABLE public.report_records RENAME COLUMN "r20_start_date" TO "report_attempt_start_date";
ALTER TABLE public.report_records RENAME COLUMN "r20_end_date" TO "report_attempt_end_date";
ALTER TABLE public.report_records RENAME COLUMN "r20_category_id" TO "report_attempt_category_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_category_name" TO "report_attempt_category_name";
ALTER TABLE public.report_records RENAME COLUMN "r20_arguments" TO "report_attempt_arguments";
ALTER TABLE public.report_records RENAME COLUMN "r20_status" TO "report_attempt_status";
ALTER TABLE public.report_records RENAME COLUMN "r20_report_id" TO "report_attempt_report_id";
ALTER TABLE public.report_records RENAME COLUMN "r20_lease_expires_at" TO "report_attempt_lease_expires_at";
ALTER TABLE public.report_records RENAME COLUMN "r20_lease_owner" TO "report_attempt_lease_owner";
ALTER TABLE public.report_records RENAME COLUMN "r20_lease_renewed_at" TO "report_attempt_lease_renewed_at";
ALTER TABLE public.report_records RENAME COLUMN "r20_lease_renewal_count" TO "report_attempt_lease_renewal_count";
ALTER TABLE public.report_records RENAME COLUMN "r20_created_at" TO "report_attempt_created_at";
ALTER TABLE public.report_records RENAME COLUMN "r20_updated_at" TO "report_attempt_updated_at";
ALTER TABLE public.report_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.savings_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.savings_records RENAME COLUMN "r23_id" TO "goal_id";
ALTER TABLE public.savings_records RENAME COLUMN "r23_user_id" TO "goal_user_id";
ALTER TABLE public.savings_records RENAME COLUMN "r23_name" TO "goal_name";
ALTER TABLE public.savings_records RENAME COLUMN "r23_target_amount" TO "goal_target_amount";
ALTER TABLE public.savings_records RENAME COLUMN "r23_current_amount" TO "goal_current_amount";
ALTER TABLE public.savings_records RENAME COLUMN "r23_created_at" TO "goal_created_at";
ALTER TABLE public.savings_records RENAME COLUMN "r23_updated_at" TO "goal_updated_at";
ALTER TABLE public.savings_records RENAME COLUMN "r23_deadline" TO "goal_deadline";
ALTER TABLE public.savings_records RENAME COLUMN "r22_id" TO "contribution_id";
ALTER TABLE public.savings_records RENAME COLUMN "r22_goal_id" TO "contribution_goal_id";
ALTER TABLE public.savings_records RENAME COLUMN "r22_amount" TO "contribution_amount";
ALTER TABLE public.savings_records RENAME COLUMN "r22_contributed_on" TO "contribution_contributed_on";
ALTER TABLE public.savings_records RENAME COLUMN "r22_note" TO "contribution_note";
ALTER TABLE public.savings_records RENAME COLUMN "r22_created_at" TO "contribution_created_at";
ALTER TABLE public.savings_records RENAME COLUMN "_record_kind" TO "record_type";
ALTER TABLE public.savings_records RENAME COLUMN "_owner_id" TO "owner_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "_row_id" TO "record_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_id" TO "transaction_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_user_id" TO "transaction_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_category_id" TO "transaction_category_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_amount" TO "transaction_amount";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_transaction_date" TO "transaction_date";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_description" TO "transaction_description";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_source" TO "transaction_source";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_receipt_image_path" TO "transaction_receipt_image_path";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_created_at" TO "transaction_created_at";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_updated_at" TO "transaction_updated_at";
ALTER TABLE public.transaction_records RENAME COLUMN "r24_receipt_items" TO "transaction_receipt_items";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_id" TO "category_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_name" TO "category_name";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_type" TO "category_type";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_icon" TO "category_icon";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_user_id" TO "category_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_color" TO "category_color";
ALTER TABLE public.transaction_records RENAME COLUMN "r08_icon_image_path" TO "category_icon_image_path";
ALTER TABLE public.transaction_records RENAME COLUMN "r25_user_id" TO "selected_category_user_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r25_category_id" TO "selected_category_category_id";
ALTER TABLE public.transaction_records RENAME COLUMN "r25_created_at" TO "selected_category_created_at";
ALTER TABLE public.transaction_records RENAME COLUMN "_record_kind" TO "record_type";
CREATE OR REPLACE FUNCTION private.trial_r24_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if not exists (
    select 1
    from public.categories c
    where c.id = new."transaction_category_id"
      and (c.user_id is null or c.user_id = new."transaction_user_id")
      and c.type in ('expense', 'income')
  ) then
    raise exception 'Transaction category is not available to this user.'
      using errcode = '23503';
  end if;

  new."transaction_source" = btrim(new."transaction_source");
  new."transaction_description" = nullif(btrim(coalesce(new."transaction_description", '')), '');
  new."transaction_updated_at" = now();
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
  new."device_updated_at" = now();
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
  IF NEW."contribution_goal_id" IS NOT NULL THEN
    SELECT user_id INTO NEW.owner_user_id FROM "public"."savings_goals" WHERE "id"=NEW."contribution_goal_id";
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
  IF NEW."export_content_export_id" IS NOT NULL THEN
    SELECT user_id INTO NEW.owner_user_id FROM "public"."data_exports" WHERE "id"=NEW."export_content_export_id";
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
    body := jsonb_build_object('alertId', new."alert_id"),
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
    where mb.user_id = new."category_limit_user_id" and mb.month = new."category_limit_month";

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."category_limit_user_id"
      and b.month = new."category_limit_month"
      and b.id <> coalesce(new."category_limit_id", -1);

    if allocated + new."category_limit_amount" > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."category_limit_user_id" and b.month = new."category_limit_month";

    if allocated > new.limit_amount then
      raise exception 'Overall monthly budget cannot be lower than allocated category limits.'
        using errcode = '23514';
    end if;
  end if;

  new."category_limit_updated_at" = now();
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
  new."session_updated_at" = now();
  return new;
end;
$function$
;
CREATE OR REPLACE FUNCTION private.trial_r16_trigger_0()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$begin

  update public.knowledge_documents kd set is_published=coalesce(not new."source_archived" and kd.revision_id=new."source_published_revision_id",false)

  from public.knowledge_revisions r where r.id=kd.revision_id and r.source_id=new."source_id"

    and kd.is_published is distinct from coalesce(not new."source_archived" and kd.revision_id=new."source_published_revision_id",false);

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
    where mb.user_id = new."monthly_budget_user_id" and mb.month = new."monthly_budget_month";

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."monthly_budget_user_id"
      and b.month = new."monthly_budget_month"
      and b.id <> coalesce(new."monthly_budget_id", -1);

    if allocated + new.amount > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new."monthly_budget_user_id" and b.month = new."monthly_budget_month";

    if allocated > new."monthly_budget_limit_amount" then
      raise exception 'Overall monthly budget cannot be lower than allocated category limits.'
        using errcode = '23514';
    end if;
  end if;

  new."monthly_budget_updated_at" = now();
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
  new."preference_updated_at" = now();
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
;
CREATE OR REPLACE FUNCTION private.trial_r19_trigger_1()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new."reminder_updated_at" = now();
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
IF TG_OP='DELETE' THEN IF OLD."contribution_id" IS NULL THEN RETURN OLD; END IF; ELSE IF NEW."contribution_id" IS NULL THEN RETURN NEW; END IF; END IF;

  affected_goal_id := case when tg_op = 'DELETE' then old."contribution_goal_id" else new."contribution_goal_id" end;

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
