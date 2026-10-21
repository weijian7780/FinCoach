-- Inverse of 20261019082834_consolidate_dfd_application_stores.sql.

-- Preserves current data through compatibility views; test on a restored copy before use.

-- Application writes must be quiesced. Reconcile Supabase migration history after a successful rollback.

BEGIN;

SET LOCAL lock_timeout='5s';

SET LOCAL check_function_bodies=false;

SET LOCAL search_path=public,extensions,pg_catalog;

LOCK TABLE "public"."account_records","public"."alert_records","public"."budget_records","public"."coaching_records","public"."export_backup_records","public"."knowledge_records","public"."profiles","public"."report_records","public"."savings_records","public"."transaction_records" IN ACCESS EXCLUSIVE MODE;

CREATE TEMP TABLE rollback_sequences(name text,value bigint,called boolean) ON COMMIT DROP;

CREATE TEMP TABLE rollback_rows_0 ON COMMIT DROP AS SELECT * FROM "private"."coaching_processing_leases";

CREATE TEMP TABLE rollback_rows_1 ON COMMIT DROP AS SELECT * FROM "private"."financial_backup_snapshots";

CREATE TEMP TABLE rollback_rows_2 ON COMMIT DROP AS SELECT * FROM "public"."account_access";

CREATE TEMP TABLE rollback_rows_3 ON COMMIT DROP AS SELECT * FROM "public"."admin_audit_logs";

INSERT INTO rollback_sequences SELECT 'public.admin_audit_logs_id_seq',last_value,is_called FROM public.admin_audit_logs_id_seq;

CREATE TEMP TABLE rollback_rows_4 ON COMMIT DROP AS SELECT * FROM "public"."alerts";

CREATE TEMP TABLE rollback_rows_5 ON COMMIT DROP AS SELECT * FROM "public"."backups";

CREATE TEMP TABLE rollback_rows_6 ON COMMIT DROP AS SELECT * FROM "public"."budgets";

INSERT INTO rollback_sequences SELECT 'public.budgets_id_seq',last_value,is_called FROM public.budgets_id_seq;

CREATE TEMP TABLE rollback_rows_7 ON COMMIT DROP AS SELECT * FROM "public"."categories";

INSERT INTO rollback_sequences SELECT 'public.categories_id_seq',last_value,is_called FROM public.categories_id_seq;

CREATE TEMP TABLE rollback_rows_8 ON COMMIT DROP AS SELECT * FROM "public"."coaching_messages";

CREATE TEMP TABLE rollback_rows_9 ON COMMIT DROP AS SELECT * FROM "public"."coaching_retrievals";

INSERT INTO rollback_sequences SELECT 'public.coaching_retrievals_id_seq',last_value,is_called FROM public.coaching_retrievals_id_seq;

CREATE TEMP TABLE rollback_rows_10 ON COMMIT DROP AS SELECT * FROM "public"."coaching_sessions";

CREATE TEMP TABLE rollback_rows_11 ON COMMIT DROP AS SELECT * FROM "public"."data_exports";

CREATE TEMP TABLE rollback_rows_12 ON COMMIT DROP AS SELECT * FROM "public"."export_contents";

CREATE TEMP TABLE rollback_rows_13 ON COMMIT DROP AS SELECT * FROM "public"."knowledge_documents";

INSERT INTO rollback_sequences SELECT 'public.knowledge_documents_id_seq',last_value,is_called FROM public.knowledge_documents_id_seq;

CREATE TEMP TABLE rollback_rows_14 ON COMMIT DROP AS SELECT * FROM "public"."knowledge_revisions";

CREATE TEMP TABLE rollback_rows_15 ON COMMIT DROP AS SELECT * FROM "public"."knowledge_sources";

CREATE TEMP TABLE rollback_rows_16 ON COMMIT DROP AS SELECT * FROM "public"."monthly_budgets";

CREATE TEMP TABLE rollback_rows_17 ON COMMIT DROP AS SELECT * FROM "public"."notification_preferences";

CREATE TEMP TABLE rollback_rows_18 ON COMMIT DROP AS SELECT * FROM "public"."reminders";

CREATE TEMP TABLE rollback_rows_19 ON COMMIT DROP AS SELECT * FROM "public"."report_attempts";

CREATE TEMP TABLE rollback_rows_20 ON COMMIT DROP AS SELECT * FROM "public"."reports";

INSERT INTO rollback_sequences SELECT 'public.reports_id_seq',last_value,is_called FROM public.reports_id_seq;

CREATE TEMP TABLE rollback_rows_21 ON COMMIT DROP AS SELECT * FROM "public"."savings_contributions";

INSERT INTO rollback_sequences SELECT 'public.savings_contributions_id_seq',last_value,is_called FROM public.savings_contributions_id_seq;

CREATE TEMP TABLE rollback_rows_22 ON COMMIT DROP AS SELECT * FROM "public"."savings_goals";

CREATE TEMP TABLE rollback_rows_23 ON COMMIT DROP AS SELECT * FROM "public"."transactions";

CREATE TEMP TABLE rollback_rows_24 ON COMMIT DROP AS SELECT * FROM "public"."user_categories";

CREATE TEMP TABLE rollback_rows_25 ON COMMIT DROP AS SELECT * FROM "public"."user_devices";

DROP TABLE "public"."account_records","public"."alert_records","public"."budget_records","public"."coaching_records","public"."export_backup_records","public"."knowledge_records","public"."report_records","public"."savings_records","public"."transaction_records" CASCADE;

CREATE TABLE "private"."coaching_processing_leases" ("message_id" uuid NOT NULL,
"token" uuid NOT NULL,
"expires_at" timestamp with time zone NOT NULL);

ALTER TABLE "private"."coaching_processing_leases" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "private"."coaching_processing_leases" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "private"."financial_backup_snapshots" ("backup_id" uuid NOT NULL,
"user_id" uuid NOT NULL,
"data" jsonb NOT NULL,
"document" jsonb,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "private"."financial_backup_snapshots" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "private"."financial_backup_snapshots" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."account_access" ("user_id" uuid NOT NULL,
"role" text DEFAULT 'student'::text NOT NULL,
"status" text DEFAULT 'active'::text NOT NULL,
"email" text,
"display_name" text,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"last_sign_in_at" timestamp with time zone,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."account_access" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."account_access" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."admin_audit_logs" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.admin_audit_logs_id_seq) NOT NULL,
"actor_id" uuid,
"action" text NOT NULL,
"target_type" text NOT NULL,
"target_id" text NOT NULL,
"details" jsonb DEFAULT '{}'::jsonb NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."admin_audit_logs" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."admin_audit_logs" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."alerts" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"type" text NOT NULL,
"kind" text DEFAULT 'alert'::text NOT NULL,
"title" text NOT NULL,
"message" text NOT NULL,
"budget_id" uuid,
"category_limit_id" bigint,
"savings_goal_id" uuid,
"reminder_id" uuid,
"source_data" jsonb DEFAULT '{}'::jsonb NOT NULL,
"dedupe_key" text NOT NULL,
"scheduled_for" timestamp with time zone,
"delivered_at" timestamp with time zone,
"read_at" timestamp with time zone,
"dismissed_at" timestamp with time zone,
"delivery_status" text DEFAULT 'pending'::text NOT NULL,
"delivery_error" text,
"delivery_attempt_count" smallint DEFAULT 0 NOT NULL,
"delivery_claimed_at" timestamp with time zone,
"next_delivery_attempt_at" timestamp with time zone,
"delivery_receipts" jsonb DEFAULT '{}'::jsonb NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."alerts" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."alerts" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."backups" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"backup_type" text NOT NULL,
"status" text NOT NULL,
"file_name" text NOT NULL,
"storage_path" text,
"file_size_bytes" bigint,
"checksum_sha256" text,
"schema_version" integer DEFAULT 1 NOT NULL,
"last_restore_status" text,
"last_restored_at" timestamp with time zone,
"completed_at" timestamp with time zone,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"data_counts" jsonb,
"attachment_count" integer DEFAULT 0 NOT NULL,
"cleanup_warning" text);

ALTER TABLE "public"."backups" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."backups" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."budgets" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.budgets_id_seq) NOT NULL,
"user_id" uuid NOT NULL,
"category_id" bigint NOT NULL,
"amount" numeric(12,2) NOT NULL,
"month" date NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."budgets" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."budgets" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."categories" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.categories_id_seq) NOT NULL,
"name" text NOT NULL,
"type" text DEFAULT 'expense'::text NOT NULL,
"icon" text,
"user_id" uuid,
"color" text,
"icon_image_path" text);

ALTER TABLE "public"."categories" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."categories" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."coaching_messages" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"session_id" uuid NOT NULL,
"user_id" uuid NOT NULL,
"role" text NOT NULL,
"content" text NOT NULL,
"reply_to_message_id" uuid,
"status" text DEFAULT 'completed'::text NOT NULL,
"error_code" text,
"model" text,
"prompt_tokens" integer,
"completion_tokens" integer,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"feedback" text,
"ui_payload" jsonb DEFAULT '{}'::jsonb NOT NULL);

ALTER TABLE "public"."coaching_messages" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."coaching_messages" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."coaching_retrievals" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.coaching_retrievals_id_seq) NOT NULL,
"user_id" uuid NOT NULL,
"assistant_message_id" uuid NOT NULL,
"knowledge_document_id" bigint,
"rank" smallint NOT NULL,
"similarity" double precision NOT NULL,
"title" text,
"source" text,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."coaching_retrievals" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."coaching_retrievals" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."coaching_sessions" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"title" text DEFAULT 'New conversation'::text NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
"last_message_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."coaching_sessions" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."coaching_sessions" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."data_exports" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"format" text NOT NULL,
"status" text NOT NULL,
"file_name" text NOT NULL,
"file_size_bytes" bigint,
"date_from" date NOT NULL,
"date_to" date NOT NULL,
"completed_at" timestamp with time zone,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."data_exports" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."data_exports" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."export_contents" ("export_id" uuid NOT NULL,
"content_type" text NOT NULL);

ALTER TABLE "public"."export_contents" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."export_contents" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."knowledge_documents" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.knowledge_documents_id_seq) NOT NULL,
"title" text,
"content" text NOT NULL,
"source" text,
"embedding" public.vector(1024) NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"page_number" integer,
"chunk_index" integer,
"content_hash" text,
"revision_id" uuid NOT NULL,
"is_published" boolean DEFAULT false NOT NULL);

ALTER TABLE "public"."knowledge_documents" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."knowledge_documents" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."knowledge_revisions" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"source_id" uuid NOT NULL,
"title" text NOT NULL,
"content" text NOT NULL,
"source_urls" jsonb DEFAULT '[]'::jsonb NOT NULL,
"checked_at" date,
"file_path" text,
"status" text DEFAULT 'draft'::text NOT NULL,
"created_by" uuid,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"lease_token" uuid,
"lease_until" timestamp with time zone,
"attempts" integer DEFAULT 0 NOT NULL,
"chunk_count" integer DEFAULT 0 NOT NULL,
"error_message" text);

ALTER TABLE "public"."knowledge_revisions" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."knowledge_revisions" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."knowledge_sources" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"source_key" text NOT NULL,
"title" text NOT NULL,
"archived" boolean DEFAULT false NOT NULL,
"published_revision_id" uuid,
"latest_revision_id" uuid,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."knowledge_sources" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."knowledge_sources" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."monthly_budgets" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"month" date NOT NULL,
"limit_amount" numeric(12,2) NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."monthly_budgets" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."monthly_budgets" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."notification_preferences" ("user_id" uuid NOT NULL,
"budget_enabled" boolean DEFAULT true NOT NULL,
"savings_enabled" boolean DEFAULT true NOT NULL,
"savings_lead_days" smallint DEFAULT 7 NOT NULL,
"savings_reminder_time" time without time zone DEFAULT '09:00:00'::time without time zone NOT NULL,
"savings_milestones_enabled" boolean DEFAULT true NOT NULL,
"spending_enabled" boolean DEFAULT true NOT NULL,
"spending_frequency" text DEFAULT 'weekly'::text NOT NULL,
"spending_weekday" smallint,
"spending_reminder_time" time without time zone DEFAULT '20:00:00'::time without time zone NOT NULL,
"bills_enabled" boolean DEFAULT true NOT NULL,
"default_bill_lead_days" smallint DEFAULT 3 NOT NULL,
"default_bill_reminder_time" time without time zone DEFAULT '09:00:00'::time without time zone NOT NULL,
"timezone" text DEFAULT 'Asia/Kuala_Lumpur'::text NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."notification_preferences" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."notification_preferences" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."reminders" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"type" text DEFAULT 'bill'::text NOT NULL,
"title" text NOT NULL,
"amount" numeric(12,2),
"due_at" timestamp with time zone NOT NULL,
"lead_days" smallint DEFAULT 3 NOT NULL,
"recurrence" text DEFAULT 'none'::text NOT NULL,
"recurrence_anchor_day" smallint NOT NULL,
"enabled" boolean DEFAULT true NOT NULL,
"next_trigger_at" timestamp with time zone,
"last_triggered_at" timestamp with time zone,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."reminders" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."reminders" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."report_attempts" ("attempt_id" uuid NOT NULL,
"user_id" uuid NOT NULL,
"message_id" uuid NOT NULL,
"action_id" uuid NOT NULL,
"storage_path" text NOT NULL,
"period" text NOT NULL,
"report_type" text NOT NULL,
"start_date" date NOT NULL,
"end_date" date NOT NULL,
"category_id" bigint,
"category_name" text,
"arguments" jsonb DEFAULT '{}'::jsonb NOT NULL,
"status" text DEFAULT 'active'::text NOT NULL,
"report_id" bigint,
"lease_expires_at" timestamp with time zone NOT NULL,
"lease_owner" uuid,
"lease_renewed_at" timestamp with time zone,
"lease_renewal_count" integer DEFAULT 0 NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."report_attempts" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."report_attempts" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."reports" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.reports_id_seq) NOT NULL,
"user_id" uuid NOT NULL,
"period" text NOT NULL,
"type" text NOT NULL,
"generated_at" timestamp with time zone DEFAULT now() NOT NULL,
"title" text,
"file_name" text,
"storage_path" text,
"report_key" text,
"start_date" date,
"end_date" date,
"category_id" bigint);

ALTER TABLE "public"."reports" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."reports" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."savings_contributions" ("id" bigint GENERATED ALWAYS AS IDENTITY (SEQUENCE NAME public.savings_contributions_id_seq) NOT NULL,
"goal_id" uuid NOT NULL,
"amount" numeric(12,2) NOT NULL,
"contributed_on" date DEFAULT CURRENT_DATE NOT NULL,
"note" text,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."savings_contributions" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."savings_contributions" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."savings_goals" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"name" text NOT NULL,
"target_amount" numeric(12,2) NOT NULL,
"current_amount" numeric(12,2) DEFAULT 0 NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
"deadline" date);

ALTER TABLE "public"."savings_goals" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."savings_goals" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."transactions" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"category_id" bigint NOT NULL,
"amount" numeric(12,2) NOT NULL,
"transaction_date" date NOT NULL,
"description" text,
"source" text NOT NULL,
"receipt_image_path" text,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
"receipt_items" jsonb DEFAULT '[]'::jsonb NOT NULL);

ALTER TABLE "public"."transactions" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."transactions" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."user_categories" ("user_id" uuid NOT NULL,
"category_id" bigint NOT NULL,
"created_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."user_categories" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."user_categories" FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE "public"."user_devices" ("id" uuid DEFAULT gen_random_uuid() NOT NULL,
"user_id" uuid NOT NULL,
"expo_push_token" text NOT NULL,
"platform" text NOT NULL,
"device_name" text,
"active" boolean DEFAULT true NOT NULL,
"last_seen_at" timestamp with time zone DEFAULT now() NOT NULL,
"last_error" text,
"created_at" timestamp with time zone DEFAULT now() NOT NULL,
"updated_at" timestamp with time zone DEFAULT now() NOT NULL);

ALTER TABLE "public"."user_devices" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."user_devices" FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.handle_new_user_profile()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
begin
  insert into public.profiles (id, email, full_name, avatar_url)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    new.raw_user_meta_data ->> 'avatar_url'
  )
  on conflict (id) do nothing;
  return new;
end;
$function$
;

REVOKE ALL ON FUNCTION private.handle_new_user_profile() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.is_active_account()
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists(select 1 from public.account_access where user_id=auth.uid() and status='active');
$function$
;

REVOKE ALL ON FUNCTION private.is_active_account() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.notify_inserted_alert()
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
    body := jsonb_build_object('alertId', new.id),
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

REVOKE ALL ON FUNCTION private.notify_inserted_alert() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.refresh_reminder_schedule()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.title = btrim(new.title);
  if new.recurrence_anchor_day is null then
    new.recurrence_anchor_day = extract(day from new.due_at)::smallint;
  end if;
  if new.enabled then
    new.next_trigger_at = new.due_at - make_interval(days => new.lead_days);
  else
    new.next_trigger_at = null;
  end if;
  return new;
end;
$function$
;

REVOKE ALL ON FUNCTION private.refresh_reminder_schedule() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.refresh_savings_goal_amount()
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
  affected_goal_id := case when tg_op = 'DELETE' then old.goal_id else new.goal_id end;

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

REVOKE ALL ON FUNCTION private.refresh_savings_goal_amount() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.require_admin(p_actor uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if not exists(select 1 from public.account_access where user_id=p_actor and role='admin' and status='active') then raise exception 'ADMIN_FORBIDDEN' using errcode='42501'; end if;
end $function$
;

REVOKE ALL ON FUNCTION private.require_admin(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.restore_financial_backup_v1(payload jsonb, backup_record_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  owner_id uuid := (select auth.uid());
  profile_data jsonb := payload -> 'data' -> 'profile';
  selected_categories jsonb;
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text, 20261010));
  perform private.validate_financial_backup_data(payload -> 'data', owner_id);
  if coalesce((payload ->> 'schemaVersion')::integer, 0) <> 1 then
    raise exception 'Unsupported backup schema.';
  end if;
  if payload ->> 'userId' <> owner_id::text then raise exception 'Backup owner mismatch.'; end if;
  if not exists (
    select 1 from public.backups b
    where b.id = backup_record_id and b.user_id = owner_id and b.status = 'completed'
  ) then raise exception 'Completed backup not found.'; end if;

  -- New backups capture tracked categories. Older v1 backups did not, so keep
  -- the current selections whose categories still exist in the restored data.
  if (payload -> 'data') ? 'userCategories' then
    selected_categories := payload -> 'data' -> 'userCategories';
    if jsonb_typeof(selected_categories) is distinct from 'array' then
      raise exception 'Invalid tracked categories in backup.';
    end if;
  else
    select coalesce(jsonb_agg(to_jsonb(uc)), '[]'::jsonb)
      into selected_categories
    from public.user_categories uc where uc.user_id = owner_id;
  end if;
  if exists (
    select 1 from jsonb_to_recordset(selected_categories)
      as x(user_id uuid, category_id bigint)
    where x.user_id is distinct from owner_id or x.category_id is null
  ) then raise exception 'Invalid tracked category owner in backup.'; end if;

  update public.backups set last_restore_status = 'processing'
  where id = backup_record_id and user_id = owner_id;

  delete from public.alerts where user_id = owner_id;
  delete from public.reminders where user_id = owner_id;
  delete from public.notification_preferences where user_id = owner_id;
  delete from public.transactions where user_id = owner_id;
  delete from public.budgets where user_id = owner_id;
  delete from public.monthly_budgets where user_id = owner_id;
  delete from public.savings_contributions
  where goal_id in (select id from public.savings_goals where user_id = owner_id);
  delete from public.savings_goals where user_id = owner_id;
  delete from public.reports where user_id = owner_id;
  delete from public.user_categories where user_id = owner_id;
  delete from public.categories where user_id = owner_id;

  if profile_data is not null and profile_data <> 'null'::jsonb then
    update public.profiles
    set full_name = profile_data ->> 'full_name',
        avatar_url = profile_data ->> 'avatar_url',
        monthly_allowance = nullif(profile_data ->> 'monthly_allowance', '')::numeric,
        university = coalesce(profile_data ->> 'university', university),
        year_of_study = profile_data ->> 'year_of_study',
        income_source = profile_data ->> 'income_source',
        financial_status = profile_data ->> 'financial_status',
        coaching_style = profile_data ->> 'coaching_style',
        onboarding_completed = coalesce((profile_data ->> 'onboarding_completed')::boolean, onboarding_completed),
        updated_at = now()
    where id = owner_id;
  end if;

  insert into public.categories (id, name, type, icon, icon_image_path, user_id, color)
  overriding system value
  select id, name, type, icon, icon_image_path, owner_id, color
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb))
    as x(id bigint, name text, type text, icon text, icon_image_path text, user_id uuid, color text);

  -- Validate new snapshots against visible categories. The definer function
  -- must not allow a supplied category ID to link to another account's data.
  if (payload -> 'data') ? 'userCategories' and exists (
    select 1 from jsonb_to_recordset(selected_categories) as x(category_id bigint)
    left join public.categories c on c.id = x.category_id
    where c.id is null or (c.user_id is not null and c.user_id <> owner_id)
  ) then raise exception 'Tracked category is not available to this account.'; end if;

  insert into public.user_categories (user_id, category_id, created_at)
  select owner_id, x.category_id, coalesce(x.created_at, now())
  from jsonb_to_recordset(selected_categories) as x(category_id bigint, created_at timestamptz)
  join public.categories c on c.id = x.category_id
  where c.user_id is null or c.user_id = owner_id;

  insert into public.monthly_budgets (id, user_id, month, limit_amount, created_at, updated_at)
  select id, owner_id, month, limit_amount, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb))
    as x(id uuid, user_id uuid, month date, limit_amount numeric, created_at timestamptz, updated_at timestamptz);

  insert into public.budgets (id, user_id, category_id, amount, month, created_at, updated_at)
  overriding system value
  select id, owner_id, category_id, amount, month, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb))
    as x(id bigint, user_id uuid, category_id bigint, amount numeric, month date, created_at timestamptz, updated_at timestamptz);

  insert into public.savings_goals (id, user_id, name, target_amount, current_amount, deadline, created_at, updated_at)
  select id, owner_id, name, target_amount, 0, deadline, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb))
    as x(id uuid, user_id uuid, name text, target_amount numeric, current_amount numeric, deadline date, created_at timestamptz, updated_at timestamptz);

  insert into public.savings_contributions (id, goal_id, amount, contributed_on, note, created_at)
  overriding system value
  select id, goal_id, amount, contributed_on, note, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb))
    as x(id bigint, goal_id uuid, amount numeric, contributed_on date, note text, created_at timestamptz);

  insert into public.transactions (
    id, user_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, receipt_items, created_at, updated_at
  )
  select id, owner_id, category_id, amount, transaction_date, description,
    source, receipt_image_path, coalesce(receipt_items, '[]'::jsonb), created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb))
    as x(id uuid, user_id uuid, category_id bigint, amount numeric, transaction_date date,
      description text, source text, receipt_image_path text, receipt_items jsonb, created_at timestamptz, updated_at timestamptz);

  -- Restore PDF metadata as well as the history row so existing stored files
  -- remain reachable from the report screen after a restore.
  insert into public.reports (
    id, user_id, period, type, generated_at, title, file_name, storage_path,
    report_key, start_date, end_date, category_id
  )
  overriding system value
  select id, owner_id, period, type, generated_at, title, file_name, storage_path,
    report_key, start_date, end_date, category_id
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb))
    as x(id bigint, user_id uuid, period text, type text, generated_at timestamptz,
      title text, file_name text, storage_path text, report_key text,
      start_date date, end_date date, category_id bigint);

  insert into public.notification_preferences (
    user_id, budget_enabled, savings_enabled, savings_lead_days, savings_reminder_time,
    savings_milestones_enabled, spending_enabled, spending_frequency, spending_weekday,
    spending_reminder_time, bills_enabled, default_bill_lead_days,
    default_bill_reminder_time, timezone, created_at, updated_at
  )
  select owner_id, budget_enabled, savings_enabled, savings_lead_days, savings_reminder_time,
    savings_milestones_enabled, spending_enabled, spending_frequency, spending_weekday,
    spending_reminder_time, bills_enabled, default_bill_lead_days,
    default_bill_reminder_time, timezone, created_at, updated_at
  from jsonb_to_record(coalesce(payload -> 'data' -> 'notificationPreferences', '{}'::jsonb))
    as x(user_id uuid, budget_enabled boolean, savings_enabled boolean, savings_lead_days smallint,
      savings_reminder_time time, savings_milestones_enabled boolean, spending_enabled boolean,
      spending_frequency text, spending_weekday smallint, spending_reminder_time time,
      bills_enabled boolean, default_bill_lead_days smallint, default_bill_reminder_time time,
      timezone text, created_at timestamptz, updated_at timestamptz)
  where payload -> 'data' -> 'notificationPreferences' is not null
    and payload -> 'data' -> 'notificationPreferences' <> 'null'::jsonb;

  insert into public.reminders (
    id, user_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at, created_at, updated_at
  )
  select id, owner_id, type, title, amount, due_at, lead_days, recurrence,
    recurrence_anchor_day, enabled, next_trigger_at, last_triggered_at, created_at, updated_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb))
    as x(id uuid, user_id uuid, type text, title text, amount numeric, due_at timestamptz,
      lead_days smallint, recurrence text, recurrence_anchor_day smallint, enabled boolean,
      next_trigger_at timestamptz, last_triggered_at timestamptz, created_at timestamptz, updated_at timestamptz);

  insert into public.alerts (
    id, user_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for, delivered_at,
    read_at, dismissed_at, delivery_status, delivery_error, delivery_attempt_count,
    delivery_claimed_at, next_delivery_attempt_at, delivery_receipts, created_at
  )
  select id, owner_id, type, kind, title, message, budget_id, category_limit_id,
    savings_goal_id, reminder_id, source_data, dedupe_key, scheduled_for, delivered_at,
    read_at, dismissed_at, delivery_status, delivery_error, delivery_attempt_count,
    delivery_claimed_at, next_delivery_attempt_at, delivery_receipts, created_at
  from jsonb_to_recordset(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
    as x(id uuid, user_id uuid, type text, kind text, title text, message text,
      budget_id uuid, category_limit_id bigint, savings_goal_id uuid, reminder_id uuid,
      source_data jsonb, dedupe_key text, scheduled_for timestamptz, delivered_at timestamptz,
      read_at timestamptz, dismissed_at timestamptz, delivery_status text, delivery_error text,
      delivery_attempt_count smallint, delivery_claimed_at timestamptz,
      next_delivery_attempt_at timestamptz, delivery_receipts jsonb, created_at timestamptz);

  -- Restored IDs were previously generated; never rewind shared sequences.
  update public.backups
  set last_restore_status = 'completed', last_restored_at = now()
  where id = backup_record_id and user_id = owner_id;

  return jsonb_build_object(
    'profile', case when profile_data is null or profile_data = 'null'::jsonb then 0 else 1 end,
    'customCategories', jsonb_array_length(coalesce(payload -> 'data' -> 'customCategories', '[]'::jsonb)),
    'transactions', jsonb_array_length(coalesce(payload -> 'data' -> 'transactions', '[]'::jsonb)),
    'monthlyBudgets', jsonb_array_length(coalesce(payload -> 'data' -> 'monthlyBudgets', '[]'::jsonb)),
    'categoryLimits', jsonb_array_length(coalesce(payload -> 'data' -> 'categoryLimits', '[]'::jsonb)),
    'savingsGoals', jsonb_array_length(coalesce(payload -> 'data' -> 'savingsGoals', '[]'::jsonb)),
    'savingsContributions', jsonb_array_length(coalesce(payload -> 'data' -> 'savingsContributions', '[]'::jsonb)),
    'reports', jsonb_array_length(coalesce(payload -> 'data' -> 'reports', '[]'::jsonb)),
    'notificationPreferences', case when payload -> 'data' -> 'notificationPreferences' is null
      or payload -> 'data' -> 'notificationPreferences' = 'null'::jsonb then 0 else 1 end,
    'reminders', jsonb_array_length(coalesce(payload -> 'data' -> 'reminders', '[]'::jsonb)),
    'alerts', jsonb_array_length(coalesce(payload -> 'data' -> 'alerts', '[]'::jsonb))
  );
end;
$function$
;

REVOKE ALL ON FUNCTION private.restore_financial_backup_v1(jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.set_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.updated_at = now();
  return new;
end;
$function$
;

REVOKE ALL ON FUNCTION private.set_updated_at() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.sync_account_access()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  insert into public.account_access(user_id,email,display_name,created_at,last_sign_in_at)
  values(new.id,new.email,coalesce((select coalesce(full_name,'') from public.profiles where id=new.id),new.raw_user_meta_data->>'display_name',new.raw_user_meta_data->>'full_name',''),new.created_at,new.last_sign_in_at)
  on conflict(user_id) do update set email=excluded.email,display_name=excluded.display_name,last_sign_in_at=excluded.last_sign_in_at;
  return new;
end $function$
;

REVOKE ALL ON FUNCTION private.sync_account_access() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.sync_knowledge_publication()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$begin
  update public.knowledge_documents kd set is_published=coalesce(not new.archived and kd.revision_id=new.published_revision_id,false)
  from public.knowledge_revisions r where r.id=kd.revision_id and r.source_id=new.id
    and kd.is_published is distinct from coalesce(not new.archived and kd.revision_id=new.published_revision_id,false);
  return new;
end$function$
;

REVOKE ALL ON FUNCTION private.sync_knowledge_publication() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.sync_profile_account_name()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  update public.account_access set display_name=coalesce(new.full_name,''),updated_at=now() where user_id=new.id;
  return new;
end $function$
;

REVOKE ALL ON FUNCTION private.sync_profile_account_name() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.valid_receipt_items(items jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO ''
AS $function$
declare item jsonb;
begin
  if items is null or jsonb_typeof(items)<>'array' then return false; end if;
  for item in select value from jsonb_array_elements(items) loop
    if jsonb_typeof(item)<>'object' or jsonb_typeof(item->'description') is distinct from 'string'
      or length(btrim(item->>'description'))=0 or jsonb_typeof(item->'amount') is distinct from 'number' then return false; end if;
    if (item->>'amount')::numeric<=0 then return false; end if;
    if item ? 'modifiers' then
      if jsonb_typeof(item->'modifiers')<>'array' then return false; end if;
      if exists(select 1 from jsonb_array_elements(item->'modifiers') m where jsonb_typeof(m)<>'string') then return false; end if;
    end if;
  end loop;
  return true;
end $function$
;

REVOKE ALL ON FUNCTION private.valid_receipt_items(jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.validate_budget_allocations()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  parent_limit numeric(12, 2);
  allocated numeric(12, 2);
begin
  if tg_table_name = 'budgets' then
    select mb.limit_amount
    into parent_limit
    from public.monthly_budgets mb
    where mb.user_id = new.user_id and mb.month = new.month;

    if parent_limit is null then
      raise exception 'Create the overall monthly budget before adding category limits.'
        using errcode = '23514';
    end if;

    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new.user_id
      and b.month = new.month
      and b.id <> coalesce(new.id, -1);

    if allocated + new.amount > parent_limit then
      raise exception 'Category limits cannot exceed the overall monthly budget.'
        using errcode = '23514';
    end if;
  else
    select coalesce(sum(b.amount), 0)
    into allocated
    from public.budgets b
    where b.user_id = new.user_id and b.month = new.month;

    if allocated > new.limit_amount then
      raise exception 'Overall monthly budget cannot be lower than allocated category limits.'
        using errcode = '23514';
    end if;
  end if;

  new.updated_at = now();
  return new;
end;
$function$
;

REVOKE ALL ON FUNCTION private.validate_budget_allocations() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.validate_financial_backup_data(data jsonb, owner_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$
;

REVOKE ALL ON FUNCTION private.validate_financial_backup_data(jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION private.validate_transaction_category()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if not exists (
    select 1
    from public.categories c
    where c.id = new.category_id
      and (c.user_id is null or c.user_id = new.user_id)
      and c.type in ('expense', 'income')
  ) then
    raise exception 'Transaction category is not available to this user.'
      using errcode = '23503';
  end if;

  new.source = btrim(new.source);
  new.description = nullif(btrim(coalesce(new.description, '')), '');
  new.updated_at = now();
  return new;
end;
$function$
;

REVOKE ALL ON FUNCTION private.validate_transaction_category() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_claim_knowledge_revision()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ declare r public.knowledge_revisions; begin
  update public.knowledge_revisions set status='failed',error_message='Processing retries exhausted.',lease_token=null,lease_until=null where status='processing' and lease_until<now() and attempts>=3;
  select * into r from public.knowledge_revisions where status='queued' or (status='processing' and lease_until<now() and attempts<3) order by created_at for update skip locked limit 1;
  if not found then return null; end if;
  update public.knowledge_revisions set status='processing',lease_token=gen_random_uuid(),lease_until=now()+interval '10 minutes',attempts=attempts+1 where id=r.id returning * into r;
  return to_jsonb(r)||jsonb_build_object('source_key',(select source_key from public.knowledge_sources where id=r.source_id));
end $function$
;

REVOKE ALL ON FUNCTION public.admin_claim_knowledge_revision() FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_fail_knowledge_revision(p_revision uuid, p_lease uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ begin
  update public.knowledge_revisions set status='failed',error_message='Document processing failed. Retry preparation.',lease_token=null,lease_until=null where id=p_revision and status='processing' and lease_token=p_lease;
end $function$
;

REVOKE ALL ON FUNCTION public.admin_fail_knowledge_revision(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_finish_knowledge_revision(p_revision uuid, p_lease uuid, p_chunks jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'extensions', 'public'
AS $function$ declare r public.knowledge_revisions; c jsonb; sk text; idx integer:=0; begin
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
end $function$
;

REVOKE ALL ON FUNCTION public.admin_finish_knowledge_revision(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_knowledge_action(p_actor uuid, p_source uuid, p_revision uuid, p_action text, p_expected uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ declare s public.knowledge_sources; r public.knowledge_revisions; begin
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
end $function$
;

REVOKE ALL ON FUNCTION public.admin_knowledge_action(uuid,uuid,uuid,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.deactivate_user_device(p_user_id uuid, p_expo_push_token text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  affected_count integer;
begin
  update public.user_devices
  set active = false,
      updated_at = now()
  where user_id = p_user_id
    and expo_push_token = p_expo_push_token;

  get diagnostics affected_count = row_count;
  return affected_count > 0;
end;
$function$
;

REVOKE ALL ON FUNCTION public.deactivate_user_device(uuid,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_recoverable_alerts(p_now timestamp with time zone, p_limit integer DEFAULT 100)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$declare result jsonb;begin
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
end $function$
;

REVOKE ALL ON FUNCTION public.admin_recoverable_alerts(timestamp with time zone,integer) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_renew_knowledge_lease(p_revision uuid, p_lease uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ begin
  update public.knowledge_revisions set lease_until=now()+interval '10 minutes' where id=p_revision and status='processing' and lease_token=p_lease and lease_until>now();
  if not found then raise exception 'ADMIN_CONFLICT'; end if;
end $function$
;

REVOKE ALL ON FUNCTION public.admin_renew_knowledge_lease(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_save_knowledge_revision(p_actor uuid, p_source uuid, p_title text, p_content text, p_urls jsonb, p_checked date, p_file_path text, p_expected uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ declare s public.knowledge_sources; rid uuid; old_path text; begin
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
    select file_path into old_path from public.knowledge_revisions where id=s.latest_revision_id;
  end if;
  if jsonb_array_length(p_urls)=0 and coalesce(p_file_path,old_path) is null then raise exception 'ADMIN_INVALID'; end if;
  insert into public.knowledge_revisions(source_id,title,content,source_urls,checked_at,file_path,created_by)
  values(s.id,trim(p_title),trim(p_content),p_urls,p_checked,coalesce(p_file_path,old_path),p_actor) returning id into rid;
  update public.knowledge_sources set latest_revision_id=rid,updated_at=now() where id=s.id;
  insert into public.admin_audit_logs(actor_id,action,target_type,target_id,details) values(p_actor,'knowledge.draft','knowledge_source',s.id::text,jsonb_build_object('revision_id',rid));
  return jsonb_build_object('source_id',s.id,'revision_id',rid);
end $function$
;

REVOKE ALL ON FUNCTION public.admin_save_knowledge_revision(uuid,uuid,text,text,jsonb,date,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.admin_set_account_status(p_actor uuid, p_user uuid, p_status text, p_reason text, p_expected text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ declare a public.account_access; begin
  perform private.require_admin(p_actor);
  if p_status not in ('active','suspended') or length(trim(p_reason)) not between 1 and 300 then raise exception 'ADMIN_INVALID'; end if;
  select * into a from public.account_access where user_id=p_user for update;
  if not found or a.role='admin' then raise exception 'ADMIN_FORBIDDEN'; end if;
  if a.status is distinct from p_expected then raise exception 'ADMIN_CONFLICT'; end if;
  update public.account_access set status=p_status,updated_at=now() where user_id=p_user;
  insert into public.admin_audit_logs(actor_id,action,target_type,target_id,details) values(p_actor,'account.'||p_status,'account',p_user::text,jsonb_build_object('reason',trim(p_reason),'previous_status',a.status));
  return jsonb_build_object('status',p_status);
end $function$
;

REVOKE ALL ON FUNCTION public.admin_set_account_status(uuid,uuid,text,text,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.auth_methods_for_email(p_email text)
 RETURNS text[]
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select coalesce(array_agg(distinct i.provider), '{}')
  from auth.identities i
  join auth.users u on u.id = i.user_id
  where lower(u.email) = lower(p_email);
$function$
;

REVOKE ALL ON FUNCTION public.auth_methods_for_email(text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.begin_financial_backup_delete_v2(backup_record_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare owner_id uuid := auth.uid();
begin
  if owner_id is null or not private.is_active_account() then raise exception 'Active account required'; end if;
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text,20261010));
  update public.backups set status='failed',cleanup_warning='Deletion pending'
    where id=backup_record_id and user_id=owner_id;
  if not found then raise exception 'Backup unavailable'; end if;
end $function$
;

REVOKE ALL ON FUNCTION public.begin_financial_backup_delete_v2(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.claim_alert_delivery(p_alert_id uuid)
 RETURNS SETOF public.alerts
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
  update public.alerts
  set delivery_status = 'sending',
      delivery_claimed_at = now(),
      delivery_attempt_count = delivery_attempt_count + 1,
      next_delivery_attempt_at = null
  where id = p_alert_id
    and (
      delivery_status in ('pending', 'retryable')
      or (
        delivery_status = 'sending'
        and delivery_claimed_at < now() - interval '5 minutes'
      )
    )
    and (next_delivery_attempt_at is null or next_delivery_attempt_at <= now())
  returning *;
$function$
;

REVOKE ALL ON FUNCTION public.claim_alert_delivery(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.complete_coaching_turn_leased(p_user_id uuid, p_session_id uuid, p_user_message_id uuid, p_assistant_message jsonb, p_retrievals jsonb, p_title text, p_token uuid)
 RETURNS SETOF public.coaching_messages
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  perform pg_advisory_xact_lock(hashtextextended('coach:' || p_user_message_id::text,0));
  if not exists(select 1 from private.coaching_processing_leases where message_id=p_user_message_id and token=p_token and expires_at>clock_timestamp()) then
    raise exception 'Processing claim expired or was replaced';
  end if;
  return query select * from public.complete_coaching_turn(p_user_id,p_session_id,p_user_message_id,p_assistant_message,p_retrievals,p_title);
  delete from private.coaching_processing_leases where message_id=p_user_message_id and token=p_token;
end $function$
;

REVOKE ALL ON FUNCTION public.complete_coaching_turn_leased(uuid,uuid,uuid,jsonb,jsonb,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.claim_bill_reminder_occurrence(p_reminder_id uuid, p_expected_trigger_at timestamp with time zone, p_next_due_at timestamp with time zone, p_title text, p_message text, p_dedupe_key text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  claimed_reminder public.reminders;
  claimed_alert_id uuid;
begin
  select reminder.* into claimed_reminder
  from public.reminders as reminder
  where reminder.id = p_reminder_id
    and reminder.enabled = true
    and reminder.next_trigger_at = p_expected_trigger_at
    and reminder.next_trigger_at <= now()
    and exists (
      select 1
      from public.notification_preferences as preference
      where preference.user_id = reminder.user_id
        and preference.bills_enabled = true
    )
  for update;

  if not found then
    return null;
  end if;

  insert into public.alerts (
    user_id,
    type,
    kind,
    title,
    message,
    reminder_id,
    dedupe_key,
    scheduled_for
  )
  values (
    claimed_reminder.user_id,
    'bill_reminder',
    'alert',
    p_title,
    p_message,
    claimed_reminder.id,
    p_dedupe_key,
    p_expected_trigger_at
  )
  on conflict (user_id, dedupe_key) do nothing
  returning id into claimed_alert_id;

  if claimed_alert_id is null then
    select id into claimed_alert_id
    from public.alerts
    where user_id = claimed_reminder.user_id
      and dedupe_key = p_dedupe_key;
  end if;

  if claimed_reminder.recurrence = 'none' then
    update public.reminders
    set enabled = false,
        next_trigger_at = null,
        last_triggered_at = p_expected_trigger_at
    where id = claimed_reminder.id;
  else
    if p_next_due_at is null then
      raise exception 'A recurring reminder requires its next due date.';
    end if;
    update public.reminders
    set due_at = p_next_due_at,
        last_triggered_at = p_expected_trigger_at
    where id = claimed_reminder.id;
  end if;

  return claimed_alert_id;
end;
$function$
;

REVOKE ALL ON FUNCTION public.claim_bill_reminder_occurrence(uuid,timestamp with time zone,timestamp with time zone,text,text,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.claim_coach_report_attempt(p_user_id uuid, p_message_id uuid, p_action_id uuid, p_attempt_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  message public.coaching_messages;
  attempt public.report_attempts;
  live public.report_attempts;
  terminal public.report_attempts;
  action_status text;
  requested_category text;
  resolved_category bigint;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload->>'type' is distinct from 'action'
    or message.ui_payload->>'action_type' is distinct from 'generate_report'
    or message.ui_payload->>'action_id' is distinct from p_action_id::text
  then raise exception 'Action not found.' using errcode='P0002'; end if;
  -- Compatibility: a report confirmation without the device-reserved attempt id
  -- must be refused before any state changes.
  if p_attempt_id is null then
    raise exception 'Update FinCoach to generate this report.' using errcode='P0101';
  end if;
  action_status:=message.ui_payload->>'status';
  if action_status='executed' then
    select * into terminal from public.report_attempts
      where action_id=p_action_id and user_id=p_user_id and message_id=p_message_id
        and status='completed'
      order by updated_at desc limit 1;
    return jsonb_build_object('message',to_jsonb(message),
      'attempt',case when terminal.attempt_id is null then null else to_jsonb(terminal) end);
  end if;
  if action_status='cancelled' then
    raise exception 'This report action was cancelled. Ask for a new report.' using errcode='P0001';
  end if;
  if action_status not in ('pending','failed','approved') or action_status is null then
    raise exception 'Invalid action transition.';
  end if;
  -- Lock order everywhere: the owned action message, then its current attempt.
  select * into live from public.report_attempts
    where action_id=p_action_id and user_id=p_user_id and status='active' for update;
  if found and live.attempt_id=p_attempt_id then
    -- The same device resumes its attempt; a lapsed lease is safely reacquired
    -- while the attempt is still the one active attempt.
    update public.report_attempts
      set lease_expires_at=clock_timestamp()+interval '5 minutes',lease_owner=p_user_id,
        lease_renewed_at=clock_timestamp(),lease_renewal_count=lease_renewal_count+1,
        updated_at=clock_timestamp()
      where attempt_id=live.attempt_id returning * into attempt;
  elsif found and live.lease_expires_at>clock_timestamp() then
    -- Another device's lease is still valid: never replace or adopt it.
    raise exception 'Report generation is already in progress.' using errcode='P0102',
      detail=jsonb_build_object('lease_expires_at',live.lease_expires_at)::text;
  else
    if found then
      -- Only an expired attempt can be replaced, and its future completion is
      -- permanently fenced by the superseded status.
      update public.report_attempts set status='superseded',updated_at=clock_timestamp()
        where attempt_id=live.attempt_id;
    end if;
    -- A terminal attempt id has a reserved path that may already hold a file,
    -- so it is never silently reused or substituted.
    if exists(select 1 from public.report_attempts where attempt_id=p_attempt_id) then
      raise exception 'This report attempt can no longer be used. Start a new attempt.'
        using errcode='P0104';
    end if;
    if jsonb_typeof(message.ui_payload->'arguments') is distinct from 'object'
      or message.ui_payload->'arguments'->>'start_date' !~ '^\d{4}-\d{2}-\d{2}$'
      or message.ui_payload->'arguments'->>'end_date' !~ '^\d{4}-\d{2}-\d{2}$'
      or (message.ui_payload->'arguments'->>'start_date')::date
         > (message.ui_payload->'arguments'->>'end_date')::date
    then raise exception 'Invalid report selection.'; end if;
    requested_category:=nullif(lower(btrim(message.ui_payload->'arguments'->>'category_name')),'');
    select c.id into resolved_category from public.categories c
      where lower(btrim(c.name))=requested_category and (c.user_id is null or c.user_id=p_user_id)
      order by (c.user_id is null),(c.type<>'expense'),c.id limit 1;
    -- A requested category that no longer resolves would silently widen the
    -- report scope, so the attempt is refused instead of mislabelled.
    if requested_category is not null and resolved_category is null then
      raise exception 'The report category is no longer available.' using errcode='P0003';
    end if;
    insert into public.report_attempts(attempt_id,user_id,message_id,action_id,storage_path,
      period,report_type,start_date,end_date,category_id,category_name,arguments,
      lease_expires_at,lease_owner)
    values(p_attempt_id,p_user_id,p_message_id,p_action_id,
      p_user_id::text||'/coach/'||p_attempt_id::text||'.pdf',
      coalesce(nullif(btrim(message.ui_payload->'arguments'->>'period'),''),'custom'),
      case when message.ui_payload->'arguments'->>'period' in ('current_month','last_month') then 'monthly'
        when message.ui_payload->'arguments'->>'period'='last_3_months' then 'multi_month' else 'custom' end
        || case when requested_category is null then '' else '_category' end,
      (message.ui_payload->'arguments'->>'start_date')::date,
      (message.ui_payload->'arguments'->>'end_date')::date,
      resolved_category,nullif(btrim(message.ui_payload->'arguments'->>'category_name'),''),
      message.ui_payload->'arguments',clock_timestamp()+interval '5 minutes',p_user_id)
    returning * into attempt;
  end if;
  if message.ui_payload->>'status' is distinct from 'approved' then
    update public.coaching_messages
      set ui_payload=jsonb_set(message.ui_payload,'{status}','"approved"')
      where id=p_message_id and user_id=p_user_id returning * into message;
  end if;
  return jsonb_build_object('message',to_jsonb(message),'attempt',to_jsonb(attempt));
end $function$
;

REVOKE ALL ON FUNCTION public.claim_coach_report_attempt(uuid,uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.claim_coaching_message(p_user_id uuid, p_message_id uuid, p_token uuid, p_session_id uuid DEFAULT NULL::uuid, p_content text DEFAULT NULL::text)
 RETURNS SETOF public.coaching_messages
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare message public.coaching_messages; lease private.coaching_processing_leases;
begin
  perform pg_advisory_xact_lock(hashtextextended('coach:' || p_message_id::text,0));
  select * into message from public.coaching_messages where id=p_message_id for update;
  if not found then
    if p_session_id is null or p_content is null then return; end if;
    if not exists(select 1 from public.coaching_sessions where id=p_session_id and user_id=p_user_id) then raise exception 'Conversation not found'; end if;
    insert into public.coaching_messages(id,session_id,user_id,role,content,status)
      values(p_message_id,p_session_id,p_user_id,'user',p_content,'completed') returning * into message;
  else
    if message.user_id<>p_user_id or message.role<>'user' or (p_session_id is not null and message.session_id<>p_session_id)
      or (p_content is not null and message.content<>p_content) then raise exception 'Message identifier is already in use'; end if;
    if exists(select 1 from public.coaching_messages where reply_to_message_id=p_message_id) then return; end if;
    select * into lease from private.coaching_processing_leases where message_id=p_message_id;
    if found and lease.expires_at>clock_timestamp() then return; end if;
    -- Pre-migration requests have no lease; allow the old worker a bounded grace period.
    if lease.message_id is null and message.status<>'failed' and message.created_at>clock_timestamp()-interval '15 minutes' then return; end if;
    update public.coaching_messages set status='completed',error_code=null where id=p_message_id returning * into message;
  end if;
  insert into private.coaching_processing_leases(message_id,token,expires_at)
    values(p_message_id,p_token,clock_timestamp()+interval '15 minutes')
    on conflict(message_id) do update set token=excluded.token,expires_at=excluded.expires_at;
  return next message;
end $function$
;

REVOKE ALL ON FUNCTION public.claim_coaching_message(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.commit_coach_action(p_user_id uuid, p_message_id uuid, p_expected_payload jsonb, p_next_payload jsonb, p_reminder jsonb DEFAULT NULL::jsonb)
 RETURNS SETOF public.coaching_messages
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  message public.coaching_messages;
  old_status text;
  new_status text;
  action_kind text;
  resolved_action_id uuid;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload is distinct from p_expected_payload then
    raise exception 'Action state changed. Reload and try again.'; end if;
  if jsonb_typeof(p_next_payload) is distinct from 'object'
    or p_expected_payload->>'type' is distinct from 'action'
    or (p_next_payload-'status'-'result') is distinct from (p_expected_payload-'status'-'result')
  then raise exception 'Invalid action transition.'; end if;
  old_status:=p_expected_payload->>'status';
  new_status:=p_next_payload->>'status';
  action_kind:=p_expected_payload->>'action_type';
  resolved_action_id:=(p_expected_payload->>'action_id')::uuid;
  if resolved_action_id is null or action_kind not in ('create_reminder','generate_report') or not coalesce(
    (new_status='cancelled' and old_status in ('pending','approved','failed'))
    or (action_kind='create_reminder' and old_status='pending' and new_status='executed'),false)
  then raise exception 'Invalid action transition.'; end if;
  if p_reminder is not null and not (action_kind='create_reminder' and new_status='executed') then
    raise exception 'Unexpected reminder effect.'; end if;
  if action_kind='create_reminder' and new_status='executed' then
    if p_reminder is not null then
      if p_reminder->>'id' is distinct from resolved_action_id::text
        or p_reminder->>'user_id' is distinct from p_user_id::text
      then raise exception 'Invalid reminder owner.'; end if;
      -- Columns and owner are fixed; arbitrary fields in JSON cannot alter unrelated records.
      insert into public.reminders(id,user_id,type,title,amount,due_at,lead_days,recurrence,
        recurrence_anchor_day,enabled,next_trigger_at)
      values(resolved_action_id,p_user_id,'bill',p_reminder->>'title',(p_reminder->>'amount')::numeric,
        (p_reminder->>'due_at')::timestamptz,(p_reminder->>'lead_days')::integer,
        p_reminder->>'recurrence',(p_reminder->>'recurrence_anchor_day')::integer,true,
        (p_reminder->>'next_trigger_at')::timestamptz)
      on conflict(id) do nothing;
    end if;
    if not exists(select 1 from public.reminders where id=resolved_action_id and user_id=p_user_id)
      or p_next_payload->'result'->>'reminder_id' is distinct from resolved_action_id::text
    then raise exception 'Reminder effect missing.'; end if;
  end if;
  if action_kind='generate_report' and new_status='cancelled' then
    update public.report_attempts set status='cancelled',updated_at=clock_timestamp()
      where action_id=resolved_action_id and user_id=p_user_id and status='active';
  end if;
  return query update public.coaching_messages set ui_payload=p_next_payload
    where id=p_message_id and user_id=p_user_id returning *;
end $function$
;

REVOKE ALL ON FUNCTION public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.complete_coach_report_attempt(p_user_id uuid, p_message_id uuid, p_action_id uuid, p_attempt_id uuid, p_success boolean, p_report jsonb DEFAULT NULL::jsonb, p_storage jsonb DEFAULT NULL::jsonb)
 RETURNS SETOF public.coaching_messages
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  message public.coaching_messages;
  attempt public.report_attempts;
  stored storage.objects;
  stored_json jsonb;
  stored_updated timestamptz;
  claimed_updated timestamptz;
  inserted public.reports;
  next_payload jsonb;
  generated_at timestamptz;
  report_title text;
  report_file_name text;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  if message.ui_payload->>'type' is distinct from 'action'
    or message.ui_payload->>'action_type' is distinct from 'generate_report'
    or message.ui_payload->>'action_id' is distinct from p_action_id::text
  then raise exception 'Action not found.' using errcode='P0002'; end if;
  if p_attempt_id is null then
    raise exception 'Update FinCoach to generate this report.' using errcode='P0101';
  end if;
  -- A repeated success after the action already executed returns the terminal
  -- result instead of inserting a second history row.
  if message.ui_payload->>'status'='executed' then
    if p_success then return next message; return; end if;
    raise exception 'Invalid action transition.';
  end if;
  if message.ui_payload->>'status' is distinct from 'approved' then
    raise exception 'The report action has not been approved.';
  end if;
  select * into attempt from public.report_attempts
    where attempt_id=p_attempt_id and user_id=p_user_id and message_id=p_message_id
      and action_id=p_action_id and status='active' for update;
  if not found then
    -- Superseded, cancelled, replaced or foreign attempts can no longer publish.
    raise exception 'The report attempt expired before it could be used.' using errcode='P0103';
  end if;
  if not p_success then
    -- A render failure releases the attempt so the action can be retried.
    update public.report_attempts set status='cancelled',updated_at=clock_timestamp()
      where attempt_id=attempt.attempt_id;
    next_payload:=jsonb_set(message.ui_payload,'{status}','"failed"');
    next_payload:=jsonb_set(next_payload,'{result}',coalesce(p_report,'{}'::jsonb));
    return query update public.coaching_messages set ui_payload=next_payload
      where id=p_message_id and user_id=p_user_id returning *;
    return;
  end if;
  if attempt.lease_expires_at<=clock_timestamp() then
    raise exception 'The report attempt expired before it could be used.' using errcode='P0103';
  end if;
  if jsonb_typeof(p_report) is distinct from 'object'
    or jsonb_typeof(p_report->'title') is distinct from 'string'
    or jsonb_typeof(p_report->'file_name') is distinct from 'string'
    or jsonb_typeof(p_report->'generated_at') is distinct from 'string'
  then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
  report_title:=btrim(p_report->>'title');
  report_file_name:=btrim(p_report->>'file_name');
  if char_length(report_title) not between 1 and 160
    or char_length(report_file_name) not between 5 and 255
    or report_file_name not like '%.pdf' or report_file_name ~ '[/\\]'
  then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
  begin
    generated_at:=(p_report->>'generated_at')::timestamptz;
  exception when others then raise exception 'Invalid report metadata.' using errcode='P0003'; end;
  if generated_at is null then raise exception 'Invalid report metadata.' using errcode='P0003'; end if;
  -- Recheck the exact object identity/version the backend downloaded. The
  -- caller can never choose the path: it must equal the attempt's reserved path.
  if p_storage is null or jsonb_typeof(p_storage) is distinct from 'object'
    or p_storage->>'path' is distinct from attempt.storage_path
    or nullif(p_storage->>'object_id','') is null
    or nullif(p_storage->>'version','') is null
    or nullif(p_storage->>'updated_at','') is null
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  select * into stored from storage.objects
    where bucket_id='financial-reports' and name=attempt.storage_path for share;
  if not found then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  stored_json:=to_jsonb(stored);
  if coalesce(stored_json->>'owner','')<>p_user_id::text
    and coalesce(stored_json->>'owner_id','')<>p_user_id::text
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  if stored_json->>'id' is distinct from p_storage->>'object_id'
    or coalesce(stored_json->>'version','') is distinct from p_storage->>'version'
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  -- The storage API serialises the row's updated_at with millisecond
  -- precision, so the same instant is compared at millisecond granularity.
  begin
    stored_updated:=(stored_json->>'updated_at')::timestamptz;
    claimed_updated:=(p_storage->>'updated_at')::timestamptz;
  exception when others then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end;
  if stored_updated is null or claimed_updated is null
    or date_trunc('milliseconds',stored_updated)
       is distinct from date_trunc('milliseconds',claimed_updated)
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  if coalesce(stored_json->'metadata'->>'size','NONE') !~ '^\d+$'
    or (stored_json->'metadata'->>'size')::bigint<=0
    or lower(btrim(split_part(coalesce(stored_json->'metadata'->>'mimetype',''),';',1))) <> 'application/pdf'
    or coalesce(p_storage->>'size','NONE') !~ '^\d+$'
    or (stored_json->'metadata'->>'size')::bigint is distinct from (p_storage->>'size')::bigint
  then
    raise exception 'The uploaded report could not be verified.' using errcode='P0105';
  end if;
  -- Selection, path and key come from the attempt, never from the caller.
  insert into public.reports(user_id,period,type,title,file_name,storage_path,report_key,
    start_date,end_date,category_id,generated_at)
  values(p_user_id,
    case when attempt.report_type in ('monthly','monthly_category') then to_char(attempt.start_date,'YYYY-MM')
      when attempt.report_type in ('multi_month','multi_month_category') then
        to_char(attempt.start_date,'YYYY-MM')||'..'||to_char(attempt.end_date,'YYYY-MM')
      else attempt.start_date::text||'..'||attempt.end_date::text end,
    attempt.report_type,report_title,report_file_name,attempt.storage_path,
    'coach:'||attempt.attempt_id::text,attempt.start_date,attempt.end_date,
    attempt.category_id,generated_at)
  returning * into inserted;
  update public.report_attempts
    set status='completed',report_id=inserted.id,updated_at=clock_timestamp()
    where attempt_id=attempt.attempt_id;
  next_payload:=jsonb_set(message.ui_payload,'{status}','"executed"');
  next_payload:=jsonb_set(next_payload,'{result}',
    jsonb_build_object('report_id',inserted.id,'storage_path',inserted.storage_path,
      'title',inserted.title));
  return query update public.coaching_messages set ui_payload=next_payload
    where id=p_message_id and user_id=p_user_id returning *;
end $function$
;

REVOKE ALL ON FUNCTION public.complete_coach_report_attempt(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.complete_coaching_turn(p_user_id uuid, p_session_id uuid, p_user_message_id uuid, p_assistant_message jsonb, p_retrievals jsonb, p_title text)
 RETURNS SETOF public.coaching_messages
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  assistant public.coaching_messages;
begin
  if jsonb_typeof(p_assistant_message) <> 'object' then
    raise exception 'Assistant message payload must be an object.';
  end if;
  if jsonb_typeof(coalesce(p_retrievals, '[]'::jsonb)) <> 'array' then
    raise exception 'Retrieval payload must be an array.';
  end if;
  if jsonb_typeof(coalesce(p_assistant_message -> 'ui_payload', '{}'::jsonb)) <> 'object' then
    raise exception 'Coach interaction payload must be an object.';
  end if;
  if not exists (
    select 1
    from public.coaching_sessions as session
    join public.coaching_messages as user_message
      on user_message.session_id = session.id
    where session.id = p_session_id
      and session.user_id = p_user_id
      and user_message.id = p_user_message_id
      and user_message.user_id = p_user_id
      and user_message.role = 'user'
  ) then
    raise exception 'Invalid coaching turn.';
  end if;

  insert into public.coaching_messages (
    id,
    session_id,
    user_id,
    role,
    content,
    reply_to_message_id,
    status,
    error_code,
    model,
    prompt_tokens,
    completion_tokens,
    ui_payload
  )
  values (
    (p_assistant_message ->> 'id')::uuid,
    p_session_id,
    p_user_id,
    'assistant',
    p_assistant_message ->> 'content',
    p_user_message_id,
    'completed',
    null,
    p_assistant_message ->> 'model',
    (p_assistant_message ->> 'prompt_tokens')::integer,
    (p_assistant_message ->> 'completion_tokens')::integer,
    coalesce(p_assistant_message -> 'ui_payload', '{}'::jsonb)
  )
  returning * into assistant;

  insert into public.coaching_retrievals (
    user_id,
    assistant_message_id,
    knowledge_document_id,
    rank,
    similarity,
    title,
    source
  )
  select
    p_user_id,
    assistant.id,
    (item ->> 'knowledge_document_id')::bigint,
    (item ->> 'rank')::smallint,
    (item ->> 'similarity')::double precision,
    item ->> 'title',
    item ->> 'source'
  from jsonb_array_elements(coalesce(p_retrievals, '[]'::jsonb)) as entries(item);

  update public.coaching_messages
  set status = 'completed',
      error_code = null
  where id = p_user_message_id
    and user_id = p_user_id
    and role = 'user';

  update public.coaching_sessions
  set last_message_at = now(),
      title = coalesce(p_title, title)
  where id = p_session_id
    and user_id = p_user_id;

  return next assistant;
end;
$function$
;

REVOKE ALL ON FUNCTION public.complete_coaching_turn(uuid,uuid,uuid,jsonb,jsonb,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.complete_financial_backup_v2(backup_record_id uuid, document jsonb, object_path text, object_size bigint, checksum text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$
;

REVOKE ALL ON FUNCTION public.complete_financial_backup_v2(uuid,jsonb,text,bigint,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.fail_coaching_message(p_user_id uuid, p_message_id uuid, p_token uuid, p_error_code text)
 RETURNS SETOF public.coaching_messages
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  perform pg_advisory_xact_lock(hashtextextended('coach:' || p_message_id::text,0));
  if not exists(select 1 from private.coaching_processing_leases where message_id=p_message_id and token=p_token)
    or not exists(select 1 from public.coaching_messages where id=p_message_id and user_id=p_user_id and role='user')
    or exists(select 1 from public.coaching_messages where reply_to_message_id=p_message_id) then return; end if;
  return query update public.coaching_messages set status='failed',error_code=p_error_code where id=p_message_id returning *;
  delete from private.coaching_processing_leases where message_id=p_message_id and token=p_token;
end $function$
;

REVOKE ALL ON FUNCTION public.fail_coaching_message(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.financial_backup_snapshot_v2(backup_record_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    'customCategories', (select coalesce(jsonb_agg(to_jsonb(c) order by c.id::text),'[]'::jsonb) from public.categories c where c.user_id=owner_id),
    'userCategories', (select coalesce(jsonb_agg(to_jsonb(c) order by c.category_id::text),'[]'::jsonb) from public.user_categories c where c.user_id=owner_id),
    'transactions', (select coalesce(jsonb_agg(to_jsonb(t) order by t.id::text),'[]'::jsonb) from public.transactions t where t.user_id=owner_id),
    'monthlyBudgets', (select coalesce(jsonb_agg(to_jsonb(b) order by b.id::text),'[]'::jsonb) from public.monthly_budgets b where b.user_id=owner_id),
    'categoryLimits', (select coalesce(jsonb_agg(to_jsonb(b) order by b.id::text),'[]'::jsonb) from public.budgets b where b.user_id=owner_id),
    'savingsGoals', (select coalesce(jsonb_agg(to_jsonb(g) order by g.id::text),'[]'::jsonb) from public.savings_goals g where g.user_id=owner_id),
    'savingsContributions', (select coalesce(jsonb_agg(to_jsonb(c) order by c.id::text),'[]'::jsonb) from public.savings_contributions c join public.savings_goals g on g.id=c.goal_id where g.user_id=owner_id),
    'reports', (select coalesce(jsonb_agg(to_jsonb(r) order by r.id::text),'[]'::jsonb) from public.reports r where r.user_id=owner_id),
    'notificationPreferences', (select to_jsonb(p) from public.notification_preferences p where p.user_id=owner_id),
    'reminders', (select coalesce(jsonb_agg(to_jsonb(r) order by r.id::text),'[]'::jsonb) from public.reminders r where r.user_id=owner_id),
    'alerts', (select coalesce(jsonb_agg(to_jsonb(a) order by a.id::text),'[]'::jsonb) from public.alerts a where a.user_id=owner_id)
  ) into result;
  if backup_record_id is not null then
    insert into private.financial_backup_snapshots(backup_id,user_id,data) values(backup_record_id,owner_id,result);
  end if;
  return result;
end $function$
;

REVOKE ALL ON FUNCTION public.financial_backup_snapshot_v2(uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.list_abandoned_coach_report_artifacts(p_after_created timestamp with time zone DEFAULT NULL::timestamp with time zone, p_after_id uuid DEFAULT NULL::uuid, p_user_id uuid DEFAULT NULL::uuid, p_message_id uuid DEFAULT NULL::uuid, p_action_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(attempt_id uuid, user_id uuid, storage_path text, created_at timestamp with time zone)
 LANGUAGE sql
 SET search_path TO ''
AS $function$
  select a.attempt_id,a.user_id,a.storage_path,a.created_at from public.report_attempts a
  where a.status in ('cancelled','superseded')
    and (p_user_id is null or a.user_id=p_user_id)
    and (p_message_id is null or a.message_id=p_message_id)
    and (p_action_id is null or a.action_id=p_action_id)
    and (p_after_created is null or (a.created_at,a.attempt_id)>(p_after_created,p_after_id))
    and not exists(select 1 from public.reports r where r.storage_path=a.storage_path)
  order by a.created_at,a.attempt_id limit 100
$function$
;

REVOKE ALL ON FUNCTION public.list_abandoned_coach_report_artifacts(timestamp with time zone,uuid,uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.match_knowledge_documents(query_embedding public.vector, match_count integer DEFAULT 5)
 RETURNS TABLE(id bigint, title text, content text, source text, page_number integer, chunk_index integer, similarity double precision)
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'extensions', 'public'
AS $function$
  select
    kd.id,
    kd.title,
    kd.content,
    kd.source,
    kd.page_number,
    kd.chunk_index,
    1 - (kd.embedding <=> query_embedding) as similarity   -- cosine similarity
  from public.published_knowledge_documents kd
  order by kd.embedding <=> query_embedding                 -- nearest first
  limit greatest(1, least(match_count, 10));
$function$
;

REVOKE ALL ON FUNCTION public.match_knowledge_documents(public.vector,integer) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.match_knowledge_documents_hybrid(query_text text, query_embedding public.vector, match_count integer DEFAULT 5)
 RETURNS TABLE(id bigint, title text, content text, source text, page_number integer, chunk_index integer, similarity double precision, dense_rank integer, lexical_rank integer, lexical_score double precision)
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'extensions', 'public'
AS $function$
  with query_terms as (
    select websearch_to_tsquery('simple', coalesce(query_text, '')) as query
  ),
  dense as (
    select
      kd.id,
      1 - (kd.embedding <=> query_embedding) as similarity,
      (row_number() over (order by kd.embedding <=> query_embedding))::integer as dense_rank
    from public.published_knowledge_documents as kd
    order by kd.embedding <=> query_embedding
    limit greatest(1, least(match_count, 10)) * 2
  ),
  lexical_scored as (
    select
      kd.id,
      ts_rank_cd(
        setweight(to_tsvector('simple', coalesce(kd.title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(kd.source, '')), 'B') ||
        setweight(to_tsvector('simple', kd.content), 'C'),
        query_terms.query
      )::double precision as lexical_score
    from public.published_knowledge_documents as kd
    cross join query_terms
    where (
      setweight(to_tsvector('simple', coalesce(kd.title, '')), 'A') ||
      setweight(to_tsvector('simple', coalesce(kd.source, '')), 'B') ||
      setweight(to_tsvector('simple', kd.content), 'C')
    ) @@ query_terms.query
  ),
  lexical as (
    select
      id,
      lexical_score,
      (row_number() over (order by lexical_score desc, id))::integer as lexical_rank
    from lexical_scored
    order by lexical_score desc, id
    limit greatest(1, least(match_count, 10)) * 2
  )
  select
    kd.id,
    kd.title,
    kd.content,
    kd.source,
    kd.page_number,
    kd.chunk_index,
    coalesce(dense.similarity, 0)::double precision as similarity,
    dense.dense_rank,
    lexical.lexical_rank,
    coalesce(lexical.lexical_score, 0)::double precision as lexical_score
  from dense
  full outer join lexical on lexical.id = dense.id
  join public.published_knowledge_documents as kd on kd.id = coalesce(dense.id, lexical.id)
  order by
    coalesce(dense.dense_rank, 2147483647),
    coalesce(lexical.lexical_rank, 2147483647)
  limit greatest(1, least(match_count, 10)) * 2;
$function$
;

REVOKE ALL ON FUNCTION public.match_knowledge_documents_hybrid(text,public.vector,integer) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.reassign_user_device(p_user_id uuid, p_expo_push_token text, p_platform text, p_device_name text DEFAULT NULL::text)
 RETURNS public.user_devices
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  registered_device public.user_devices;
begin
  insert into public.user_devices (
    user_id,
    expo_push_token,
    platform,
    device_name,
    active,
    last_seen_at,
    last_error
  )
  values (
    p_user_id,
    btrim(p_expo_push_token),
    p_platform,
    nullif(btrim(p_device_name), ''),
    true,
    now(),
    null
  )
  on conflict (expo_push_token) do update
  set user_id = excluded.user_id,
      platform = excluded.platform,
      device_name = excluded.device_name,
      active = true,
      last_seen_at = now(),
      last_error = null
  returning * into registered_device;

  return registered_device;
end;
$function$
;

REVOKE ALL ON FUNCTION public.reassign_user_device(uuid,text,text,text) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.renew_report_attempt(p_user_id uuid, p_message_id uuid, p_attempt_id uuid)
 RETURNS SETOF public.report_attempts
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  message public.coaching_messages;
  attempt public.report_attempts;
begin
  select * into message from public.coaching_messages
    where id=p_message_id and user_id=p_user_id and role='assistant' for update;
  if not found then raise exception 'Action not found.' using errcode='P0002'; end if;
  update public.report_attempts
    set lease_expires_at=clock_timestamp()+interval '5 minutes',lease_owner=p_user_id,
      lease_renewed_at=clock_timestamp(),lease_renewal_count=lease_renewal_count+1,
      updated_at=clock_timestamp()
    where attempt_id=p_attempt_id and user_id=p_user_id and message_id=p_message_id
      and status='active' and lease_expires_at>clock_timestamp()
    returning * into attempt;
  if not found then
    raise exception 'The report attempt lease expired or was replaced.' using errcode='P0002';
  end if;
  return next attempt;
end $function$
;

REVOKE ALL ON FUNCTION public.renew_report_attempt(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.replace_tracked_categories(p_user_id uuid, p_category_ids bigint[])
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if auth.uid() is distinct from p_user_id then raise exception 'Not authorized' using errcode='42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended('tracked:' || p_user_id::text, 0));
  if p_category_ids is null or exists (
    select 1 from unnest(p_category_ids) as selected(category_id) left join public.categories c on c.id=selected.category_id
    where c.id is null or (c.user_id is not null and c.user_id <> p_user_id)
  ) then raise exception 'Invalid tracked category'; end if;
  delete from public.user_categories where user_id=p_user_id and not (category_id=any(p_category_ids));
  insert into public.user_categories(user_id,category_id)
    select p_user_id,id from (select distinct unnest(p_category_ids) id) selected
    on conflict(user_id,category_id) do nothing;
end $function$
;

REVOKE ALL ON FUNCTION public.replace_tracked_categories(uuid,bigint[]) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.restore_financial_backup_v1(payload jsonb, backup_record_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  if not private.is_active_account() then raise exception 'Account access denied' using errcode='42501'; end if;
  return private.restore_financial_backup_v1(payload,backup_record_id);
end $function$
;

REVOKE ALL ON FUNCTION public.restore_financial_backup_v1(jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.restore_financial_backup_v2(payload jsonb, backup_record_id uuid, restored_paths jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$
;

REVOKE ALL ON FUNCTION public.restore_financial_backup_v2(jsonb,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.save_budget_month(p_user_id uuid, p_month date, p_overall numeric, p_allocations jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare item record; old_total numeric;
begin
  if auth.uid() is distinct from p_user_id then raise exception 'Not authorized' using errcode='42501'; end if;
  if p_month is null or extract(day from p_month) <> 1 or p_overall is null or p_overall <= 0
     or p_overall <> round(p_overall,2) or p_overall::text in ('NaN','Infinity','-Infinity')
     or p_allocations is null or jsonb_typeof(p_allocations) <> 'array' then raise exception 'Invalid budget'; end if;
  perform pg_advisory_xact_lock(hashtextextended('budget:' || p_user_id::text || ':' || p_month::text,0));
  if exists(select 1 from jsonb_to_recordset(p_allocations) as x(category_id bigint,amount numeric)
    left join public.categories c on c.id=x.category_id
    where c.id is null or c.type <> 'expense' or (c.user_id is not null and c.user_id<>p_user_id)
      or x.amount is null or x.amount<=0 or x.amount<>round(x.amount,2) or x.amount::text in ('NaN','Infinity','-Infinity'))
    or (select count(*) <> count(distinct category_id) from jsonb_to_recordset(p_allocations) as x(category_id bigint))
    or (select coalesce(sum(amount),0)>p_overall from jsonb_to_recordset(p_allocations) as x(amount numeric))
  then raise exception 'Invalid category allocations'; end if;
  select limit_amount into old_total from public.monthly_budgets where user_id=p_user_id and month=p_month for update;
  -- Expand first, reduce allocations before increases, and shrink the parent last.
  if old_total is null then
    insert into public.monthly_budgets(user_id,month,limit_amount) values(p_user_id,p_month,p_overall);
  elsif p_overall > old_total then
    update public.monthly_budgets set limit_amount=p_overall where user_id=p_user_id and month=p_month;
  end if;
  delete from public.budgets where user_id=p_user_id and month=p_month
    and category_id not in (select category_id from jsonb_to_recordset(p_allocations) as x(category_id bigint));
  for item in select x.category_id,x.amount from jsonb_to_recordset(p_allocations) as x(category_id bigint,amount numeric)
    left join public.budgets b on b.user_id=p_user_id and b.month=p_month and b.category_id=x.category_id
    order by x.amount-coalesce(b.amount,0),x.category_id
  loop
    -- UPDATE avoids the BEFORE INSERT trigger checking an existing allocation twice.
    update public.budgets set amount=item.amount where user_id=p_user_id and month=p_month and category_id=item.category_id;
    if not found then insert into public.budgets(user_id,month,category_id,amount) values(p_user_id,p_month,item.category_id,item.amount); end if;
  end loop;
  update public.monthly_budgets set limit_amount=p_overall where user_id=p_user_id and month=p_month;
end $function$
;

REVOKE ALL ON FUNCTION public.save_budget_month(uuid,date,numeric,jsonb) FROM PUBLIC,anon,authenticated,service_role;

INSERT INTO "private"."coaching_processing_leases" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_0;

INSERT INTO "private"."financial_backup_snapshots" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_1;

INSERT INTO "public"."account_access" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_2;

INSERT INTO "public"."admin_audit_logs" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_3;

SELECT setval('public.admin_audit_logs_id_seq',value,called) FROM rollback_sequences WHERE name='public.admin_audit_logs_id_seq';

INSERT INTO "public"."alerts" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_4;

INSERT INTO "public"."backups" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_5;

INSERT INTO "public"."budgets" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_6;

SELECT setval('public.budgets_id_seq',value,called) FROM rollback_sequences WHERE name='public.budgets_id_seq';

INSERT INTO "public"."categories" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_7;

SELECT setval('public.categories_id_seq',value,called) FROM rollback_sequences WHERE name='public.categories_id_seq';

INSERT INTO "public"."coaching_messages" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_8;

INSERT INTO "public"."coaching_retrievals" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_9;

SELECT setval('public.coaching_retrievals_id_seq',value,called) FROM rollback_sequences WHERE name='public.coaching_retrievals_id_seq';

INSERT INTO "public"."coaching_sessions" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_10;

INSERT INTO "public"."data_exports" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_11;

INSERT INTO "public"."export_contents" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_12;

INSERT INTO "public"."knowledge_documents" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_13;

SELECT setval('public.knowledge_documents_id_seq',value,called) FROM rollback_sequences WHERE name='public.knowledge_documents_id_seq';

INSERT INTO "public"."knowledge_revisions" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_14;

INSERT INTO "public"."knowledge_sources" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_15;

INSERT INTO "public"."monthly_budgets" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_16;

INSERT INTO "public"."notification_preferences" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_17;

INSERT INTO "public"."reminders" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_18;

INSERT INTO "public"."report_attempts" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_19;

INSERT INTO "public"."reports" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_20;

SELECT setval('public.reports_id_seq',value,called) FROM rollback_sequences WHERE name='public.reports_id_seq';

INSERT INTO "public"."savings_contributions" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_21;

SELECT setval('public.savings_contributions_id_seq',value,called) FROM rollback_sequences WHERE name='public.savings_contributions_id_seq';

INSERT INTO "public"."savings_goals" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_22;

INSERT INTO "public"."transactions" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_23;

INSERT INTO "public"."user_categories" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_24;

INSERT INTO "public"."user_devices" OVERRIDING SYSTEM VALUE SELECT * FROM rollback_rows_25;

ALTER TABLE "private"."coaching_processing_leases" ADD CONSTRAINT "coaching_processing_leases_pkey" PRIMARY KEY (message_id);

ALTER TABLE "private"."financial_backup_snapshots" ADD CONSTRAINT "financial_backup_snapshots_pkey" PRIMARY KEY (backup_id);

ALTER TABLE "public"."account_access" ADD CONSTRAINT "account_access_pkey" PRIMARY KEY (user_id);

ALTER TABLE "public"."admin_audit_logs" ADD CONSTRAINT "admin_audit_logs_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."categories" ADD CONSTRAINT "categories_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."coaching_sessions" ADD CONSTRAINT "coaching_sessions_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."export_contents" ADD CONSTRAINT "export_contents_pkey" PRIMARY KEY (export_id, content_type);

ALTER TABLE "public"."knowledge_documents" ADD CONSTRAINT "knowledge_documents_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."knowledge_revisions" ADD CONSTRAINT "knowledge_revisions_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."knowledge_sources" ADD CONSTRAINT "knowledge_sources_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."monthly_budgets" ADD CONSTRAINT "monthly_budgets_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_pkey" PRIMARY KEY (user_id);

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_pkey" PRIMARY KEY (attempt_id);

ALTER TABLE "public"."reports" ADD CONSTRAINT "reports_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."savings_contributions" ADD CONSTRAINT "savings_contributions_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."savings_goals" ADD CONSTRAINT "savings_goals_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."user_categories" ADD CONSTRAINT "user_categories_pkey" PRIMARY KEY (user_id, category_id);

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_pkey" PRIMARY KEY (id);

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_user_id_dedupe_key_key" UNIQUE (user_id, dedupe_key);

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_user_id_category_id_month_key" UNIQUE (user_id, category_id, month);

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_reply_to_message_id_key" UNIQUE (reply_to_message_id);

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_assistant_message_id_knowledge_document_key" UNIQUE (assistant_message_id, knowledge_document_id);

ALTER TABLE "public"."knowledge_revisions" ADD CONSTRAINT "knowledge_revisions_source_id_id_key" UNIQUE (source_id, id);

ALTER TABLE "public"."knowledge_sources" ADD CONSTRAINT "knowledge_sources_source_key_key" UNIQUE (source_key);

ALTER TABLE "public"."monthly_budgets" ADD CONSTRAINT "monthly_budgets_user_id_month_key" UNIQUE (user_id, month);

ALTER TABLE "public"."reports" ADD CONSTRAINT "reports_user_report_key_key" UNIQUE (user_id, report_key);

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_expo_push_token_key" UNIQUE (expo_push_token);

ALTER TABLE "public"."account_access" ADD CONSTRAINT "account_access_role_check" CHECK ((role = ANY (ARRAY['student'::text, 'admin'::text])));

ALTER TABLE "public"."account_access" ADD CONSTRAINT "account_access_status_check" CHECK ((status = ANY (ARRAY['active'::text, 'suspended'::text])));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_dedupe_key_check" CHECK (((char_length(btrim(dedupe_key)) >= 1) AND (char_length(btrim(dedupe_key)) <= 200)));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_delivery_attempt_count_check" CHECK (((delivery_attempt_count >= 0) AND (delivery_attempt_count <= 100)));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_delivery_error_check" CHECK (((delivery_error IS NULL) OR (char_length(delivery_error) <= 1000)));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_delivery_status_check" CHECK ((delivery_status = ANY (ARRAY['pending'::text, 'sending'::text, 'sent'::text, 'delivered'::text, 'partially_delivered'::text, 'retryable'::text, 'failed'::text, 'no_active_device'::text])));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_kind_check" CHECK ((kind = ANY (ARRAY['alert'::text, 'insight'::text])));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_message_check" CHECK (((char_length(btrim(message)) >= 1) AND (char_length(btrim(message)) <= 500)));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_title_check" CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 100)));

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_type_check" CHECK ((type = ANY (ARRAY['budget_warning'::text, 'budget_exceeded'::text, 'savings_deadline'::text, 'savings_milestone'::text, 'spending_reminder'::text, 'bill_reminder'::text])));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_attachment_count_check" CHECK ((attachment_count >= 0));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_backup_type_check" CHECK ((backup_type = ANY (ARRAY['manual'::text, 'automatic'::text])));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_checksum_sha256_check" CHECK (((checksum_sha256 IS NULL) OR (checksum_sha256 ~ '^[a-f0-9]{64}$'::text)));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_file_name_check" CHECK (((char_length(btrim(file_name)) >= 1) AND (char_length(btrim(file_name)) <= 255)));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_file_size_bytes_check" CHECK (((file_size_bytes IS NULL) OR (file_size_bytes >= 0)));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_last_restore_status_check" CHECK (((last_restore_status IS NULL) OR (last_restore_status = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text]))));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_schema_version_check" CHECK ((schema_version > 0));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text])));

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_storage_path_check" CHECK (((storage_path IS NULL) OR ((char_length(storage_path) >= 1) AND (char_length(storage_path) <= 512))));

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_amount_positive_check" CHECK ((amount > (0)::numeric));

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_month_first_day_check" CHECK ((month = (date_trunc('month'::text, (month)::timestamp with time zone))::date));

ALTER TABLE "public"."categories" ADD CONSTRAINT "categories_type_check" CHECK ((type = ANY (ARRAY['expense'::text, 'income'::text])));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_prompt_tokens_check" CHECK (((prompt_tokens IS NULL) OR (prompt_tokens >= 0)));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_completion_tokens_check" CHECK (((completion_tokens IS NULL) OR (completion_tokens >= 0)));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_content_check" CHECK (((char_length(btrim(content)) >= 1) AND (char_length(btrim(content)) <= 8000)));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_feedback_check" CHECK (((feedback IS NULL) OR ((role = 'assistant'::text) AND (feedback = ANY (ARRAY['helpful'::text, 'not_helpful'::text])))));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_reply_shape_check" CHECK ((((role = 'user'::text) AND (reply_to_message_id IS NULL)) OR ((role = 'assistant'::text) AND (reply_to_message_id IS NOT NULL))));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_role_check" CHECK ((role = ANY (ARRAY['user'::text, 'assistant'::text])));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_status_check" CHECK ((status = ANY (ARRAY['completed'::text, 'failed'::text])));

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_ui_payload_object_check" CHECK ((jsonb_typeof(ui_payload) = 'object'::text));

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_rank_check" CHECK (((rank >= 1) AND (rank <= 10)));

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_similarity_check" CHECK (((similarity >= ('-1'::integer)::double precision) AND (similarity <= (1)::double precision)));

ALTER TABLE "public"."coaching_sessions" ADD CONSTRAINT "coaching_sessions_title_check" CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 80)));

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_date_range_check" CHECK ((date_from <= date_to));

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_file_name_check" CHECK (((char_length(btrim(file_name)) >= 1) AND (char_length(btrim(file_name)) <= 255)));

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_file_size_bytes_check" CHECK (((file_size_bytes IS NULL) OR (file_size_bytes >= 0)));

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_format_check" CHECK ((format = ANY (ARRAY['csv'::text, 'pdf'::text])));

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text])));

ALTER TABLE "public"."export_contents" ADD CONSTRAINT "export_contents_content_type_check" CHECK ((content_type = ANY (ARRAY['transaction'::text, 'budget'::text, 'savings'::text, 'report'::text])));

ALTER TABLE "public"."knowledge_revisions" ADD CONSTRAINT "knowledge_revisions_status_check" CHECK ((status = ANY (ARRAY['draft'::text, 'queued'::text, 'processing'::text, 'ready'::text, 'published'::text, 'failed'::text])));

ALTER TABLE "public"."monthly_budgets" ADD CONSTRAINT "monthly_budgets_limit_amount_check" CHECK ((limit_amount > (0)::numeric));

ALTER TABLE "public"."monthly_budgets" ADD CONSTRAINT "monthly_budgets_month_first_day_check" CHECK ((month = (date_trunc('month'::text, (month)::timestamp with time zone))::date));

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_bill_lead_days_check" CHECK (((default_bill_lead_days >= 0) AND (default_bill_lead_days <= 365)));

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_savings_lead_days_check" CHECK (((savings_lead_days >= 0) AND (savings_lead_days <= 365)));

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_spending_frequency_check" CHECK ((spending_frequency = ANY (ARRAY['daily'::text, 'weekly'::text])));

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_spending_weekday_check" CHECK (((spending_weekday IS NULL) OR ((spending_weekday >= 0) AND (spending_weekday <= 6))));

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_timezone_check" CHECK (((char_length(btrim(timezone)) >= 1) AND (char_length(btrim(timezone)) <= 100)));

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_amount_check" CHECK (((amount IS NULL) OR (amount > (0)::numeric)));

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_lead_days_check" CHECK (((lead_days >= 0) AND (lead_days <= 365)));

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_recurrence_anchor_day_check" CHECK (((recurrence_anchor_day >= 1) AND (recurrence_anchor_day <= 31)));

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_recurrence_check" CHECK ((recurrence = ANY (ARRAY['none'::text, 'weekly'::text, 'monthly'::text, 'yearly'::text])));

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_title_check" CHECK (((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 100)));

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_type_check" CHECK ((type = 'bill'::text));

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_dates_check" CHECK ((start_date <= end_date));

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_path_check" CHECK ((storage_path = ((((user_id)::text || '/coach/'::text) || (attempt_id)::text) || '.pdf'::text)));

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_status_check" CHECK ((status = ANY (ARRAY['active'::text, 'completed'::text, 'cancelled'::text, 'superseded'::text])));

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_type_check" CHECK ((report_type = ANY (ARRAY['monthly'::text, 'monthly_category'::text, 'multi_month'::text, 'multi_month_category'::text, 'custom'::text, 'custom_category'::text])));

ALTER TABLE "public"."reports" ADD CONSTRAINT "reports_pdf_metadata_check" CHECK (((report_key IS NULL) OR ((title IS NOT NULL) AND (file_name IS NOT NULL) AND (storage_path IS NOT NULL) AND ((char_length(btrim(title)) >= 1) AND (char_length(btrim(title)) <= 160)) AND ((char_length(btrim(file_name)) >= 5) AND (char_length(btrim(file_name)) <= 255)) AND (file_name ~~ '%.pdf'::text) AND ((char_length(btrim(storage_path)) >= 5) AND (char_length(btrim(storage_path)) <= 512)) AND (storage_path ~~ ((user_id)::text || '/%'::text)) AND (start_date IS NOT NULL) AND (end_date IS NOT NULL) AND (start_date <= end_date)))) NOT VALID;

ALTER TABLE "public"."reports" ADD CONSTRAINT "reports_period_length_check" CHECK (((char_length(btrim(period)) >= 7) AND (char_length(btrim(period)) <= 50))) NOT VALID;

ALTER TABLE "public"."reports" ADD CONSTRAINT "reports_type_check" CHECK ((type = ANY (ARRAY['monthly'::text, 'monthly_category'::text, 'multi_month'::text, 'multi_month_category'::text, 'custom'::text, 'custom_category'::text]))) NOT VALID;

ALTER TABLE "public"."savings_contributions" ADD CONSTRAINT "savings_contributions_amount_check" CHECK ((amount > (0)::numeric));

ALTER TABLE "public"."savings_contributions" ADD CONSTRAINT "savings_contributions_contributed_on_check" CHECK ((contributed_on <= CURRENT_DATE));

ALTER TABLE "public"."savings_contributions" ADD CONSTRAINT "savings_contributions_note_check" CHECK (((note IS NULL) OR (char_length(note) <= 200)));

ALTER TABLE "public"."savings_goals" ADD CONSTRAINT "savings_goals_current_nonnegative" CHECK ((current_amount >= (0)::numeric)) NOT VALID;

ALTER TABLE "public"."savings_goals" ADD CONSTRAINT "savings_goals_name_not_blank" CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 100))) NOT VALID;

ALTER TABLE "public"."savings_goals" ADD CONSTRAINT "savings_goals_target_covers_current" CHECK ((target_amount >= current_amount)) NOT VALID;

ALTER TABLE "public"."savings_goals" ADD CONSTRAINT "savings_goals_target_positive" CHECK ((target_amount > (0)::numeric)) NOT VALID;

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_amount_check" CHECK ((amount > (0)::numeric));

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_description_check" CHECK (((description IS NULL) OR (char_length(description) <= 300)));

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_receipt_image_path_check" CHECK (((receipt_image_path IS NULL) OR ((char_length(receipt_image_path) >= 1) AND (char_length(receipt_image_path) <= 512))));

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_receipt_items_valid" CHECK (private.valid_receipt_items(receipt_items));

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_source_check" CHECK (((char_length(btrim(source)) >= 1) AND (char_length(btrim(source)) <= 120)));

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_transaction_date_check" CHECK ((transaction_date <= CURRENT_DATE));

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_device_name_check" CHECK (((device_name IS NULL) OR (char_length(device_name) <= 100)));

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_last_error_check" CHECK (((last_error IS NULL) OR (char_length(last_error) <= 1000)));

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_platform_check" CHECK ((platform = ANY (ARRAY['android'::text, 'ios'::text])));

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_token_check" CHECK (((char_length(btrim(expo_push_token)) >= 20) AND (char_length(btrim(expo_push_token)) <= 255)));

ALTER TABLE "private"."coaching_processing_leases" ADD CONSTRAINT "coaching_processing_leases_message_id_fkey" FOREIGN KEY (message_id) REFERENCES public.coaching_messages(id) ON DELETE CASCADE;

ALTER TABLE "private"."financial_backup_snapshots" ADD CONSTRAINT "financial_backup_snapshots_backup_id_fkey" FOREIGN KEY (backup_id) REFERENCES public.backups(id) ON DELETE CASCADE;

ALTER TABLE "private"."financial_backup_snapshots" ADD CONSTRAINT "financial_backup_snapshots_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."account_access" ADD CONSTRAINT "account_access_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."admin_audit_logs" ADD CONSTRAINT "admin_audit_logs_actor_id_fkey" FOREIGN KEY (actor_id) REFERENCES auth.users(id) ON DELETE SET NULL;

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_budget_id_fkey" FOREIGN KEY (budget_id) REFERENCES public.monthly_budgets(id) ON DELETE SET NULL;

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_category_limit_id_fkey" FOREIGN KEY (category_limit_id) REFERENCES public.budgets(id) ON DELETE SET NULL;

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_reminder_id_fkey" FOREIGN KEY (reminder_id) REFERENCES public.reminders(id) ON DELETE SET NULL;

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_savings_goal_id_fkey" FOREIGN KEY (savings_goal_id) REFERENCES public.savings_goals(id) ON DELETE SET NULL;

ALTER TABLE "public"."alerts" ADD CONSTRAINT "alerts_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."backups" ADD CONSTRAINT "backups_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_category_id_fkey" FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_monthly_budget_fkey" FOREIGN KEY (user_id, month) REFERENCES public.monthly_budgets(user_id, month) ON DELETE CASCADE;

ALTER TABLE "public"."budgets" ADD CONSTRAINT "budgets_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."categories" ADD CONSTRAINT "categories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_reply_to_message_id_fkey" FOREIGN KEY (reply_to_message_id) REFERENCES public.coaching_messages(id) ON DELETE SET NULL;

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_session_id_fkey" FOREIGN KEY (session_id) REFERENCES public.coaching_sessions(id) ON DELETE CASCADE;

ALTER TABLE "public"."coaching_messages" ADD CONSTRAINT "coaching_messages_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_assistant_message_id_fkey" FOREIGN KEY (assistant_message_id) REFERENCES public.coaching_messages(id) ON DELETE CASCADE;

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_knowledge_document_id_fkey" FOREIGN KEY (knowledge_document_id) REFERENCES public.knowledge_documents(id) ON DELETE SET NULL;

ALTER TABLE "public"."coaching_retrievals" ADD CONSTRAINT "coaching_retrievals_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."coaching_sessions" ADD CONSTRAINT "coaching_sessions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."data_exports" ADD CONSTRAINT "data_exports_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."export_contents" ADD CONSTRAINT "export_contents_export_id_fkey" FOREIGN KEY (export_id) REFERENCES public.data_exports(id) ON DELETE CASCADE;

ALTER TABLE "public"."knowledge_documents" ADD CONSTRAINT "knowledge_documents_revision_id_fkey" FOREIGN KEY (revision_id) REFERENCES public.knowledge_revisions(id);

ALTER TABLE "public"."knowledge_revisions" ADD CONSTRAINT "knowledge_revisions_created_by_fkey" FOREIGN KEY (created_by) REFERENCES auth.users(id);

ALTER TABLE "public"."knowledge_revisions" ADD CONSTRAINT "knowledge_revisions_source_id_fkey" FOREIGN KEY (source_id) REFERENCES public.knowledge_sources(id);

ALTER TABLE "public"."knowledge_sources" ADD CONSTRAINT "knowledge_sources_id_latest_revision_id_fkey" FOREIGN KEY (id, latest_revision_id) REFERENCES public.knowledge_revisions(source_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE "public"."knowledge_sources" ADD CONSTRAINT "knowledge_sources_id_published_revision_id_fkey" FOREIGN KEY (id, published_revision_id) REFERENCES public.knowledge_revisions(source_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE "public"."monthly_budgets" ADD CONSTRAINT "monthly_budgets_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."notification_preferences" ADD CONSTRAINT "notification_preferences_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."reminders" ADD CONSTRAINT "reminders_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_message_id_fkey" FOREIGN KEY (message_id) REFERENCES public.coaching_messages(id) ON DELETE CASCADE;

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_report_id_fkey" FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE SET NULL;

ALTER TABLE "public"."report_attempts" ADD CONSTRAINT "report_attempts_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."reports" ADD CONSTRAINT "reports_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."savings_contributions" ADD CONSTRAINT "savings_contributions_goal_id_fkey" FOREIGN KEY (goal_id) REFERENCES public.savings_goals(id) ON DELETE CASCADE;

ALTER TABLE "public"."savings_goals" ADD CONSTRAINT "savings_goals_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_category_id_fkey" FOREIGN KEY (category_id) REFERENCES public.categories(id);

ALTER TABLE "public"."transactions" ADD CONSTRAINT "transactions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."user_categories" ADD CONSTRAINT "user_categories_category_id_fkey" FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;

ALTER TABLE "public"."user_categories" ADD CONSTRAINT "user_categories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE "public"."user_devices" ADD CONSTRAINT "user_devices_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE POLICY "account_access_self" ON "public"."account_access" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((user_id = auth.uid()));

CREATE INDEX alerts_inbox_idx ON public.alerts USING btree (user_id, created_at DESC) WHERE (dismissed_at IS NULL);

CREATE INDEX alerts_unread_idx ON public.alerts USING btree (user_id, created_at DESC) WHERE ((read_at IS NULL) AND (dismissed_at IS NULL));

CREATE INDEX alerts_reminder_source_idx ON public.alerts USING btree (reminder_id) WHERE (reminder_id IS NOT NULL);

CREATE INDEX alerts_savings_source_idx ON public.alerts USING btree (savings_goal_id) WHERE (savings_goal_id IS NOT NULL);

CREATE INDEX alerts_budget_source_idx ON public.alerts USING btree (budget_id, category_limit_id) WHERE ((budget_id IS NOT NULL) OR (category_limit_id IS NOT NULL));

CREATE INDEX alerts_delivery_retry_idx ON public.alerts USING btree (next_delivery_attempt_at, created_at) WHERE (delivery_status = ANY (ARRAY['pending'::text, 'retryable'::text, 'sent'::text]));

CREATE TRIGGER deliver_inserted_alert AFTER INSERT ON public.alerts FOR EACH ROW EXECUTE FUNCTION private.notify_inserted_alert();

CREATE POLICY "Users can add own alerts" ON "public"."alerts" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own alerts" ON "public"."alerts" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own alerts" ON "public"."alerts" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."alerts" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX backups_user_created_idx ON public.backups USING btree (user_id, created_at DESC);

CREATE INDEX backups_user_automatic_idx ON public.backups USING btree (user_id, backup_type, status, completed_at DESC);

CREATE POLICY "Users can create own backups" ON "public"."backups" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can delete own backups" ON "public"."backups" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own backups" ON "public"."backups" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own backups" ON "public"."backups" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."backups" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX budgets_user_month_idx ON public.budgets USING btree (user_id, month DESC);

CREATE TRIGGER validate_category_budget_allocations BEFORE INSERT OR UPDATE OF user_id, month, amount ON public.budgets FOR EACH ROW EXECUTE FUNCTION private.validate_budget_allocations();

CREATE POLICY "Users can create own category limits" ON "public"."budgets" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK (((( SELECT auth.uid() AS uid) = user_id) AND (EXISTS ( SELECT 1
   FROM public.categories c
  WHERE ((c.id = budgets.category_id) AND (c.type = 'expense'::text) AND ((c.user_id IS NULL) OR (c.user_id = ( SELECT auth.uid() AS uid))))))));

CREATE POLICY "Users can delete own category limits" ON "public"."budgets" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own category limits" ON "public"."budgets" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own category limits" ON "public"."budgets" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK (((( SELECT auth.uid() AS uid) = user_id) AND (EXISTS ( SELECT 1
   FROM public.categories c
  WHERE ((c.id = budgets.category_id) AND (c.type = 'expense'::text) AND ((c.user_id IS NULL) OR (c.user_id = ( SELECT auth.uid() AS uid))))))));

CREATE POLICY "account_must_be_active" ON "public"."budgets" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE UNIQUE INDEX categories_user_name_unique ON public.categories USING btree (user_id, lower(name)) WHERE (user_id IS NOT NULL);

CREATE UNIQUE INDEX categories_default_name_unique ON public.categories USING btree (lower(name)) WHERE (user_id IS NULL);

CREATE POLICY "Users can create own custom categories" ON "public"."categories" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK (((( SELECT auth.uid() AS uid) = user_id) AND (type = 'expense'::text)));

CREATE POLICY "Users can delete own custom categories" ON "public"."categories" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read visible expense categories" ON "public"."categories" AS PERMISSIVE FOR SELECT TO "authenticated" USING (((user_id IS NULL) OR (( SELECT auth.uid() AS uid) = user_id)));

CREATE POLICY "Users can update own custom categories" ON "public"."categories" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK (((( SELECT auth.uid() AS uid) = user_id) AND (type = 'expense'::text)));

CREATE POLICY "account_must_be_active" ON "public"."categories" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX coaching_messages_history_cursor_idx ON public.coaching_messages USING btree (user_id, session_id, created_at DESC, id DESC);

CREATE INDEX coaching_messages_session_created_idx ON public.coaching_messages USING btree (session_id, created_at);

CREATE INDEX coaching_messages_user_created_idx ON public.coaching_messages USING btree (user_id, created_at DESC) WHERE (role = 'user'::text);

CREATE POLICY "Users can read own coaching messages" ON "public"."coaching_messages" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can send own coaching messages" ON "public"."coaching_messages" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK (((( SELECT auth.uid() AS uid) IS NOT NULL) AND (( SELECT auth.uid() AS uid) = user_id) AND (role = 'user'::text) AND (EXISTS ( SELECT 1
   FROM public.coaching_sessions session
  WHERE ((session.id = coaching_messages.session_id) AND (session.user_id = ( SELECT auth.uid() AS uid)))))));

CREATE POLICY "account_must_be_active" ON "public"."coaching_messages" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX coaching_retrievals_message_rank_idx ON public.coaching_retrievals USING btree (assistant_message_id, rank);

CREATE POLICY "Users can read own coaching retrievals" ON "public"."coaching_retrievals" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."coaching_retrievals" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX coaching_sessions_user_last_message_idx ON public.coaching_sessions USING btree (user_id, last_message_at DESC);

CREATE TRIGGER coaching_sessions_set_updated_at BEFORE UPDATE ON public.coaching_sessions FOR EACH ROW EXECUTE FUNCTION private.set_updated_at();

CREATE POLICY "Users can create own coaching sessions" ON "public"."coaching_sessions" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can delete own coaching sessions" ON "public"."coaching_sessions" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own coaching sessions" ON "public"."coaching_sessions" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own coaching sessions" ON "public"."coaching_sessions" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."coaching_sessions" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX data_exports_user_created_idx ON public.data_exports USING btree (user_id, created_at DESC);

CREATE INDEX data_exports_user_period_idx ON public.data_exports USING btree (user_id, date_from, date_to);

CREATE POLICY "Users can create own data exports" ON "public"."data_exports" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can delete own data exports" ON "public"."data_exports" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own data exports" ON "public"."data_exports" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own data exports" ON "public"."data_exports" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."data_exports" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can create own export contents" ON "public"."export_contents" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((EXISTS ( SELECT 1
   FROM public.data_exports e
  WHERE ((e.id = export_contents.export_id) AND (e.user_id = ( SELECT auth.uid() AS uid))))));

CREATE POLICY "Users can delete own export contents" ON "public"."export_contents" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM public.data_exports e
  WHERE ((e.id = export_contents.export_id) AND (e.user_id = ( SELECT auth.uid() AS uid))))));

CREATE POLICY "Users can read own export contents" ON "public"."export_contents" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM public.data_exports e
  WHERE ((e.id = export_contents.export_id) AND (e.user_id = ( SELECT auth.uid() AS uid))))));

CREATE POLICY "Users can update own export contents" ON "public"."export_contents" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM public.data_exports e
  WHERE ((e.id = export_contents.export_id) AND (e.user_id = ( SELECT auth.uid() AS uid)))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM public.data_exports e
  WHERE ((e.id = export_contents.export_id) AND (e.user_id = ( SELECT auth.uid() AS uid))))));

CREATE POLICY "account_must_be_active" ON "public"."export_contents" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX knowledge_documents_revision_idx ON public.knowledge_documents USING btree (revision_id);

CREATE INDEX knowledge_documents_fts_idx ON public.knowledge_documents USING gin ((((setweight(to_tsvector('simple'::regconfig, COALESCE(title, ''::text)), 'A'::"char") || setweight(to_tsvector('simple'::regconfig, COALESCE(source, ''::text)), 'B'::"char")) || setweight(to_tsvector('simple'::regconfig, content), 'C'::"char")))) WHERE is_published;

CREATE INDEX knowledge_documents_embedding_idx ON public.knowledge_documents USING hnsw (embedding public.vector_cosine_ops) WHERE is_published;

CREATE INDEX knowledge_revisions_queue_idx ON public.knowledge_revisions USING btree (status, lease_until, created_at);

CREATE TRIGGER fincoach_knowledge_publication AFTER UPDATE OF published_revision_id, archived ON public.knowledge_sources FOR EACH ROW EXECUTE FUNCTION private.sync_knowledge_publication();

CREATE INDEX monthly_budgets_user_month_idx ON public.monthly_budgets USING btree (user_id, month DESC);

CREATE TRIGGER validate_monthly_budget_allocations BEFORE INSERT OR UPDATE OF user_id, month, limit_amount ON public.monthly_budgets FOR EACH ROW EXECUTE FUNCTION private.validate_budget_allocations();

CREATE POLICY "Users can create own monthly budgets" ON "public"."monthly_budgets" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can delete own monthly budgets" ON "public"."monthly_budgets" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own monthly budgets" ON "public"."monthly_budgets" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own monthly budgets" ON "public"."monthly_budgets" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."monthly_budgets" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE INDEX notification_preferences_user_updated_idx ON public.notification_preferences USING btree (user_id, updated_at DESC);

CREATE TRIGGER notification_preferences_set_updated_at BEFORE UPDATE ON public.notification_preferences FOR EACH ROW EXECUTE FUNCTION private.set_updated_at();

CREATE POLICY "Users can add own notification preferences" ON "public"."notification_preferences" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."notification_preferences" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can read own notification preferences" ON "public"."notification_preferences" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own notification preferences" ON "public"."notification_preferences" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE INDEX reminders_due_idx ON public.reminders USING btree (next_trigger_at) WHERE ((enabled = true) AND (next_trigger_at IS NOT NULL));

CREATE INDEX reminders_user_due_idx ON public.reminders USING btree (user_id, due_at, created_at DESC);

CREATE TRIGGER reminders_refresh_schedule BEFORE INSERT OR UPDATE OF title, due_at, lead_days, recurrence_anchor_day, enabled ON public.reminders FOR EACH ROW EXECUTE FUNCTION private.refresh_reminder_schedule();

CREATE TRIGGER reminders_set_updated_at BEFORE UPDATE ON public.reminders FOR EACH ROW EXECUTE FUNCTION private.set_updated_at();

CREATE POLICY "Users can add own reminders" ON "public"."reminders" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."reminders" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can delete own reminders" ON "public"."reminders" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own reminders" ON "public"."reminders" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own reminders" ON "public"."reminders" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE INDEX report_attempts_owner_path_idx ON public.report_attempts USING btree (user_id, storage_path);

CREATE INDEX report_attempts_owner_message_idx ON public.report_attempts USING btree (user_id, message_id);

CREATE UNIQUE INDEX report_attempts_active_action_idx ON public.report_attempts USING btree (action_id) WHERE (status = 'active'::text);

CREATE POLICY "account_must_be_active" ON "public"."report_attempts" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can read own report attempts" ON "public"."report_attempts" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE INDEX reports_user_generated_idx ON public.reports USING btree (user_id, generated_at DESC);

CREATE POLICY "Users can create own reports" ON "public"."reports" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK (((( SELECT auth.uid() AS uid) = user_id) AND (COALESCE(report_key, ''::text) !~~ 'coach:%'::text) AND (COALESCE((storage.foldername(storage_path))[2], ''::text) <> 'coach'::text)));

CREATE POLICY "account_must_be_active" ON "public"."reports" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can read own reports" ON "public"."reports" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can update own reports" ON "public"."reports" AS PERMISSIVE FOR UPDATE TO "authenticated" USING (((( SELECT auth.uid() AS uid) = user_id) AND (COALESCE(report_key, ''::text) !~~ 'coach:%'::text))) WITH CHECK (((( SELECT auth.uid() AS uid) = user_id) AND (COALESCE(report_key, ''::text) !~~ 'coach:%'::text) AND (COALESCE((storage.foldername(storage_path))[2], ''::text) <> 'coach'::text)));

CREATE INDEX savings_contributions_history_idx ON public.savings_contributions USING btree (goal_id, contributed_on DESC, created_at DESC);

CREATE TRIGGER refresh_savings_goal_amount AFTER INSERT OR DELETE ON public.savings_contributions FOR EACH ROW EXECUTE FUNCTION private.refresh_savings_goal_amount();

CREATE POLICY "Users can add own savings contributions" ON "public"."savings_contributions" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((EXISTS ( SELECT 1
   FROM public.savings_goals g
  WHERE ((g.id = savings_contributions.goal_id) AND (g.user_id = ( SELECT auth.uid() AS uid))))));

CREATE POLICY "Users can delete own savings contributions" ON "public"."savings_contributions" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM public.savings_goals g
  WHERE ((g.id = savings_contributions.goal_id) AND (g.user_id = ( SELECT auth.uid() AS uid))))));

CREATE POLICY "account_must_be_active" ON "public"."savings_contributions" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can read own savings contributions" ON "public"."savings_contributions" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((EXISTS ( SELECT 1
   FROM public.savings_goals g
  WHERE ((g.id = savings_contributions.goal_id) AND (g.user_id = ( SELECT auth.uid() AS uid))))));

CREATE INDEX savings_goals_user_id_idx ON public.savings_goals USING btree (user_id);

CREATE POLICY "Users can add own savings goals" ON "public"."savings_goals" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can delete own savings goals" ON "public"."savings_goals" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own savings goals" ON "public"."savings_goals" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."savings_goals" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can update own savings goals" ON "public"."savings_goals" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "savings_goals delete own" ON "public"."savings_goals" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((auth.uid() = user_id));

CREATE POLICY "savings_goals insert own" ON "public"."savings_goals" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((auth.uid() = user_id));

CREATE POLICY "savings_goals select own" ON "public"."savings_goals" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((auth.uid() = user_id));

CREATE POLICY "savings_goals update own" ON "public"."savings_goals" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));

CREATE INDEX transactions_user_category_date_idx ON public.transactions USING btree (user_id, category_id, transaction_date DESC);

CREATE INDEX transactions_user_date_idx ON public.transactions USING btree (user_id, transaction_date DESC, created_at DESC);

CREATE TRIGGER validate_transaction_category BEFORE INSERT OR UPDATE OF user_id, category_id, source, description ON public.transactions FOR EACH ROW EXECUTE FUNCTION private.validate_transaction_category();

CREATE POLICY "Users can add own transactions" ON "public"."transactions" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can delete own transactions" ON "public"."transactions" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "Users can read own transactions" ON "public"."transactions" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."transactions" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users can update own transactions" ON "public"."transactions" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((( SELECT auth.uid() AS uid) = user_id)) WITH CHECK ((( SELECT auth.uid() AS uid) = user_id));

CREATE POLICY "account_must_be_active" ON "public"."user_categories" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE POLICY "Users manage own tracked categories" ON "public"."user_categories" AS PERMISSIVE FOR ALL TO "authenticated" USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id));

CREATE INDEX user_devices_active_idx ON public.user_devices USING btree (user_id, last_seen_at DESC) WHERE (active = true);

CREATE TRIGGER user_devices_set_updated_at BEFORE UPDATE ON public.user_devices FOR EACH ROW EXECUTE FUNCTION private.set_updated_at();

CREATE POLICY "account_must_be_active" ON "public"."user_devices" AS RESTRICTIVE FOR ALL TO "authenticated" USING (private.is_active_account()) WITH CHECK (private.is_active_account());

CREATE VIEW public.published_knowledge_documents WITH (security_invoker=true) AS SELECT * FROM public.knowledge_documents WHERE is_published;

DROP POLICY IF EXISTS "Users can upload own financial reports" ON storage.objects;

CREATE POLICY "Users can upload own financial reports" ON "storage"."objects" FOR INSERT TO "authenticated" WITH CHECK ((("bucket_id" = 'financial-reports'::"text") AND (("storage"."foldername"("name"))[1] = ( SELECT ("auth"."uid"())::"text" AS "uid")) AND ((COALESCE(("storage"."foldername"("name"))[2], ''::"text") <> 'coach'::"text") OR (EXISTS ( SELECT 1
   FROM "public"."report_attempts" "a"
  WHERE (("a"."user_id" = ( SELECT "auth"."uid"() AS "uid")) AND ("a"."storage_path" = "objects"."name") AND ("a"."status" = 'active'::"text") AND ("a"."lease_expires_at" > "clock_timestamp"())))))));

GRANT USAGE ON SCHEMA "private" TO "authenticated";

GRANT USAGE ON SCHEMA "private" TO "service_role";

GRANT USAGE ON SCHEMA "public" TO "postgres";

GRANT USAGE ON SCHEMA "public" TO "anon";

GRANT USAGE ON SCHEMA "public" TO "authenticated";

GRANT USAGE ON SCHEMA "public" TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_in"("cstring", "oid", integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_out"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_recv"("internal", "oid", integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_send"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_typmod_in"("cstring"[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_in"("cstring", "oid", integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_out"("public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_recv"("internal", "oid", integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_send"("public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_typmod_in"("cstring"[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_in"("cstring", "oid", integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_out"("public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_recv"("internal", "oid", integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_send"("public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_typmod_in"("cstring"[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(real[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(real[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_vector"(real[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(double precision[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(double precision[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_vector"(double precision[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(integer[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(integer[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_vector"(integer[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_halfvec"(numeric[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_sparsevec"(numeric[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."array_to_vector"(numeric[], integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_to_float4"("public"."halfvec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec"("public"."halfvec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_to_sparsevec"("public"."halfvec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_to_vector"("public"."halfvec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_to_halfvec"("public"."sparsevec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec"("public"."sparsevec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_to_vector"("public"."sparsevec", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_to_float4"("public"."vector", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_to_halfvec"("public"."vector", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_to_sparsevec"("public"."vector", integer, boolean) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "anon";

GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector"("public"."vector", integer, boolean) TO "service_role";

REVOKE ALL ON FUNCTION "private"."is_active_account"() FROM PUBLIC;

GRANT ALL ON FUNCTION "private"."is_active_account"() TO "authenticated";

REVOKE ALL ON FUNCTION "private"."notify_inserted_alert"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."refresh_savings_goal_amount"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."require_admin"("p_actor" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "private"."require_admin"("p_actor" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "private"."restore_financial_backup_v1"("payload" "jsonb", "backup_record_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "private"."restore_financial_backup_v1"("payload" "jsonb", "backup_record_id" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "private"."sync_account_access"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."sync_knowledge_publication"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."sync_profile_account_name"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."valid_receipt_items"("items" "jsonb") FROM PUBLIC;

GRANT ALL ON FUNCTION "private"."valid_receipt_items"("items" "jsonb") TO "authenticated";

GRANT ALL ON FUNCTION "private"."valid_receipt_items"("items" "jsonb") TO "service_role";

REVOKE ALL ON FUNCTION "private"."validate_budget_allocations"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."validate_financial_backup_data"("data" "jsonb", "owner_id" "uuid") FROM PUBLIC;

REVOKE ALL ON FUNCTION "private"."validate_transaction_category"() FROM PUBLIC;

REVOKE ALL ON FUNCTION "public"."admin_claim_knowledge_revision"() FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_claim_knowledge_revision"() TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_fail_knowledge_revision"("p_revision" "uuid", "p_lease" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_fail_knowledge_revision"("p_revision" "uuid", "p_lease" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_finish_knowledge_revision"("p_revision" "uuid", "p_lease" "uuid", "p_chunks" "jsonb") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_finish_knowledge_revision"("p_revision" "uuid", "p_lease" "uuid", "p_chunks" "jsonb") TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_knowledge_action"("p_actor" "uuid", "p_source" "uuid", "p_revision" "uuid", "p_action" "text", "p_expected" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_knowledge_action"("p_actor" "uuid", "p_source" "uuid", "p_revision" "uuid", "p_action" "text", "p_expected" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_recoverable_alerts"("p_now" timestamp with time zone, "p_limit" integer) FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_recoverable_alerts"("p_now" timestamp with time zone, "p_limit" integer) TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_renew_knowledge_lease"("p_revision" "uuid", "p_lease" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_renew_knowledge_lease"("p_revision" "uuid", "p_lease" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_save_knowledge_revision"("p_actor" "uuid", "p_source" "uuid", "p_title" "text", "p_content" "text", "p_urls" "jsonb", "p_checked" "date", "p_file_path" "text", "p_expected" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_save_knowledge_revision"("p_actor" "uuid", "p_source" "uuid", "p_title" "text", "p_content" "text", "p_urls" "jsonb", "p_checked" "date", "p_file_path" "text", "p_expected" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."admin_set_account_status"("p_actor" "uuid", "p_user" "uuid", "p_status" "text", "p_reason" "text", "p_expected" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."admin_set_account_status"("p_actor" "uuid", "p_user" "uuid", "p_status" "text", "p_reason" "text", "p_expected" "text") TO "service_role";

GRANT ALL ON FUNCTION "public"."auth_methods_for_email"("p_email" "text") TO "anon";

GRANT ALL ON FUNCTION "public"."auth_methods_for_email"("p_email" "text") TO "authenticated";

GRANT ALL ON FUNCTION "public"."auth_methods_for_email"("p_email" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."begin_financial_backup_delete_v2"("backup_record_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."begin_financial_backup_delete_v2"("backup_record_id" "uuid") TO "authenticated";

GRANT ALL ON FUNCTION "public"."begin_financial_backup_delete_v2"("backup_record_id" "uuid") TO "service_role";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."binary_quantize"("public"."vector") TO "service_role";

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."alerts" TO "authenticated";

GRANT ALL ON TABLE "public"."alerts" TO "service_role";

GRANT INSERT("user_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("type") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("kind") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("title") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("message") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("budget_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("category_limit_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("savings_goal_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("reminder_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("source_data") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("dedupe_key") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT("scheduled_for") ON TABLE "public"."alerts" TO "authenticated";

GRANT UPDATE("read_at") ON TABLE "public"."alerts" TO "authenticated";

GRANT UPDATE("dismissed_at") ON TABLE "public"."alerts" TO "authenticated";

REVOKE ALL ON FUNCTION "public"."claim_alert_delivery"("p_alert_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_alert_delivery"("p_alert_id" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."claim_bill_reminder_occurrence"("p_reminder_id" "uuid", "p_expected_trigger_at" timestamp with time zone, "p_next_due_at" timestamp with time zone, "p_title" "text", "p_message" "text", "p_dedupe_key" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_bill_reminder_occurrence"("p_reminder_id" "uuid", "p_expected_trigger_at" timestamp with time zone, "p_next_due_at" timestamp with time zone, "p_title" "text", "p_message" "text", "p_dedupe_key" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."claim_coach_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid", "p_attempt_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_coach_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid", "p_attempt_id" "uuid") TO "service_role";

GRANT ALL ON TABLE "public"."coaching_messages" TO "anon";

GRANT ALL ON TABLE "public"."coaching_messages" TO "authenticated";

GRANT ALL ON TABLE "public"."coaching_messages" TO "service_role";

REVOKE ALL ON FUNCTION "public"."claim_coaching_message"("p_user_id" "uuid", "p_message_id" "uuid", "p_token" "uuid", "p_session_id" "uuid", "p_content" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_coaching_message"("p_user_id" "uuid", "p_message_id" "uuid", "p_token" "uuid", "p_session_id" "uuid", "p_content" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."commit_coach_action"("p_user_id" "uuid", "p_message_id" "uuid", "p_expected_payload" "jsonb", "p_next_payload" "jsonb", "p_reminder" "jsonb") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."commit_coach_action"("p_user_id" "uuid", "p_message_id" "uuid", "p_expected_payload" "jsonb", "p_next_payload" "jsonb", "p_reminder" "jsonb") TO "service_role";

REVOKE ALL ON FUNCTION "public"."complete_coach_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid", "p_attempt_id" "uuid", "p_success" boolean, "p_report" "jsonb", "p_storage" "jsonb") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."complete_coach_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid", "p_attempt_id" "uuid", "p_success" boolean, "p_report" "jsonb", "p_storage" "jsonb") TO "service_role";

REVOKE ALL ON FUNCTION "public"."complete_coaching_turn"("p_user_id" "uuid", "p_session_id" "uuid", "p_user_message_id" "uuid", "p_assistant_message" "jsonb", "p_retrievals" "jsonb", "p_title" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."complete_coaching_turn"("p_user_id" "uuid", "p_session_id" "uuid", "p_user_message_id" "uuid", "p_assistant_message" "jsonb", "p_retrievals" "jsonb", "p_title" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."complete_coaching_turn_leased"("p_user_id" "uuid", "p_session_id" "uuid", "p_user_message_id" "uuid", "p_assistant_message" "jsonb", "p_retrievals" "jsonb", "p_title" "text", "p_token" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."complete_coaching_turn_leased"("p_user_id" "uuid", "p_session_id" "uuid", "p_user_message_id" "uuid", "p_assistant_message" "jsonb", "p_retrievals" "jsonb", "p_title" "text", "p_token" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."complete_financial_backup_v2"("backup_record_id" "uuid", "document" "jsonb", "object_path" "text", "object_size" bigint, "checksum" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."complete_financial_backup_v2"("backup_record_id" "uuid", "document" "jsonb", "object_path" "text", "object_size" bigint, "checksum" "text") TO "authenticated";

GRANT ALL ON FUNCTION "public"."complete_financial_backup_v2"("backup_record_id" "uuid", "document" "jsonb", "object_path" "text", "object_size" bigint, "checksum" "text") TO "service_role";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."cosine_distance"("public"."vector", "public"."vector") TO "service_role";

REVOKE ALL ON FUNCTION "public"."deactivate_user_device"("p_user_id" "uuid", "p_expo_push_token" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."deactivate_user_device"("p_user_id" "uuid", "p_expo_push_token" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."fail_coaching_message"("p_user_id" "uuid", "p_message_id" "uuid", "p_token" "uuid", "p_error_code" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."fail_coaching_message"("p_user_id" "uuid", "p_message_id" "uuid", "p_token" "uuid", "p_error_code" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."financial_backup_snapshot_v2"("backup_record_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."financial_backup_snapshot_v2"("backup_record_id" "uuid") TO "authenticated";

GRANT ALL ON FUNCTION "public"."financial_backup_snapshot_v2"("backup_record_id" "uuid") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_accum"(double precision[], "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_add"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_avg"(double precision[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_cmp"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_combine"(double precision[], double precision[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_concat"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_eq"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_ge"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_gt"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_l2_squared_distance"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_le"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_lt"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_mul"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_ne"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_negative_inner_product"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_spherical_distance"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."halfvec_sub"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "postgres";

GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "anon";

GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "authenticated";

GRANT ALL ON FUNCTION "public"."hamming_distance"(bit, bit) TO "service_role";

GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."hnsw_bit_support"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."hnsw_halfvec_support"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."hnsw_sparsevec_support"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."hnswhandler"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."inner_product"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."ivfflat_bit_support"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."ivfflat_halfvec_support"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "postgres";

GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "anon";

GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "authenticated";

GRANT ALL ON FUNCTION "public"."ivfflathandler"("internal") TO "service_role";

GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "postgres";

GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "anon";

GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "authenticated";

GRANT ALL ON FUNCTION "public"."jaccard_distance"(bit, bit) TO "service_role";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l1_distance"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."halfvec", "public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_distance"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_norm"("public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."l2_normalize"("public"."vector") TO "service_role";

REVOKE ALL ON FUNCTION "public"."list_abandoned_coach_report_artifacts"("p_after_created" timestamp with time zone, "p_after_id" "uuid", "p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."list_abandoned_coach_report_artifacts"("p_after_created" timestamp with time zone, "p_after_id" "uuid", "p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."match_knowledge_documents"("query_embedding" "public"."vector", "match_count" integer) FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."match_knowledge_documents"("query_embedding" "public"."vector", "match_count" integer) TO "service_role";

REVOKE ALL ON FUNCTION "public"."match_knowledge_documents_hybrid"("query_text" "text", "query_embedding" "public"."vector", "match_count" integer) FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."match_knowledge_documents_hybrid"("query_text" "text", "query_embedding" "public"."vector", "match_count" integer) TO "service_role";

GRANT ALL ON TABLE "public"."user_devices" TO "service_role";

REVOKE ALL ON FUNCTION "public"."reassign_user_device"("p_user_id" "uuid", "p_expo_push_token" "text", "p_platform" "text", "p_device_name" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."reassign_user_device"("p_user_id" "uuid", "p_expo_push_token" "text", "p_platform" "text", "p_device_name" "text") TO "service_role";

GRANT ALL ON TABLE "public"."report_attempts" TO "service_role";

GRANT SELECT ON TABLE "public"."report_attempts" TO "authenticated";

REVOKE ALL ON FUNCTION "public"."renew_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_attempt_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."renew_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_attempt_id" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."replace_tracked_categories"("p_user_id" "uuid", "p_category_ids" bigint[]) FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."replace_tracked_categories"("p_user_id" "uuid", "p_category_ids" bigint[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."replace_tracked_categories"("p_user_id" "uuid", "p_category_ids" bigint[]) TO "service_role";

REVOKE ALL ON FUNCTION "public"."restore_financial_backup_v1"("payload" "jsonb", "backup_record_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."restore_financial_backup_v1"("payload" "jsonb", "backup_record_id" "uuid") TO "authenticated";

GRANT ALL ON FUNCTION "public"."restore_financial_backup_v1"("payload" "jsonb", "backup_record_id" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."restore_financial_backup_v2"("payload" "jsonb", "backup_record_id" "uuid", "restored_paths" "jsonb") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."restore_financial_backup_v2"("payload" "jsonb", "backup_record_id" "uuid", "restored_paths" "jsonb") TO "authenticated";

GRANT ALL ON FUNCTION "public"."restore_financial_backup_v2"("payload" "jsonb", "backup_record_id" "uuid", "restored_paths" "jsonb") TO "service_role";

REVOKE ALL ON FUNCTION "public"."save_budget_month"("p_user_id" "uuid", "p_month" "date", "p_overall" numeric, "p_allocations" "jsonb") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."save_budget_month"("p_user_id" "uuid", "p_month" "date", "p_overall" numeric, "p_allocations" "jsonb") TO "authenticated";

GRANT ALL ON FUNCTION "public"."save_budget_month"("p_user_id" "uuid", "p_month" "date", "p_overall" numeric, "p_allocations" "jsonb") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_cmp"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_eq"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_ge"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_gt"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_l2_squared_distance"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_le"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_lt"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_ne"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "anon";

GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sparsevec_negative_inner_product"("public"."sparsevec", "public"."sparsevec") TO "service_role";

GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "anon";

GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."subvector"("public"."halfvec", integer, integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "postgres";

GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "anon";

GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "authenticated";

GRANT ALL ON FUNCTION "public"."subvector"("public"."vector", integer, integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_accum"(double precision[], "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_add"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_avg"(double precision[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_cmp"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "anon";

GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_combine"(double precision[], double precision[]) TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_concat"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_dims"("public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_eq"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_ge"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_gt"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_l2_squared_distance"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_le"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_lt"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_mul"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_ne"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_negative_inner_product"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_norm"("public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_spherical_distance"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."vector_sub"("public"."vector", "public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."avg"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."avg"("public"."vector") TO "service_role";

GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "postgres";

GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "anon";

GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sum"("public"."halfvec") TO "service_role";

GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "postgres";

GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "anon";

GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "authenticated";

GRANT ALL ON FUNCTION "public"."sum"("public"."vector") TO "service_role";

GRANT ALL ON TABLE "public"."account_access" TO "service_role";

GRANT SELECT("user_id") ON TABLE "public"."account_access" TO "authenticated";

GRANT SELECT("role") ON TABLE "public"."account_access" TO "authenticated";

GRANT SELECT("status") ON TABLE "public"."account_access" TO "authenticated";

GRANT ALL ON TABLE "public"."admin_audit_logs" TO "service_role";

GRANT ALL ON SEQUENCE "public"."admin_audit_logs_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."admin_audit_logs_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."admin_audit_logs_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."backups" TO "authenticated";

GRANT ALL ON TABLE "public"."backups" TO "service_role";

GRANT ALL ON TABLE "public"."budgets" TO "anon";

GRANT ALL ON TABLE "public"."budgets" TO "authenticated";

GRANT ALL ON TABLE "public"."budgets" TO "service_role";

GRANT ALL ON SEQUENCE "public"."budgets_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."budgets_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."budgets_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."categories" TO "anon";

GRANT ALL ON TABLE "public"."categories" TO "authenticated";

GRANT ALL ON TABLE "public"."categories" TO "service_role";

GRANT ALL ON SEQUENCE "public"."categories_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."categories_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."categories_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."coaching_retrievals" TO "anon";

GRANT ALL ON TABLE "public"."coaching_retrievals" TO "authenticated";

GRANT ALL ON TABLE "public"."coaching_retrievals" TO "service_role";

GRANT ALL ON SEQUENCE "public"."coaching_retrievals_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."coaching_retrievals_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."coaching_retrievals_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."coaching_sessions" TO "anon";

GRANT ALL ON TABLE "public"."coaching_sessions" TO "authenticated";

GRANT ALL ON TABLE "public"."coaching_sessions" TO "service_role";

GRANT ALL ON TABLE "public"."data_exports" TO "authenticated";

GRANT ALL ON TABLE "public"."data_exports" TO "service_role";

GRANT ALL ON TABLE "public"."export_contents" TO "authenticated";

GRANT ALL ON TABLE "public"."export_contents" TO "service_role";

GRANT ALL ON TABLE "public"."knowledge_documents" TO "service_role";

GRANT ALL ON SEQUENCE "public"."knowledge_documents_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."knowledge_documents_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."knowledge_documents_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."knowledge_revisions" TO "service_role";

GRANT ALL ON TABLE "public"."knowledge_sources" TO "service_role";

GRANT ALL ON TABLE "public"."monthly_budgets" TO "anon";

GRANT ALL ON TABLE "public"."monthly_budgets" TO "authenticated";

GRANT ALL ON TABLE "public"."monthly_budgets" TO "service_role";

GRANT ALL ON TABLE "public"."notification_preferences" TO "authenticated";

GRANT ALL ON TABLE "public"."notification_preferences" TO "service_role";

GRANT ALL ON TABLE "public"."profiles" TO "anon";

GRANT ALL ON TABLE "public"."profiles" TO "authenticated";

GRANT ALL ON TABLE "public"."profiles" TO "service_role";

GRANT ALL ON TABLE "public"."published_knowledge_documents" TO "service_role";

GRANT ALL ON TABLE "public"."reminders" TO "authenticated";

GRANT ALL ON TABLE "public"."reminders" TO "service_role";

GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN,UPDATE ON TABLE "public"."reports" TO "authenticated";

GRANT ALL ON TABLE "public"."reports" TO "service_role";

GRANT ALL ON SEQUENCE "public"."reports_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."reports_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."reports_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."savings_contributions" TO "authenticated";

GRANT ALL ON TABLE "public"."savings_contributions" TO "service_role";

GRANT ALL ON SEQUENCE "public"."savings_contributions_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."savings_contributions_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."savings_contributions_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."savings_goals" TO "anon";

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."savings_goals" TO "authenticated";

GRANT ALL ON TABLE "public"."savings_goals" TO "service_role";

GRANT UPDATE("name") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE("target_amount") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE("updated_at") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE("deadline") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT ALL ON TABLE "public"."transactions" TO "authenticated";

GRANT ALL ON TABLE "public"."transactions" TO "service_role";

GRANT ALL ON TABLE "public"."user_categories" TO "anon";

GRANT ALL ON TABLE "public"."user_categories" TO "authenticated";

GRANT ALL ON TABLE "public"."user_categories" TO "service_role";

GRANT EXECUTE ON FUNCTION private.set_updated_at() TO PUBLIC;

GRANT EXECUTE ON FUNCTION private.handle_new_user_profile() TO PUBLIC;

GRANT EXECUTE ON FUNCTION private.refresh_reminder_schedule() TO PUBLIC;

DROP FUNCTION IF EXISTS private.trial_r05_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r07_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r11_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r16_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r17_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r18_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r19_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r19_trigger_1();

DROP FUNCTION IF EXISTS private.trial_r22_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r24_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r26_trigger_0();

DROP FUNCTION IF EXISTS private.trial_r22_owner();

DROP FUNCTION IF EXISTS private.trial_r13_owner();

DO $verify$ BEGIN
IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private') AND c.relkind IN ('r','p'))<>27 THEN RAISE EXCEPTION 'Rollback did not recreate exactly 27 application tables'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "private"."coaching_processing_leases" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_0 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_0 t EXCEPT ALL SELECT to_jsonb(t) FROM "private"."coaching_processing_leases" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: private.coaching_processing_leases'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "private"."financial_backup_snapshots" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_1 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_1 t EXCEPT ALL SELECT to_jsonb(t) FROM "private"."financial_backup_snapshots" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: private.financial_backup_snapshots'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."account_access" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_2 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_2 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."account_access" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.account_access'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."admin_audit_logs" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_3 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_3 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."admin_audit_logs" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.admin_audit_logs'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."alerts" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_4 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_4 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."alerts" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.alerts'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."backups" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_5 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_5 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."backups" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.backups'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."budgets" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_6 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_6 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."budgets" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.budgets'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."categories" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_7 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_7 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."categories" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.categories'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."coaching_messages" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_8 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_8 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."coaching_messages" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.coaching_messages'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."coaching_retrievals" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_9 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_9 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."coaching_retrievals" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.coaching_retrievals'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."coaching_sessions" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_10 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_10 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."coaching_sessions" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.coaching_sessions'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."data_exports" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_11 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_11 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."data_exports" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.data_exports'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."export_contents" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_12 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_12 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."export_contents" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.export_contents'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."knowledge_documents" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_13 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_13 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."knowledge_documents" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.knowledge_documents'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."knowledge_revisions" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_14 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_14 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."knowledge_revisions" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.knowledge_revisions'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."knowledge_sources" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_15 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_15 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."knowledge_sources" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.knowledge_sources'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."monthly_budgets" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_16 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_16 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."monthly_budgets" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.monthly_budgets'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."notification_preferences" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_17 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_17 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."notification_preferences" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.notification_preferences'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."reminders" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_18 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_18 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."reminders" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.reminders'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."report_attempts" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_19 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_19 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."report_attempts" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.report_attempts'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."reports" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_20 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_20 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."reports" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.reports'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."savings_contributions" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_21 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_21 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."savings_contributions" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.savings_contributions'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."savings_goals" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_22 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_22 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."savings_goals" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.savings_goals'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."transactions" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_23 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_23 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."transactions" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.transactions'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."user_categories" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_24 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_24 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."user_categories" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.user_categories'; END IF;
IF EXISTS ((SELECT to_jsonb(t) FROM "public"."user_devices" t EXCEPT ALL SELECT to_jsonb(t) FROM rollback_rows_25 t) UNION ALL (SELECT to_jsonb(t) FROM rollback_rows_25 t EXCEPT ALL SELECT to_jsonb(t) FROM "public"."user_devices" t)) THEN RAISE EXCEPTION 'Rollback row mismatch: public.user_devices'; END IF;
END $verify$;

NOTIFY pgrst,'reload schema';

COMMIT;
