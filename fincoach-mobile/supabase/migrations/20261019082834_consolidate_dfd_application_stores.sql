-- Consolidate 27 application tables into 10 DFD stores. Tested against a restored copy.
-- Legacy public/private names remain security-invoker compatibility views.
-- Auth and Storage system tables remain provider-managed.
-- A transaction aborts if source columns or any copied row differ.
-- Inverse migration: docs/database/ten-stores/rollback-current-data.sql

BEGIN;

SET LOCAL check_function_bodies=false;

SET LOCAL lock_timeout='5s';

SET LOCAL search_path=public,extensions,pg_catalog;

LOCK TABLE "private"."coaching_processing_leases", "private"."financial_backup_snapshots", "public"."account_access", "public"."admin_audit_logs", "public"."alerts", "public"."backups", "public"."budgets", "public"."categories", "public"."coaching_messages", "public"."coaching_retrievals", "public"."coaching_sessions", "public"."data_exports", "public"."export_contents", "public"."knowledge_documents", "public"."knowledge_revisions", "public"."knowledge_sources", "public"."monthly_budgets", "public"."notification_preferences", "public"."profiles", "public"."reminders", "public"."report_attempts", "public"."reports", "public"."savings_contributions", "public"."savings_goals", "public"."transactions", "public"."user_categories", "public"."user_devices" IN ACCESS EXCLUSIVE MODE;

CREATE TEMP TABLE trial_expected_rows(name text,rows bigint,digest text) ON COMMIT DROP;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='private.coaching_processing_leases'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['message_id','token','expires_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: private.coaching_processing_leases'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'private.coaching_processing_leases',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "private"."coaching_processing_leases" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='private.financial_backup_snapshots'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['backup_id','user_id','data','document','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: private.financial_backup_snapshots'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'private.financial_backup_snapshots',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "private"."financial_backup_snapshots" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.account_access'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['user_id','role','status','email','display_name','created_at','last_sign_in_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.account_access'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.account_access',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."account_access" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.admin_audit_logs'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','actor_id','action','target_type','target_id','details','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.admin_audit_logs'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.admin_audit_logs',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."admin_audit_logs" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.alerts'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','type','kind','title','message','budget_id','category_limit_id','savings_goal_id','reminder_id','source_data','dedupe_key','scheduled_for','delivered_at','read_at','dismissed_at','delivery_status','delivery_error','delivery_attempt_count','delivery_claimed_at','next_delivery_attempt_at','delivery_receipts','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.alerts'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.alerts',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."alerts" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.backups'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','backup_type','status','file_name','storage_path','file_size_bytes','checksum_sha256','schema_version','last_restore_status','last_restored_at','completed_at','created_at','data_counts','attachment_count','cleanup_warning']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.backups'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.backups',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."backups" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.budgets'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','category_id','amount','month','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.budgets'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.budgets',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."budgets" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.categories'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','name','type','icon','user_id','color','icon_image_path']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.categories'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.categories',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."categories" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.coaching_messages'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','session_id','user_id','role','content','reply_to_message_id','status','error_code','model','prompt_tokens','completion_tokens','created_at','feedback','ui_payload']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.coaching_messages'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.coaching_messages',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."coaching_messages" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.coaching_retrievals'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','assistant_message_id','knowledge_document_id','rank','similarity','title','source','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.coaching_retrievals'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.coaching_retrievals',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."coaching_retrievals" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.coaching_sessions'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','title','created_at','updated_at','last_message_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.coaching_sessions'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.coaching_sessions',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."coaching_sessions" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.data_exports'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','format','status','file_name','file_size_bytes','date_from','date_to','completed_at','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.data_exports'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.data_exports',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."data_exports" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.export_contents'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['export_id','content_type']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.export_contents'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.export_contents',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."export_contents" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.knowledge_documents'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','title','content','source','embedding','created_at','page_number','chunk_index','content_hash','revision_id','is_published']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.knowledge_documents'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.knowledge_documents',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."knowledge_documents" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.knowledge_revisions'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','source_id','title','content','source_urls','checked_at','file_path','status','created_by','created_at','lease_token','lease_until','attempts','chunk_count','error_message']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.knowledge_revisions'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.knowledge_revisions',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."knowledge_revisions" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.knowledge_sources'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','source_key','title','archived','published_revision_id','latest_revision_id','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.knowledge_sources'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.knowledge_sources',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."knowledge_sources" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.monthly_budgets'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','month','limit_amount','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.monthly_budgets'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.monthly_budgets',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."monthly_budgets" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.notification_preferences'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['user_id','budget_enabled','savings_enabled','savings_lead_days','savings_reminder_time','savings_milestones_enabled','spending_enabled','spending_frequency','spending_weekday','spending_reminder_time','bills_enabled','default_bill_lead_days','default_bill_reminder_time','timezone','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.notification_preferences'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.notification_preferences',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."notification_preferences" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.profiles'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','email','full_name','avatar_url','onboarding_completed','spending_records_consent','university','student_id','monthly_income','monthly_budget','spending_categories','created_at','updated_at','monthly_allowance','year_of_study','income_source','financial_status','coaching_style','auto_backup_enabled']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.profiles'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.profiles',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."profiles" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.reminders'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','type','title','amount','due_at','lead_days','recurrence','recurrence_anchor_day','enabled','next_trigger_at','last_triggered_at','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.reminders'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.reminders',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."reminders" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.report_attempts'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['attempt_id','user_id','message_id','action_id','storage_path','period','report_type','start_date','end_date','category_id','category_name','arguments','status','report_id','lease_expires_at','lease_owner','lease_renewed_at','lease_renewal_count','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.report_attempts'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.report_attempts',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."report_attempts" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.reports'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','period','type','generated_at','title','file_name','storage_path','report_key','start_date','end_date','category_id']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.reports'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.reports',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."reports" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.savings_contributions'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','goal_id','amount','contributed_on','note','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.savings_contributions'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.savings_contributions',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."savings_contributions" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.savings_goals'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','name','target_amount','current_amount','created_at','updated_at','deadline']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.savings_goals'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.savings_goals',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."savings_goals" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.transactions'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','category_id','amount','transaction_date','description','source','receipt_image_path','created_at','updated_at','receipt_items']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.transactions'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.transactions',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."transactions" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.user_categories'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['user_id','category_id','created_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.user_categories'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.user_categories',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."user_categories" t)s;

DO $$ BEGIN
      IF (SELECT array_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.user_devices'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM ARRAY['id','user_id','expo_push_token','platform','device_name','active','last_seen_at','last_error','created_at','updated_at']::name[]
      THEN RAISE EXCEPTION 'Source columns changed: public.user_devices'; END IF;
    END $$;

INSERT INTO trial_expected_rows SELECT 'public.user_devices',count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) FROM (SELECT to_jsonb(t) row FROM "public"."user_devices" t)s;

CREATE TEMP TABLE trial_sequence_state(name text,value bigint,called boolean) ON COMMIT DROP;

INSERT INTO trial_sequence_state SELECT 'public.admin_audit_logs_id_seq',last_value,is_called FROM public.admin_audit_logs_id_seq;

INSERT INTO trial_sequence_state SELECT 'public.budgets_id_seq',last_value,is_called FROM public.budgets_id_seq;

INSERT INTO trial_sequence_state SELECT 'public.categories_id_seq',last_value,is_called FROM public.categories_id_seq;

INSERT INTO trial_sequence_state SELECT 'public.coaching_retrievals_id_seq',last_value,is_called FROM public.coaching_retrievals_id_seq;

INSERT INTO trial_sequence_state SELECT 'public.knowledge_documents_id_seq',last_value,is_called FROM public.knowledge_documents_id_seq;

INSERT INTO trial_sequence_state SELECT 'public.reports_id_seq',last_value,is_called FROM public.reports_id_seq;

INSERT INTO trial_sequence_state SELECT 'public.savings_contributions_id_seq',last_value,is_called FROM public.savings_contributions_id_seq;

CREATE TABLE public."transaction_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r24_id" uuid,
  "r24_user_id" uuid,
  "r24_category_id" bigint,
  "r24_amount" numeric(12,2),
  "r24_transaction_date" date,
  "r24_description" text,
  "r24_source" text,
  "r24_receipt_image_path" text,
  "r24_created_at" timestamp with time zone,
  "r24_updated_at" timestamp with time zone,
  "r24_receipt_items" jsonb,
  "r08_id" bigint,
  "r08_name" text,
  "r08_type" text,
  "r08_icon" text,
  "r08_user_id" uuid,
  "r08_color" text,
  "r08_icon_image_path" text,
  "r25_user_id" uuid,
  "r25_category_id" bigint,
  "r25_created_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r24_id" IS NOT NULL THEN 'public.transactions' WHEN "r08_id" IS NOT NULL THEN 'public.categories' WHEN "r25_user_id" IS NOT NULL THEN 'public.user_categories' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.transactions' THEN ("r24_id" IS NOT NULL AND "r24_user_id" IS NOT NULL AND "r24_category_id" IS NOT NULL AND "r24_amount" IS NOT NULL AND "r24_transaction_date" IS NOT NULL AND "r24_source" IS NOT NULL AND "r24_created_at" IS NOT NULL AND "r24_updated_at" IS NOT NULL AND "r24_receipt_items" IS NOT NULL) ELSE ("r24_id" IS NULL AND "r24_user_id" IS NULL AND "r24_category_id" IS NULL AND "r24_amount" IS NULL AND "r24_transaction_date" IS NULL AND "r24_description" IS NULL AND "r24_source" IS NULL AND "r24_receipt_image_path" IS NULL AND "r24_created_at" IS NULL AND "r24_updated_at" IS NULL AND "r24_receipt_items" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.categories' THEN ("r08_id" IS NOT NULL AND "r08_name" IS NOT NULL AND "r08_type" IS NOT NULL) ELSE ("r08_id" IS NULL AND "r08_name" IS NULL AND "r08_type" IS NULL AND "r08_icon" IS NULL AND "r08_user_id" IS NULL AND "r08_color" IS NULL AND "r08_icon_image_path" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.user_categories' THEN ("r25_user_id" IS NOT NULL AND "r25_category_id" IS NOT NULL AND "r25_created_at" IS NOT NULL) ELSE ("r25_user_id" IS NULL AND "r25_category_id" IS NULL AND "r25_created_at" IS NULL) END)
);

ALTER TABLE public."transaction_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."transaction_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."transaction_records" TO service_role;

INSERT INTO public."transaction_records" ("r24_id", "r24_user_id", "r24_category_id", "r24_amount", "r24_transaction_date", "r24_description", "r24_source", "r24_receipt_image_path", "r24_created_at", "r24_updated_at", "r24_receipt_items") SELECT "id", "user_id", "category_id", "amount", "transaction_date", "description", "source", "receipt_image_path", "created_at", "updated_at", "receipt_items" FROM "public"."transactions";

INSERT INTO public."transaction_records" ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") SELECT "id", "name", "type", "icon", "user_id", "color", "icon_image_path" FROM "public"."categories";

INSERT INTO public."transaction_records" ("r25_user_id", "r25_category_id", "r25_created_at") SELECT "user_id", "category_id", "created_at" FROM "public"."user_categories";

CREATE TABLE public."budget_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r17_id" uuid,
  "r17_user_id" uuid,
  "r17_month" date,
  "r17_limit_amount" numeric(12,2),
  "r17_created_at" timestamp with time zone,
  "r17_updated_at" timestamp with time zone,
  "r07_id" bigint,
  "r07_user_id" uuid,
  "r07_category_id" bigint,
  "r07_amount" numeric(12,2),
  "r07_month" date,
  "r07_created_at" timestamp with time zone,
  "r07_updated_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r17_id" IS NOT NULL THEN 'public.monthly_budgets' WHEN "r07_id" IS NOT NULL THEN 'public.budgets' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.monthly_budgets' THEN ("r17_id" IS NOT NULL AND "r17_user_id" IS NOT NULL AND "r17_month" IS NOT NULL AND "r17_limit_amount" IS NOT NULL AND "r17_created_at" IS NOT NULL AND "r17_updated_at" IS NOT NULL) ELSE ("r17_id" IS NULL AND "r17_user_id" IS NULL AND "r17_month" IS NULL AND "r17_limit_amount" IS NULL AND "r17_created_at" IS NULL AND "r17_updated_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.budgets' THEN ("r07_id" IS NOT NULL AND "r07_user_id" IS NOT NULL AND "r07_category_id" IS NOT NULL AND "r07_amount" IS NOT NULL AND "r07_month" IS NOT NULL AND "r07_created_at" IS NOT NULL AND "r07_updated_at" IS NOT NULL) ELSE ("r07_id" IS NULL AND "r07_user_id" IS NULL AND "r07_category_id" IS NULL AND "r07_amount" IS NULL AND "r07_month" IS NULL AND "r07_created_at" IS NULL AND "r07_updated_at" IS NULL) END)
);

ALTER TABLE public."budget_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."budget_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."budget_records" TO service_role;

INSERT INTO public."budget_records" ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") SELECT "id", "user_id", "month", "limit_amount", "created_at", "updated_at" FROM "public"."monthly_budgets";

INSERT INTO public."budget_records" ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") SELECT "id", "user_id", "category_id", "amount", "month", "created_at", "updated_at" FROM "public"."budgets";

CREATE TABLE public."savings_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r23_id" uuid,
  "r23_user_id" uuid,
  "r23_name" text,
  "r23_target_amount" numeric(12,2),
  "r23_current_amount" numeric(12,2),
  "r23_created_at" timestamp with time zone,
  "r23_updated_at" timestamp with time zone,
  "r23_deadline" date,
  "r22_id" bigint,
  "r22_goal_id" uuid,
  "r22_amount" numeric(12,2),
  "r22_contributed_on" date,
  "r22_note" text,
  "r22_created_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r23_id" IS NOT NULL THEN 'public.savings_goals' WHEN "r22_id" IS NOT NULL THEN 'public.savings_contributions' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  _owner_id uuid,
  CHECK (CASE WHEN _record_kind='public.savings_goals' THEN ("r23_id" IS NOT NULL AND "r23_user_id" IS NOT NULL AND "r23_name" IS NOT NULL AND "r23_target_amount" IS NOT NULL AND "r23_current_amount" IS NOT NULL AND "r23_created_at" IS NOT NULL AND "r23_updated_at" IS NOT NULL) ELSE ("r23_id" IS NULL AND "r23_user_id" IS NULL AND "r23_name" IS NULL AND "r23_target_amount" IS NULL AND "r23_current_amount" IS NULL AND "r23_created_at" IS NULL AND "r23_updated_at" IS NULL AND "r23_deadline" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.savings_contributions' THEN ("r22_id" IS NOT NULL AND "r22_goal_id" IS NOT NULL AND "r22_amount" IS NOT NULL AND "r22_contributed_on" IS NOT NULL AND "r22_created_at" IS NOT NULL) ELSE ("r22_id" IS NULL AND "r22_goal_id" IS NULL AND "r22_amount" IS NULL AND "r22_contributed_on" IS NULL AND "r22_note" IS NULL AND "r22_created_at" IS NULL) END)
);

ALTER TABLE public."savings_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."savings_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."savings_records" TO service_role;

INSERT INTO public."savings_records" ("r23_id", "r23_user_id", "r23_name", "r23_target_amount", "r23_current_amount", "r23_created_at", "r23_updated_at", "r23_deadline") SELECT "id", "user_id", "name", "target_amount", "current_amount", "created_at", "updated_at", "deadline" FROM "public"."savings_goals";

INSERT INTO public."savings_records" ("r22_id", "r22_goal_id", "r22_amount", "r22_contributed_on", "r22_note", "r22_created_at") SELECT "id", "goal_id", "amount", "contributed_on", "note", "created_at" FROM "public"."savings_contributions";

CREATE TABLE public."export_backup_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r12_id" uuid,
  "r12_user_id" uuid,
  "r12_format" text,
  "r12_status" text,
  "r12_file_name" text,
  "r12_file_size_bytes" bigint,
  "r12_date_from" date,
  "r12_date_to" date,
  "r12_completed_at" timestamp with time zone,
  "r12_created_at" timestamp with time zone,
  "r13_export_id" uuid,
  "r13_content_type" text,
  "r06_id" uuid,
  "r06_user_id" uuid,
  "r06_backup_type" text,
  "r06_status" text,
  "r06_file_name" text,
  "r06_storage_path" text,
  "r06_file_size_bytes" bigint,
  "r06_checksum_sha256" text,
  "r06_schema_version" integer,
  "r06_last_restore_status" text,
  "r06_last_restored_at" timestamp with time zone,
  "r06_completed_at" timestamp with time zone,
  "r06_created_at" timestamp with time zone,
  "r06_data_counts" jsonb,
  "r06_attachment_count" integer,
  "r06_cleanup_warning" text,
  "r02_backup_id" uuid,
  "r02_user_id" uuid,
  "r02_data" jsonb,
  "r02_document" jsonb,
  "r02_created_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r12_id" IS NOT NULL THEN 'public.data_exports' WHEN "r13_export_id" IS NOT NULL THEN 'public.export_contents' WHEN "r06_id" IS NOT NULL THEN 'public.backups' WHEN "r02_backup_id" IS NOT NULL THEN 'private.financial_backup_snapshots' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  _owner_id uuid,
  CHECK (CASE WHEN _record_kind='public.data_exports' THEN ("r12_id" IS NOT NULL AND "r12_user_id" IS NOT NULL AND "r12_format" IS NOT NULL AND "r12_status" IS NOT NULL AND "r12_file_name" IS NOT NULL AND "r12_date_from" IS NOT NULL AND "r12_date_to" IS NOT NULL AND "r12_created_at" IS NOT NULL) ELSE ("r12_id" IS NULL AND "r12_user_id" IS NULL AND "r12_format" IS NULL AND "r12_status" IS NULL AND "r12_file_name" IS NULL AND "r12_file_size_bytes" IS NULL AND "r12_date_from" IS NULL AND "r12_date_to" IS NULL AND "r12_completed_at" IS NULL AND "r12_created_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.export_contents' THEN ("r13_export_id" IS NOT NULL AND "r13_content_type" IS NOT NULL) ELSE ("r13_export_id" IS NULL AND "r13_content_type" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.backups' THEN ("r06_id" IS NOT NULL AND "r06_user_id" IS NOT NULL AND "r06_backup_type" IS NOT NULL AND "r06_status" IS NOT NULL AND "r06_file_name" IS NOT NULL AND "r06_schema_version" IS NOT NULL AND "r06_created_at" IS NOT NULL AND "r06_attachment_count" IS NOT NULL) ELSE ("r06_id" IS NULL AND "r06_user_id" IS NULL AND "r06_backup_type" IS NULL AND "r06_status" IS NULL AND "r06_file_name" IS NULL AND "r06_storage_path" IS NULL AND "r06_file_size_bytes" IS NULL AND "r06_checksum_sha256" IS NULL AND "r06_schema_version" IS NULL AND "r06_last_restore_status" IS NULL AND "r06_last_restored_at" IS NULL AND "r06_completed_at" IS NULL AND "r06_created_at" IS NULL AND "r06_data_counts" IS NULL AND "r06_attachment_count" IS NULL AND "r06_cleanup_warning" IS NULL) END),
  CHECK (CASE WHEN _record_kind='private.financial_backup_snapshots' THEN ("r02_backup_id" IS NOT NULL AND "r02_user_id" IS NOT NULL AND "r02_data" IS NOT NULL AND "r02_created_at" IS NOT NULL) ELSE ("r02_backup_id" IS NULL AND "r02_user_id" IS NULL AND "r02_data" IS NULL AND "r02_document" IS NULL AND "r02_created_at" IS NULL) END)
);

ALTER TABLE public."export_backup_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."export_backup_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."export_backup_records" TO service_role;

INSERT INTO public."export_backup_records" ("r12_id", "r12_user_id", "r12_format", "r12_status", "r12_file_name", "r12_file_size_bytes", "r12_date_from", "r12_date_to", "r12_completed_at", "r12_created_at") SELECT "id", "user_id", "format", "status", "file_name", "file_size_bytes", "date_from", "date_to", "completed_at", "created_at" FROM "public"."data_exports";

INSERT INTO public."export_backup_records" ("r13_export_id", "r13_content_type") SELECT "export_id", "content_type" FROM "public"."export_contents";

INSERT INTO public."export_backup_records" ("r06_id", "r06_user_id", "r06_backup_type", "r06_status", "r06_file_name", "r06_storage_path", "r06_file_size_bytes", "r06_checksum_sha256", "r06_schema_version", "r06_last_restore_status", "r06_last_restored_at", "r06_completed_at", "r06_created_at", "r06_data_counts", "r06_attachment_count", "r06_cleanup_warning") SELECT "id", "user_id", "backup_type", "status", "file_name", "storage_path", "file_size_bytes", "checksum_sha256", "schema_version", "last_restore_status", "last_restored_at", "completed_at", "created_at", "data_counts", "attachment_count", "cleanup_warning" FROM "public"."backups";

INSERT INTO public."export_backup_records" ("r02_backup_id", "r02_user_id", "r02_data", "r02_document", "r02_created_at") SELECT "backup_id", "user_id", "data", "document", "created_at" FROM "private"."financial_backup_snapshots";

CREATE TABLE public."coaching_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r11_id" uuid,
  "r11_user_id" uuid,
  "r11_title" text,
  "r11_created_at" timestamp with time zone,
  "r11_updated_at" timestamp with time zone,
  "r11_last_message_at" timestamp with time zone,
  "r09_id" uuid,
  "r09_session_id" uuid,
  "r09_user_id" uuid,
  "r09_role" text,
  "r09_content" text,
  "r09_reply_to_message_id" uuid,
  "r09_status" text,
  "r09_error_code" text,
  "r09_model" text,
  "r09_prompt_tokens" integer,
  "r09_completion_tokens" integer,
  "r09_created_at" timestamp with time zone,
  "r09_feedback" text,
  "r09_ui_payload" jsonb,
  "r10_id" bigint,
  "r10_user_id" uuid,
  "r10_assistant_message_id" uuid,
  "r10_knowledge_document_id" bigint,
  "r10_rank" smallint,
  "r10_similarity" double precision,
  "r10_title" text,
  "r10_source" text,
  "r10_created_at" timestamp with time zone,
  "r01_message_id" uuid,
  "r01_token" uuid,
  "r01_expires_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r11_id" IS NOT NULL THEN 'public.coaching_sessions' WHEN "r09_id" IS NOT NULL THEN 'public.coaching_messages' WHEN "r10_id" IS NOT NULL THEN 'public.coaching_retrievals' WHEN "r01_message_id" IS NOT NULL THEN 'private.coaching_processing_leases' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.coaching_sessions' THEN ("r11_id" IS NOT NULL AND "r11_user_id" IS NOT NULL AND "r11_title" IS NOT NULL AND "r11_created_at" IS NOT NULL AND "r11_updated_at" IS NOT NULL AND "r11_last_message_at" IS NOT NULL) ELSE ("r11_id" IS NULL AND "r11_user_id" IS NULL AND "r11_title" IS NULL AND "r11_created_at" IS NULL AND "r11_updated_at" IS NULL AND "r11_last_message_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.coaching_messages' THEN ("r09_id" IS NOT NULL AND "r09_session_id" IS NOT NULL AND "r09_user_id" IS NOT NULL AND "r09_role" IS NOT NULL AND "r09_content" IS NOT NULL AND "r09_status" IS NOT NULL AND "r09_created_at" IS NOT NULL AND "r09_ui_payload" IS NOT NULL) ELSE ("r09_id" IS NULL AND "r09_session_id" IS NULL AND "r09_user_id" IS NULL AND "r09_role" IS NULL AND "r09_content" IS NULL AND "r09_reply_to_message_id" IS NULL AND "r09_status" IS NULL AND "r09_error_code" IS NULL AND "r09_model" IS NULL AND "r09_prompt_tokens" IS NULL AND "r09_completion_tokens" IS NULL AND "r09_created_at" IS NULL AND "r09_feedback" IS NULL AND "r09_ui_payload" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.coaching_retrievals' THEN ("r10_id" IS NOT NULL AND "r10_user_id" IS NOT NULL AND "r10_assistant_message_id" IS NOT NULL AND "r10_rank" IS NOT NULL AND "r10_similarity" IS NOT NULL AND "r10_created_at" IS NOT NULL) ELSE ("r10_id" IS NULL AND "r10_user_id" IS NULL AND "r10_assistant_message_id" IS NULL AND "r10_knowledge_document_id" IS NULL AND "r10_rank" IS NULL AND "r10_similarity" IS NULL AND "r10_title" IS NULL AND "r10_source" IS NULL AND "r10_created_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='private.coaching_processing_leases' THEN ("r01_message_id" IS NOT NULL AND "r01_token" IS NOT NULL AND "r01_expires_at" IS NOT NULL) ELSE ("r01_message_id" IS NULL AND "r01_token" IS NULL AND "r01_expires_at" IS NULL) END)
);

ALTER TABLE public."coaching_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."coaching_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."coaching_records" TO service_role;

INSERT INTO public."coaching_records" ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") SELECT "id", "user_id", "title", "created_at", "updated_at", "last_message_at" FROM "public"."coaching_sessions";

INSERT INTO public."coaching_records" ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") SELECT "id", "session_id", "user_id", "role", "content", "reply_to_message_id", "status", "error_code", "model", "prompt_tokens", "completion_tokens", "created_at", "feedback", "ui_payload" FROM "public"."coaching_messages";

INSERT INTO public."coaching_records" ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") SELECT "id", "user_id", "assistant_message_id", "knowledge_document_id", "rank", "similarity", "title", "source", "created_at" FROM "public"."coaching_retrievals";

INSERT INTO public."coaching_records" ("r01_message_id", "r01_token", "r01_expires_at") SELECT "message_id", "token", "expires_at" FROM "private"."coaching_processing_leases";

CREATE TABLE public."report_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r21_id" bigint,
  "r21_user_id" uuid,
  "r21_period" text,
  "r21_type" text,
  "r21_generated_at" timestamp with time zone,
  "r21_title" text,
  "r21_file_name" text,
  "r21_storage_path" text,
  "r21_report_key" text,
  "r21_start_date" date,
  "r21_end_date" date,
  "r21_category_id" bigint,
  "r20_attempt_id" uuid,
  "r20_user_id" uuid,
  "r20_message_id" uuid,
  "r20_action_id" uuid,
  "r20_storage_path" text,
  "r20_period" text,
  "r20_report_type" text,
  "r20_start_date" date,
  "r20_end_date" date,
  "r20_category_id" bigint,
  "r20_category_name" text,
  "r20_arguments" jsonb,
  "r20_status" text,
  "r20_report_id" bigint,
  "r20_lease_expires_at" timestamp with time zone,
  "r20_lease_owner" uuid,
  "r20_lease_renewed_at" timestamp with time zone,
  "r20_lease_renewal_count" integer,
  "r20_created_at" timestamp with time zone,
  "r20_updated_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r21_id" IS NOT NULL THEN 'public.reports' WHEN "r20_attempt_id" IS NOT NULL THEN 'public.report_attempts' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.reports' THEN ("r21_id" IS NOT NULL AND "r21_user_id" IS NOT NULL AND "r21_period" IS NOT NULL AND "r21_type" IS NOT NULL AND "r21_generated_at" IS NOT NULL) ELSE ("r21_id" IS NULL AND "r21_user_id" IS NULL AND "r21_period" IS NULL AND "r21_type" IS NULL AND "r21_generated_at" IS NULL AND "r21_title" IS NULL AND "r21_file_name" IS NULL AND "r21_storage_path" IS NULL AND "r21_report_key" IS NULL AND "r21_start_date" IS NULL AND "r21_end_date" IS NULL AND "r21_category_id" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.report_attempts' THEN ("r20_attempt_id" IS NOT NULL AND "r20_user_id" IS NOT NULL AND "r20_message_id" IS NOT NULL AND "r20_action_id" IS NOT NULL AND "r20_storage_path" IS NOT NULL AND "r20_period" IS NOT NULL AND "r20_report_type" IS NOT NULL AND "r20_start_date" IS NOT NULL AND "r20_end_date" IS NOT NULL AND "r20_arguments" IS NOT NULL AND "r20_status" IS NOT NULL AND "r20_lease_expires_at" IS NOT NULL AND "r20_lease_renewal_count" IS NOT NULL AND "r20_created_at" IS NOT NULL AND "r20_updated_at" IS NOT NULL) ELSE ("r20_attempt_id" IS NULL AND "r20_user_id" IS NULL AND "r20_message_id" IS NULL AND "r20_action_id" IS NULL AND "r20_storage_path" IS NULL AND "r20_period" IS NULL AND "r20_report_type" IS NULL AND "r20_start_date" IS NULL AND "r20_end_date" IS NULL AND "r20_category_id" IS NULL AND "r20_category_name" IS NULL AND "r20_arguments" IS NULL AND "r20_status" IS NULL AND "r20_report_id" IS NULL AND "r20_lease_expires_at" IS NULL AND "r20_lease_owner" IS NULL AND "r20_lease_renewed_at" IS NULL AND "r20_lease_renewal_count" IS NULL AND "r20_created_at" IS NULL AND "r20_updated_at" IS NULL) END)
);

ALTER TABLE public."report_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."report_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."report_records" TO service_role;

INSERT INTO public."report_records" ("r21_id", "r21_user_id", "r21_period", "r21_type", "r21_generated_at", "r21_title", "r21_file_name", "r21_storage_path", "r21_report_key", "r21_start_date", "r21_end_date", "r21_category_id") SELECT "id", "user_id", "period", "type", "generated_at", "title", "file_name", "storage_path", "report_key", "start_date", "end_date", "category_id" FROM "public"."reports";

INSERT INTO public."report_records" ("r20_attempt_id", "r20_user_id", "r20_message_id", "r20_action_id", "r20_storage_path", "r20_period", "r20_report_type", "r20_start_date", "r20_end_date", "r20_category_id", "r20_category_name", "r20_arguments", "r20_status", "r20_report_id", "r20_lease_expires_at", "r20_lease_owner", "r20_lease_renewed_at", "r20_lease_renewal_count", "r20_created_at", "r20_updated_at") SELECT "attempt_id", "user_id", "message_id", "action_id", "storage_path", "period", "report_type", "start_date", "end_date", "category_id", "category_name", "arguments", "status", "report_id", "lease_expires_at", "lease_owner", "lease_renewed_at", "lease_renewal_count", "created_at", "updated_at" FROM "public"."report_attempts";

CREATE TABLE public."alert_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r05_id" uuid,
  "r05_user_id" uuid,
  "r05_type" text,
  "r05_kind" text,
  "r05_title" text,
  "r05_message" text,
  "r05_budget_id" uuid,
  "r05_category_limit_id" bigint,
  "r05_savings_goal_id" uuid,
  "r05_reminder_id" uuid,
  "r05_source_data" jsonb,
  "r05_dedupe_key" text,
  "r05_scheduled_for" timestamp with time zone,
  "r05_delivered_at" timestamp with time zone,
  "r05_read_at" timestamp with time zone,
  "r05_dismissed_at" timestamp with time zone,
  "r05_delivery_status" text,
  "r05_delivery_error" text,
  "r05_delivery_attempt_count" smallint,
  "r05_delivery_claimed_at" timestamp with time zone,
  "r05_next_delivery_attempt_at" timestamp with time zone,
  "r05_delivery_receipts" jsonb,
  "r05_created_at" timestamp with time zone,
  "r19_id" uuid,
  "r19_user_id" uuid,
  "r19_type" text,
  "r19_title" text,
  "r19_amount" numeric(12,2),
  "r19_due_at" timestamp with time zone,
  "r19_lead_days" smallint,
  "r19_recurrence" text,
  "r19_recurrence_anchor_day" smallint,
  "r19_enabled" boolean,
  "r19_next_trigger_at" timestamp with time zone,
  "r19_last_triggered_at" timestamp with time zone,
  "r19_created_at" timestamp with time zone,
  "r19_updated_at" timestamp with time zone,
  "r18_user_id" uuid,
  "r18_budget_enabled" boolean,
  "r18_savings_enabled" boolean,
  "r18_savings_lead_days" smallint,
  "r18_savings_reminder_time" time without time zone,
  "r18_savings_milestones_enabled" boolean,
  "r18_spending_enabled" boolean,
  "r18_spending_frequency" text,
  "r18_spending_weekday" smallint,
  "r18_spending_reminder_time" time without time zone,
  "r18_bills_enabled" boolean,
  "r18_default_bill_lead_days" smallint,
  "r18_default_bill_reminder_time" time without time zone,
  "r18_timezone" text,
  "r18_created_at" timestamp with time zone,
  "r18_updated_at" timestamp with time zone,
  "r26_id" uuid,
  "r26_user_id" uuid,
  "r26_expo_push_token" text,
  "r26_platform" text,
  "r26_device_name" text,
  "r26_active" boolean,
  "r26_last_seen_at" timestamp with time zone,
  "r26_last_error" text,
  "r26_created_at" timestamp with time zone,
  "r26_updated_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r05_id" IS NOT NULL THEN 'public.alerts' WHEN "r19_id" IS NOT NULL THEN 'public.reminders' WHEN "r18_user_id" IS NOT NULL THEN 'public.notification_preferences' WHEN "r26_id" IS NOT NULL THEN 'public.user_devices' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.alerts' THEN ("r05_id" IS NOT NULL AND "r05_user_id" IS NOT NULL AND "r05_type" IS NOT NULL AND "r05_kind" IS NOT NULL AND "r05_title" IS NOT NULL AND "r05_message" IS NOT NULL AND "r05_source_data" IS NOT NULL AND "r05_dedupe_key" IS NOT NULL AND "r05_delivery_status" IS NOT NULL AND "r05_delivery_attempt_count" IS NOT NULL AND "r05_delivery_receipts" IS NOT NULL AND "r05_created_at" IS NOT NULL) ELSE ("r05_id" IS NULL AND "r05_user_id" IS NULL AND "r05_type" IS NULL AND "r05_kind" IS NULL AND "r05_title" IS NULL AND "r05_message" IS NULL AND "r05_budget_id" IS NULL AND "r05_category_limit_id" IS NULL AND "r05_savings_goal_id" IS NULL AND "r05_reminder_id" IS NULL AND "r05_source_data" IS NULL AND "r05_dedupe_key" IS NULL AND "r05_scheduled_for" IS NULL AND "r05_delivered_at" IS NULL AND "r05_read_at" IS NULL AND "r05_dismissed_at" IS NULL AND "r05_delivery_status" IS NULL AND "r05_delivery_error" IS NULL AND "r05_delivery_attempt_count" IS NULL AND "r05_delivery_claimed_at" IS NULL AND "r05_next_delivery_attempt_at" IS NULL AND "r05_delivery_receipts" IS NULL AND "r05_created_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.reminders' THEN ("r19_id" IS NOT NULL AND "r19_user_id" IS NOT NULL AND "r19_type" IS NOT NULL AND "r19_title" IS NOT NULL AND "r19_due_at" IS NOT NULL AND "r19_lead_days" IS NOT NULL AND "r19_recurrence" IS NOT NULL AND "r19_recurrence_anchor_day" IS NOT NULL AND "r19_enabled" IS NOT NULL AND "r19_created_at" IS NOT NULL AND "r19_updated_at" IS NOT NULL) ELSE ("r19_id" IS NULL AND "r19_user_id" IS NULL AND "r19_type" IS NULL AND "r19_title" IS NULL AND "r19_amount" IS NULL AND "r19_due_at" IS NULL AND "r19_lead_days" IS NULL AND "r19_recurrence" IS NULL AND "r19_recurrence_anchor_day" IS NULL AND "r19_enabled" IS NULL AND "r19_next_trigger_at" IS NULL AND "r19_last_triggered_at" IS NULL AND "r19_created_at" IS NULL AND "r19_updated_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.notification_preferences' THEN ("r18_user_id" IS NOT NULL AND "r18_budget_enabled" IS NOT NULL AND "r18_savings_enabled" IS NOT NULL AND "r18_savings_lead_days" IS NOT NULL AND "r18_savings_reminder_time" IS NOT NULL AND "r18_savings_milestones_enabled" IS NOT NULL AND "r18_spending_enabled" IS NOT NULL AND "r18_spending_frequency" IS NOT NULL AND "r18_spending_reminder_time" IS NOT NULL AND "r18_bills_enabled" IS NOT NULL AND "r18_default_bill_lead_days" IS NOT NULL AND "r18_default_bill_reminder_time" IS NOT NULL AND "r18_timezone" IS NOT NULL AND "r18_created_at" IS NOT NULL AND "r18_updated_at" IS NOT NULL) ELSE ("r18_user_id" IS NULL AND "r18_budget_enabled" IS NULL AND "r18_savings_enabled" IS NULL AND "r18_savings_lead_days" IS NULL AND "r18_savings_reminder_time" IS NULL AND "r18_savings_milestones_enabled" IS NULL AND "r18_spending_enabled" IS NULL AND "r18_spending_frequency" IS NULL AND "r18_spending_weekday" IS NULL AND "r18_spending_reminder_time" IS NULL AND "r18_bills_enabled" IS NULL AND "r18_default_bill_lead_days" IS NULL AND "r18_default_bill_reminder_time" IS NULL AND "r18_timezone" IS NULL AND "r18_created_at" IS NULL AND "r18_updated_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.user_devices' THEN ("r26_id" IS NOT NULL AND "r26_user_id" IS NOT NULL AND "r26_expo_push_token" IS NOT NULL AND "r26_platform" IS NOT NULL AND "r26_active" IS NOT NULL AND "r26_last_seen_at" IS NOT NULL AND "r26_created_at" IS NOT NULL AND "r26_updated_at" IS NOT NULL) ELSE ("r26_id" IS NULL AND "r26_user_id" IS NULL AND "r26_expo_push_token" IS NULL AND "r26_platform" IS NULL AND "r26_device_name" IS NULL AND "r26_active" IS NULL AND "r26_last_seen_at" IS NULL AND "r26_last_error" IS NULL AND "r26_created_at" IS NULL AND "r26_updated_at" IS NULL) END)
);

ALTER TABLE public."alert_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."alert_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."alert_records" TO service_role;

INSERT INTO public."alert_records" ("r05_id", "r05_user_id", "r05_type", "r05_kind", "r05_title", "r05_message", "r05_budget_id", "r05_category_limit_id", "r05_savings_goal_id", "r05_reminder_id", "r05_source_data", "r05_dedupe_key", "r05_scheduled_for", "r05_delivered_at", "r05_read_at", "r05_dismissed_at", "r05_delivery_status", "r05_delivery_error", "r05_delivery_attempt_count", "r05_delivery_claimed_at", "r05_next_delivery_attempt_at", "r05_delivery_receipts", "r05_created_at") SELECT "id", "user_id", "type", "kind", "title", "message", "budget_id", "category_limit_id", "savings_goal_id", "reminder_id", "source_data", "dedupe_key", "scheduled_for", "delivered_at", "read_at", "dismissed_at", "delivery_status", "delivery_error", "delivery_attempt_count", "delivery_claimed_at", "next_delivery_attempt_at", "delivery_receipts", "created_at" FROM "public"."alerts";

INSERT INTO public."alert_records" ("r19_id", "r19_user_id", "r19_type", "r19_title", "r19_amount", "r19_due_at", "r19_lead_days", "r19_recurrence", "r19_recurrence_anchor_day", "r19_enabled", "r19_next_trigger_at", "r19_last_triggered_at", "r19_created_at", "r19_updated_at") SELECT "id", "user_id", "type", "title", "amount", "due_at", "lead_days", "recurrence", "recurrence_anchor_day", "enabled", "next_trigger_at", "last_triggered_at", "created_at", "updated_at" FROM "public"."reminders";

INSERT INTO public."alert_records" ("r18_user_id", "r18_budget_enabled", "r18_savings_enabled", "r18_savings_lead_days", "r18_savings_reminder_time", "r18_savings_milestones_enabled", "r18_spending_enabled", "r18_spending_frequency", "r18_spending_weekday", "r18_spending_reminder_time", "r18_bills_enabled", "r18_default_bill_lead_days", "r18_default_bill_reminder_time", "r18_timezone", "r18_created_at", "r18_updated_at") SELECT "user_id", "budget_enabled", "savings_enabled", "savings_lead_days", "savings_reminder_time", "savings_milestones_enabled", "spending_enabled", "spending_frequency", "spending_weekday", "spending_reminder_time", "bills_enabled", "default_bill_lead_days", "default_bill_reminder_time", "timezone", "created_at", "updated_at" FROM "public"."notification_preferences";

INSERT INTO public."alert_records" ("r26_id", "r26_user_id", "r26_expo_push_token", "r26_platform", "r26_device_name", "r26_active", "r26_last_seen_at", "r26_last_error", "r26_created_at", "r26_updated_at") SELECT "id", "user_id", "expo_push_token", "platform", "device_name", "active", "last_seen_at", "last_error", "created_at", "updated_at" FROM "public"."user_devices";

CREATE TABLE public."knowledge_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r16_id" uuid,
  "r16_source_key" text,
  "r16_title" text,
  "r16_archived" boolean,
  "r16_published_revision_id" uuid,
  "r16_latest_revision_id" uuid,
  "r16_created_at" timestamp with time zone,
  "r16_updated_at" timestamp with time zone,
  "r15_id" uuid,
  "r15_source_id" uuid,
  "r15_title" text,
  "r15_content" text,
  "r15_source_urls" jsonb,
  "r15_checked_at" date,
  "r15_file_path" text,
  "r15_status" text,
  "r15_created_by" uuid,
  "r15_created_at" timestamp with time zone,
  "r15_lease_token" uuid,
  "r15_lease_until" timestamp with time zone,
  "r15_attempts" integer,
  "r15_chunk_count" integer,
  "r15_error_message" text,
  "r14_id" bigint,
  "r14_title" text,
  "r14_content" text,
  "r14_source" text,
  "r14_embedding" public.vector(1024),
  "r14_created_at" timestamp with time zone,
  "r14_page_number" integer,
  "r14_chunk_index" integer,
  "r14_content_hash" text,
  "r14_revision_id" uuid,
  "r14_is_published" boolean,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r16_id" IS NOT NULL THEN 'public.knowledge_sources' WHEN "r15_id" IS NOT NULL THEN 'public.knowledge_revisions' WHEN "r14_id" IS NOT NULL THEN 'public.knowledge_documents' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.knowledge_sources' THEN ("r16_id" IS NOT NULL AND "r16_source_key" IS NOT NULL AND "r16_title" IS NOT NULL AND "r16_archived" IS NOT NULL AND "r16_created_at" IS NOT NULL AND "r16_updated_at" IS NOT NULL) ELSE ("r16_id" IS NULL AND "r16_source_key" IS NULL AND "r16_title" IS NULL AND "r16_archived" IS NULL AND "r16_published_revision_id" IS NULL AND "r16_latest_revision_id" IS NULL AND "r16_created_at" IS NULL AND "r16_updated_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.knowledge_revisions' THEN ("r15_id" IS NOT NULL AND "r15_source_id" IS NOT NULL AND "r15_title" IS NOT NULL AND "r15_content" IS NOT NULL AND "r15_source_urls" IS NOT NULL AND "r15_status" IS NOT NULL AND "r15_created_at" IS NOT NULL AND "r15_attempts" IS NOT NULL AND "r15_chunk_count" IS NOT NULL) ELSE ("r15_id" IS NULL AND "r15_source_id" IS NULL AND "r15_title" IS NULL AND "r15_content" IS NULL AND "r15_source_urls" IS NULL AND "r15_checked_at" IS NULL AND "r15_file_path" IS NULL AND "r15_status" IS NULL AND "r15_created_by" IS NULL AND "r15_created_at" IS NULL AND "r15_lease_token" IS NULL AND "r15_lease_until" IS NULL AND "r15_attempts" IS NULL AND "r15_chunk_count" IS NULL AND "r15_error_message" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.knowledge_documents' THEN ("r14_id" IS NOT NULL AND "r14_content" IS NOT NULL AND "r14_embedding" IS NOT NULL AND "r14_created_at" IS NOT NULL AND "r14_revision_id" IS NOT NULL AND "r14_is_published" IS NOT NULL) ELSE ("r14_id" IS NULL AND "r14_title" IS NULL AND "r14_content" IS NULL AND "r14_source" IS NULL AND "r14_embedding" IS NULL AND "r14_created_at" IS NULL AND "r14_page_number" IS NULL AND "r14_chunk_index" IS NULL AND "r14_content_hash" IS NULL AND "r14_revision_id" IS NULL AND "r14_is_published" IS NULL) END)
);

ALTER TABLE public."knowledge_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."knowledge_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."knowledge_records" TO service_role;

INSERT INTO public."knowledge_records" ("r16_id", "r16_source_key", "r16_title", "r16_archived", "r16_published_revision_id", "r16_latest_revision_id", "r16_created_at", "r16_updated_at") SELECT "id", "source_key", "title", "archived", "published_revision_id", "latest_revision_id", "created_at", "updated_at" FROM "public"."knowledge_sources";

INSERT INTO public."knowledge_records" ("r15_id", "r15_source_id", "r15_title", "r15_content", "r15_source_urls", "r15_checked_at", "r15_file_path", "r15_status", "r15_created_by", "r15_created_at", "r15_lease_token", "r15_lease_until", "r15_attempts", "r15_chunk_count", "r15_error_message") SELECT "id", "source_id", "title", "content", "source_urls", "checked_at", "file_path", "status", "created_by", "created_at", "lease_token", "lease_until", "attempts", "chunk_count", "error_message" FROM "public"."knowledge_revisions";

INSERT INTO public."knowledge_records" ("r14_id", "r14_title", "r14_content", "r14_source", "r14_embedding", "r14_created_at", "r14_page_number", "r14_chunk_index", "r14_content_hash", "r14_revision_id", "r14_is_published") SELECT "id", "title", "content", "source", "embedding", "created_at", "page_number", "chunk_index", "content_hash", "revision_id", "is_published" FROM "public"."knowledge_documents";

CREATE TABLE public."account_records" (
  _row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "r03_user_id" uuid,
  "r03_role" text,
  "r03_status" text,
  "r03_email" text,
  "r03_display_name" text,
  "r03_created_at" timestamp with time zone,
  "r03_last_sign_in_at" timestamp with time zone,
  "r03_updated_at" timestamp with time zone,
  "r04_id" bigint,
  "r04_actor_id" uuid,
  "r04_action" text,
  "r04_target_type" text,
  "r04_target_id" text,
  "r04_details" jsonb,
  "r04_created_at" timestamp with time zone,
  _record_kind text GENERATED ALWAYS AS (CASE WHEN "r03_user_id" IS NOT NULL THEN 'public.account_access' WHEN "r04_id" IS NOT NULL THEN 'public.admin_audit_logs' END) STORED,
  CHECK (_record_kind IS NOT NULL),
  CHECK (CASE WHEN _record_kind='public.account_access' THEN ("r03_user_id" IS NOT NULL AND "r03_role" IS NOT NULL AND "r03_status" IS NOT NULL AND "r03_created_at" IS NOT NULL AND "r03_updated_at" IS NOT NULL) ELSE ("r03_user_id" IS NULL AND "r03_role" IS NULL AND "r03_status" IS NULL AND "r03_email" IS NULL AND "r03_display_name" IS NULL AND "r03_created_at" IS NULL AND "r03_last_sign_in_at" IS NULL AND "r03_updated_at" IS NULL) END),
  CHECK (CASE WHEN _record_kind='public.admin_audit_logs' THEN ("r04_id" IS NOT NULL AND "r04_action" IS NOT NULL AND "r04_target_type" IS NOT NULL AND "r04_target_id" IS NOT NULL AND "r04_details" IS NOT NULL AND "r04_created_at" IS NOT NULL) ELSE ("r04_id" IS NULL AND "r04_actor_id" IS NULL AND "r04_action" IS NULL AND "r04_target_type" IS NULL AND "r04_target_id" IS NULL AND "r04_details" IS NULL AND "r04_created_at" IS NULL) END)
);

ALTER TABLE public."account_records" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public."account_records" FROM PUBLIC,anon,authenticated;

GRANT ALL ON public."account_records" TO service_role;

INSERT INTO public."account_records" ("r03_user_id", "r03_role", "r03_status", "r03_email", "r03_display_name", "r03_created_at", "r03_last_sign_in_at", "r03_updated_at") SELECT "user_id", "role", "status", "email", "display_name", "created_at", "last_sign_in_at", "updated_at" FROM "public"."account_access";

INSERT INTO public."account_records" ("r04_id", "r04_actor_id", "r04_action", "r04_target_type", "r04_target_id", "r04_details", "r04_created_at") SELECT "id", "actor_id", "action", "target_type", "target_id", "details", "created_at" FROM "public"."admin_audit_logs";

DROP TABLE "private"."coaching_processing_leases", "private"."financial_backup_snapshots", "public"."account_access", "public"."admin_audit_logs", "public"."alerts", "public"."backups", "public"."budgets", "public"."categories", "public"."coaching_messages", "public"."coaching_retrievals", "public"."coaching_sessions", "public"."data_exports", "public"."export_contents", "public"."knowledge_documents", "public"."knowledge_revisions", "public"."knowledge_sources", "public"."monthly_budgets", "public"."notification_preferences", "public"."reminders", "public"."report_attempts", "public"."reports", "public"."savings_contributions", "public"."savings_goals", "public"."transactions", "public"."user_categories", "public"."user_devices" CASCADE;

CREATE VIEW "private"."coaching_processing_leases" WITH (security_invoker=true,security_barrier=true) AS SELECT "r01_message_id" AS "message_id", "r01_token" AS "token", "r01_expires_at" AS "expires_at" FROM "public"."coaching_records" WHERE "r01_message_id" IS NOT NULL WITH CASCADED CHECK OPTION;

CREATE VIEW "private"."financial_backup_snapshots" WITH (security_invoker=true,security_barrier=true) AS SELECT "r02_backup_id" AS "backup_id", "r02_user_id" AS "user_id", "r02_data" AS "data", "r02_document" AS "document", "r02_created_at" AS "created_at" FROM "public"."export_backup_records" WHERE "r02_backup_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "private"."financial_backup_snapshots" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."account_access" WITH (security_invoker=true,security_barrier=true) AS SELECT "r03_user_id" AS "user_id", "r03_role" AS "role", "r03_status" AS "status", "r03_email" AS "email", "r03_display_name" AS "display_name", "r03_created_at" AS "created_at", "r03_last_sign_in_at" AS "last_sign_in_at", "r03_updated_at" AS "updated_at" FROM "public"."account_records" WHERE "r03_user_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."account_access" ALTER COLUMN "role" SET DEFAULT 'student'::text;

ALTER VIEW "public"."account_access" ALTER COLUMN "status" SET DEFAULT 'active'::text;

ALTER VIEW "public"."account_access" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."account_access" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE SEQUENCE public.admin_audit_logs_id_seq;

SELECT setval('public.admin_audit_logs_id_seq',value,called) FROM trial_sequence_state WHERE name='public.admin_audit_logs_id_seq';

ALTER SEQUENCE public.admin_audit_logs_id_seq OWNED BY "public"."account_records"."r04_id";

CREATE VIEW "public"."admin_audit_logs" WITH (security_invoker=true,security_barrier=true) AS SELECT "r04_id" AS "id", "r04_actor_id" AS "actor_id", "r04_action" AS "action", "r04_target_type" AS "target_type", "r04_target_id" AS "target_id", "r04_details" AS "details", "r04_created_at" AS "created_at" FROM "public"."account_records" WHERE "r04_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."admin_audit_logs" ALTER COLUMN "id" SET DEFAULT nextval('public.admin_audit_logs_id_seq'::regclass);

ALTER VIEW "public"."admin_audit_logs" ALTER COLUMN "details" SET DEFAULT '{}'::jsonb;

ALTER VIEW "public"."admin_audit_logs" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."alerts" WITH (security_invoker=true,security_barrier=true) AS SELECT "r05_id" AS "id", "r05_user_id" AS "user_id", "r05_type" AS "type", "r05_kind" AS "kind", "r05_title" AS "title", "r05_message" AS "message", "r05_budget_id" AS "budget_id", "r05_category_limit_id" AS "category_limit_id", "r05_savings_goal_id" AS "savings_goal_id", "r05_reminder_id" AS "reminder_id", "r05_source_data" AS "source_data", "r05_dedupe_key" AS "dedupe_key", "r05_scheduled_for" AS "scheduled_for", "r05_delivered_at" AS "delivered_at", "r05_read_at" AS "read_at", "r05_dismissed_at" AS "dismissed_at", "r05_delivery_status" AS "delivery_status", "r05_delivery_error" AS "delivery_error", "r05_delivery_attempt_count" AS "delivery_attempt_count", "r05_delivery_claimed_at" AS "delivery_claimed_at", "r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "r05_delivery_receipts" AS "delivery_receipts", "r05_created_at" AS "created_at" FROM "public"."alert_records" WHERE "r05_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."alerts" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."alerts" ALTER COLUMN "kind" SET DEFAULT 'alert'::text;

ALTER VIEW "public"."alerts" ALTER COLUMN "source_data" SET DEFAULT '{}'::jsonb;

ALTER VIEW "public"."alerts" ALTER COLUMN "delivery_status" SET DEFAULT 'pending'::text;

ALTER VIEW "public"."alerts" ALTER COLUMN "delivery_attempt_count" SET DEFAULT 0;

ALTER VIEW "public"."alerts" ALTER COLUMN "delivery_receipts" SET DEFAULT '{}'::jsonb;

ALTER VIEW "public"."alerts" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."backups" WITH (security_invoker=true,security_barrier=true) AS SELECT "r06_id" AS "id", "r06_user_id" AS "user_id", "r06_backup_type" AS "backup_type", "r06_status" AS "status", "r06_file_name" AS "file_name", "r06_storage_path" AS "storage_path", "r06_file_size_bytes" AS "file_size_bytes", "r06_checksum_sha256" AS "checksum_sha256", "r06_schema_version" AS "schema_version", "r06_last_restore_status" AS "last_restore_status", "r06_last_restored_at" AS "last_restored_at", "r06_completed_at" AS "completed_at", "r06_created_at" AS "created_at", "r06_data_counts" AS "data_counts", "r06_attachment_count" AS "attachment_count", "r06_cleanup_warning" AS "cleanup_warning" FROM "public"."export_backup_records" WHERE "r06_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."backups" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."backups" ALTER COLUMN "schema_version" SET DEFAULT 1;

ALTER VIEW "public"."backups" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."backups" ALTER COLUMN "attachment_count" SET DEFAULT 0;

CREATE SEQUENCE public.budgets_id_seq;

SELECT setval('public.budgets_id_seq',value,called) FROM trial_sequence_state WHERE name='public.budgets_id_seq';

ALTER SEQUENCE public.budgets_id_seq OWNED BY "public"."budget_records"."r07_id";

CREATE VIEW "public"."budgets" WITH (security_invoker=true,security_barrier=true) AS SELECT "r07_id" AS "id", "r07_user_id" AS "user_id", "r07_category_id" AS "category_id", "r07_amount" AS "amount", "r07_month" AS "month", "r07_created_at" AS "created_at", "r07_updated_at" AS "updated_at" FROM "public"."budget_records" WHERE "r07_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."budgets" ALTER COLUMN "id" SET DEFAULT nextval('public.budgets_id_seq'::regclass);

ALTER VIEW "public"."budgets" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."budgets" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE SEQUENCE public.categories_id_seq;

SELECT setval('public.categories_id_seq',value,called) FROM trial_sequence_state WHERE name='public.categories_id_seq';

ALTER SEQUENCE public.categories_id_seq OWNED BY "public"."transaction_records"."r08_id";

CREATE VIEW "public"."categories" WITH (security_invoker=true,security_barrier=true) AS SELECT "r08_id" AS "id", "r08_name" AS "name", "r08_type" AS "type", "r08_icon" AS "icon", "r08_user_id" AS "user_id", "r08_color" AS "color", "r08_icon_image_path" AS "icon_image_path" FROM "public"."transaction_records" WHERE "r08_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."categories" ALTER COLUMN "id" SET DEFAULT nextval('public.categories_id_seq'::regclass);

ALTER VIEW "public"."categories" ALTER COLUMN "type" SET DEFAULT 'expense'::text;

CREATE VIEW "public"."coaching_messages" WITH (security_invoker=true,security_barrier=true) AS SELECT "r09_id" AS "id", "r09_session_id" AS "session_id", "r09_user_id" AS "user_id", "r09_role" AS "role", "r09_content" AS "content", "r09_reply_to_message_id" AS "reply_to_message_id", "r09_status" AS "status", "r09_error_code" AS "error_code", "r09_model" AS "model", "r09_prompt_tokens" AS "prompt_tokens", "r09_completion_tokens" AS "completion_tokens", "r09_created_at" AS "created_at", "r09_feedback" AS "feedback", "r09_ui_payload" AS "ui_payload" FROM "public"."coaching_records" WHERE "r09_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."coaching_messages" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."coaching_messages" ALTER COLUMN "status" SET DEFAULT 'completed'::text;

ALTER VIEW "public"."coaching_messages" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."coaching_messages" ALTER COLUMN "ui_payload" SET DEFAULT '{}'::jsonb;

CREATE SEQUENCE public.coaching_retrievals_id_seq;

SELECT setval('public.coaching_retrievals_id_seq',value,called) FROM trial_sequence_state WHERE name='public.coaching_retrievals_id_seq';

ALTER SEQUENCE public.coaching_retrievals_id_seq OWNED BY "public"."coaching_records"."r10_id";

CREATE VIEW "public"."coaching_retrievals" WITH (security_invoker=true,security_barrier=true) AS SELECT "r10_id" AS "id", "r10_user_id" AS "user_id", "r10_assistant_message_id" AS "assistant_message_id", "r10_knowledge_document_id" AS "knowledge_document_id", "r10_rank" AS "rank", "r10_similarity" AS "similarity", "r10_title" AS "title", "r10_source" AS "source", "r10_created_at" AS "created_at" FROM "public"."coaching_records" WHERE "r10_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."coaching_retrievals" ALTER COLUMN "id" SET DEFAULT nextval('public.coaching_retrievals_id_seq'::regclass);

ALTER VIEW "public"."coaching_retrievals" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."coaching_sessions" WITH (security_invoker=true,security_barrier=true) AS SELECT "r11_id" AS "id", "r11_user_id" AS "user_id", "r11_title" AS "title", "r11_created_at" AS "created_at", "r11_updated_at" AS "updated_at", "r11_last_message_at" AS "last_message_at" FROM "public"."coaching_records" WHERE "r11_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."coaching_sessions" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."coaching_sessions" ALTER COLUMN "title" SET DEFAULT 'New conversation'::text;

ALTER VIEW "public"."coaching_sessions" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."coaching_sessions" ALTER COLUMN "updated_at" SET DEFAULT now();

ALTER VIEW "public"."coaching_sessions" ALTER COLUMN "last_message_at" SET DEFAULT now();

CREATE VIEW "public"."data_exports" WITH (security_invoker=true,security_barrier=true) AS SELECT "r12_id" AS "id", "r12_user_id" AS "user_id", "r12_format" AS "format", "r12_status" AS "status", "r12_file_name" AS "file_name", "r12_file_size_bytes" AS "file_size_bytes", "r12_date_from" AS "date_from", "r12_date_to" AS "date_to", "r12_completed_at" AS "completed_at", "r12_created_at" AS "created_at" FROM "public"."export_backup_records" WHERE "r12_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."data_exports" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."data_exports" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."export_contents" WITH (security_invoker=true,security_barrier=true) AS SELECT "r13_export_id" AS "export_id", "r13_content_type" AS "content_type" FROM "public"."export_backup_records" WHERE "r13_export_id" IS NOT NULL WITH CASCADED CHECK OPTION;

CREATE SEQUENCE public.knowledge_documents_id_seq;

SELECT setval('public.knowledge_documents_id_seq',value,called) FROM trial_sequence_state WHERE name='public.knowledge_documents_id_seq';

ALTER SEQUENCE public.knowledge_documents_id_seq OWNED BY "public"."knowledge_records"."r14_id";

CREATE VIEW "public"."knowledge_documents" WITH (security_invoker=true,security_barrier=true) AS SELECT "r14_id" AS "id", "r14_title" AS "title", "r14_content" AS "content", "r14_source" AS "source", "r14_embedding" AS "embedding", "r14_created_at" AS "created_at", "r14_page_number" AS "page_number", "r14_chunk_index" AS "chunk_index", "r14_content_hash" AS "content_hash", "r14_revision_id" AS "revision_id", "r14_is_published" AS "is_published" FROM "public"."knowledge_records" WHERE "r14_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."knowledge_documents" ALTER COLUMN "id" SET DEFAULT nextval('public.knowledge_documents_id_seq'::regclass);

ALTER VIEW "public"."knowledge_documents" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."knowledge_documents" ALTER COLUMN "is_published" SET DEFAULT false;

CREATE VIEW "public"."knowledge_revisions" WITH (security_invoker=true,security_barrier=true) AS SELECT "r15_id" AS "id", "r15_source_id" AS "source_id", "r15_title" AS "title", "r15_content" AS "content", "r15_source_urls" AS "source_urls", "r15_checked_at" AS "checked_at", "r15_file_path" AS "file_path", "r15_status" AS "status", "r15_created_by" AS "created_by", "r15_created_at" AS "created_at", "r15_lease_token" AS "lease_token", "r15_lease_until" AS "lease_until", "r15_attempts" AS "attempts", "r15_chunk_count" AS "chunk_count", "r15_error_message" AS "error_message" FROM "public"."knowledge_records" WHERE "r15_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."knowledge_revisions" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."knowledge_revisions" ALTER COLUMN "source_urls" SET DEFAULT '[]'::jsonb;

ALTER VIEW "public"."knowledge_revisions" ALTER COLUMN "status" SET DEFAULT 'draft'::text;

ALTER VIEW "public"."knowledge_revisions" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."knowledge_revisions" ALTER COLUMN "attempts" SET DEFAULT 0;

ALTER VIEW "public"."knowledge_revisions" ALTER COLUMN "chunk_count" SET DEFAULT 0;

CREATE VIEW "public"."knowledge_sources" WITH (security_invoker=true,security_barrier=true) AS SELECT "r16_id" AS "id", "r16_source_key" AS "source_key", "r16_title" AS "title", "r16_archived" AS "archived", "r16_published_revision_id" AS "published_revision_id", "r16_latest_revision_id" AS "latest_revision_id", "r16_created_at" AS "created_at", "r16_updated_at" AS "updated_at" FROM "public"."knowledge_records" WHERE "r16_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."knowledge_sources" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."knowledge_sources" ALTER COLUMN "archived" SET DEFAULT false;

ALTER VIEW "public"."knowledge_sources" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."knowledge_sources" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE VIEW "public"."monthly_budgets" WITH (security_invoker=true,security_barrier=true) AS SELECT "r17_id" AS "id", "r17_user_id" AS "user_id", "r17_month" AS "month", "r17_limit_amount" AS "limit_amount", "r17_created_at" AS "created_at", "r17_updated_at" AS "updated_at" FROM "public"."budget_records" WHERE "r17_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."monthly_budgets" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."monthly_budgets" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."monthly_budgets" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE VIEW "public"."notification_preferences" WITH (security_invoker=true,security_barrier=true) AS SELECT "r18_user_id" AS "user_id", "r18_budget_enabled" AS "budget_enabled", "r18_savings_enabled" AS "savings_enabled", "r18_savings_lead_days" AS "savings_lead_days", "r18_savings_reminder_time" AS "savings_reminder_time", "r18_savings_milestones_enabled" AS "savings_milestones_enabled", "r18_spending_enabled" AS "spending_enabled", "r18_spending_frequency" AS "spending_frequency", "r18_spending_weekday" AS "spending_weekday", "r18_spending_reminder_time" AS "spending_reminder_time", "r18_bills_enabled" AS "bills_enabled", "r18_default_bill_lead_days" AS "default_bill_lead_days", "r18_default_bill_reminder_time" AS "default_bill_reminder_time", "r18_timezone" AS "timezone", "r18_created_at" AS "created_at", "r18_updated_at" AS "updated_at" FROM "public"."alert_records" WHERE "r18_user_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "budget_enabled" SET DEFAULT true;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "savings_enabled" SET DEFAULT true;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "savings_lead_days" SET DEFAULT 7;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "savings_reminder_time" SET DEFAULT '09:00:00'::time without time zone;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "savings_milestones_enabled" SET DEFAULT true;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "spending_enabled" SET DEFAULT true;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "spending_frequency" SET DEFAULT 'weekly'::text;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "spending_reminder_time" SET DEFAULT '20:00:00'::time without time zone;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "bills_enabled" SET DEFAULT true;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "default_bill_lead_days" SET DEFAULT 3;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "default_bill_reminder_time" SET DEFAULT '09:00:00'::time without time zone;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "timezone" SET DEFAULT 'Asia/Kuala_Lumpur'::text;

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."notification_preferences" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE VIEW "public"."reminders" WITH (security_invoker=true,security_barrier=true) AS SELECT "r19_id" AS "id", "r19_user_id" AS "user_id", "r19_type" AS "type", "r19_title" AS "title", "r19_amount" AS "amount", "r19_due_at" AS "due_at", "r19_lead_days" AS "lead_days", "r19_recurrence" AS "recurrence", "r19_recurrence_anchor_day" AS "recurrence_anchor_day", "r19_enabled" AS "enabled", "r19_next_trigger_at" AS "next_trigger_at", "r19_last_triggered_at" AS "last_triggered_at", "r19_created_at" AS "created_at", "r19_updated_at" AS "updated_at" FROM "public"."alert_records" WHERE "r19_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."reminders" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."reminders" ALTER COLUMN "type" SET DEFAULT 'bill'::text;

ALTER VIEW "public"."reminders" ALTER COLUMN "lead_days" SET DEFAULT 3;

ALTER VIEW "public"."reminders" ALTER COLUMN "recurrence" SET DEFAULT 'none'::text;

ALTER VIEW "public"."reminders" ALTER COLUMN "enabled" SET DEFAULT true;

ALTER VIEW "public"."reminders" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."reminders" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE VIEW "public"."report_attempts" WITH (security_invoker=true,security_barrier=true) AS SELECT "r20_attempt_id" AS "attempt_id", "r20_user_id" AS "user_id", "r20_message_id" AS "message_id", "r20_action_id" AS "action_id", "r20_storage_path" AS "storage_path", "r20_period" AS "period", "r20_report_type" AS "report_type", "r20_start_date" AS "start_date", "r20_end_date" AS "end_date", "r20_category_id" AS "category_id", "r20_category_name" AS "category_name", "r20_arguments" AS "arguments", "r20_status" AS "status", "r20_report_id" AS "report_id", "r20_lease_expires_at" AS "lease_expires_at", "r20_lease_owner" AS "lease_owner", "r20_lease_renewed_at" AS "lease_renewed_at", "r20_lease_renewal_count" AS "lease_renewal_count", "r20_created_at" AS "created_at", "r20_updated_at" AS "updated_at" FROM "public"."report_records" WHERE "r20_attempt_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."report_attempts" ALTER COLUMN "arguments" SET DEFAULT '{}'::jsonb;

ALTER VIEW "public"."report_attempts" ALTER COLUMN "status" SET DEFAULT 'active'::text;

ALTER VIEW "public"."report_attempts" ALTER COLUMN "lease_renewal_count" SET DEFAULT 0;

ALTER VIEW "public"."report_attempts" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."report_attempts" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE SEQUENCE public.reports_id_seq;

SELECT setval('public.reports_id_seq',value,called) FROM trial_sequence_state WHERE name='public.reports_id_seq';

ALTER SEQUENCE public.reports_id_seq OWNED BY "public"."report_records"."r21_id";

CREATE VIEW "public"."reports" WITH (security_invoker=true,security_barrier=true) AS SELECT "r21_id" AS "id", "r21_user_id" AS "user_id", "r21_period" AS "period", "r21_type" AS "type", "r21_generated_at" AS "generated_at", "r21_title" AS "title", "r21_file_name" AS "file_name", "r21_storage_path" AS "storage_path", "r21_report_key" AS "report_key", "r21_start_date" AS "start_date", "r21_end_date" AS "end_date", "r21_category_id" AS "category_id" FROM "public"."report_records" WHERE "r21_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."reports" ALTER COLUMN "id" SET DEFAULT nextval('public.reports_id_seq'::regclass);

ALTER VIEW "public"."reports" ALTER COLUMN "generated_at" SET DEFAULT now();

CREATE SEQUENCE public.savings_contributions_id_seq;

SELECT setval('public.savings_contributions_id_seq',value,called) FROM trial_sequence_state WHERE name='public.savings_contributions_id_seq';

ALTER SEQUENCE public.savings_contributions_id_seq OWNED BY "public"."savings_records"."r22_id";

CREATE VIEW "public"."savings_contributions" WITH (security_invoker=true,security_barrier=true) AS SELECT "r22_id" AS "id", "r22_goal_id" AS "goal_id", "r22_amount" AS "amount", "r22_contributed_on" AS "contributed_on", "r22_note" AS "note", "r22_created_at" AS "created_at" FROM "public"."savings_records" WHERE "r22_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."savings_contributions" ALTER COLUMN "id" SET DEFAULT nextval('public.savings_contributions_id_seq'::regclass);

ALTER VIEW "public"."savings_contributions" ALTER COLUMN "contributed_on" SET DEFAULT CURRENT_DATE;

ALTER VIEW "public"."savings_contributions" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."savings_goals" WITH (security_invoker=true,security_barrier=true) AS SELECT "r23_id" AS "id", "r23_user_id" AS "user_id", "r23_name" AS "name", "r23_target_amount" AS "target_amount", "r23_current_amount" AS "current_amount", "r23_created_at" AS "created_at", "r23_updated_at" AS "updated_at", "r23_deadline" AS "deadline" FROM "public"."savings_records" WHERE "r23_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."savings_goals" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."savings_goals" ALTER COLUMN "current_amount" SET DEFAULT 0;

ALTER VIEW "public"."savings_goals" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."savings_goals" ALTER COLUMN "updated_at" SET DEFAULT now();

CREATE VIEW "public"."transactions" WITH (security_invoker=true,security_barrier=true) AS SELECT "r24_id" AS "id", "r24_user_id" AS "user_id", "r24_category_id" AS "category_id", "r24_amount" AS "amount", "r24_transaction_date" AS "transaction_date", "r24_description" AS "description", "r24_source" AS "source", "r24_receipt_image_path" AS "receipt_image_path", "r24_created_at" AS "created_at", "r24_updated_at" AS "updated_at", "r24_receipt_items" AS "receipt_items" FROM "public"."transaction_records" WHERE "r24_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."transactions" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."transactions" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."transactions" ALTER COLUMN "updated_at" SET DEFAULT now();

ALTER VIEW "public"."transactions" ALTER COLUMN "receipt_items" SET DEFAULT '[]'::jsonb;

CREATE VIEW "public"."user_categories" WITH (security_invoker=true,security_barrier=true) AS SELECT "r25_user_id" AS "user_id", "r25_category_id" AS "category_id", "r25_created_at" AS "created_at" FROM "public"."transaction_records" WHERE "r25_user_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."user_categories" ALTER COLUMN "created_at" SET DEFAULT now();

CREATE VIEW "public"."user_devices" WITH (security_invoker=true,security_barrier=true) AS SELECT "r26_id" AS "id", "r26_user_id" AS "user_id", "r26_expo_push_token" AS "expo_push_token", "r26_platform" AS "platform", "r26_device_name" AS "device_name", "r26_active" AS "active", "r26_last_seen_at" AS "last_seen_at", "r26_last_error" AS "last_error", "r26_created_at" AS "created_at", "r26_updated_at" AS "updated_at" FROM "public"."alert_records" WHERE "r26_id" IS NOT NULL WITH CASCADED CHECK OPTION;

ALTER VIEW "public"."user_devices" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

ALTER VIEW "public"."user_devices" ALTER COLUMN "active" SET DEFAULT true;

ALTER VIEW "public"."user_devices" ALTER COLUMN "last_seen_at" SET DEFAULT now();

ALTER VIEW "public"."user_devices" ALTER COLUMN "created_at" SET DEFAULT now();

ALTER VIEW "public"."user_devices" ALTER COLUMN "updated_at" SET DEFAULT now();

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

CREATE OR REPLACE FUNCTION private.is_active_account()
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$

  select exists(select 1 from public.account_access where user_id=auth.uid() and status='active');

$function$
;

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

CREATE OR REPLACE FUNCTION private.require_admin(p_actor uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$

begin

  if not exists(select 1 from public.account_access where user_id=p_actor and role='admin' and status='active') then raise exception 'ADMIN_FORBIDDEN' using errcode='42501'; end if;

end $function$
;

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

CREATE OR REPLACE FUNCTION public.admin_fail_knowledge_revision(p_revision uuid, p_lease uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ begin

  update public.knowledge_revisions set status='failed',error_message='Document processing failed. Retry preparation.',lease_token=null,lease_until=null where id=p_revision and status='processing' and lease_token=p_lease;

end $function$
;

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

CREATE OR REPLACE FUNCTION public.admin_renew_knowledge_lease(p_revision uuid, p_lease uuid)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$ begin

  update public.knowledge_revisions set lease_until=now()+interval '10 minutes' where id=p_revision and status='processing' and lease_token=p_lease and lease_until>now();

  if not found then raise exception 'ADMIN_CONFLICT'; end if;

end $function$
;

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

CREATE OR REPLACE VIEW public.published_knowledge_documents WITH (security_invoker=true) AS SELECT * FROM public.knowledge_documents WHERE is_published;

DROP POLICY IF EXISTS "Users can upload own financial reports" ON storage.objects;

CREATE POLICY "Users can upload own financial reports" ON "storage"."objects" FOR INSERT TO "authenticated" WITH CHECK ((("bucket_id" = 'financial-reports'::"text") AND (("storage"."foldername"("name"))[1] = ( SELECT ("auth"."uid"())::"text" AS "uid")) AND ((COALESCE(("storage"."foldername"("name"))[2], ''::"text") <> 'coach'::"text") OR (EXISTS ( SELECT 1
   FROM "public"."report_attempts" "a"
  WHERE (("a"."user_id" = ( SELECT "auth"."uid"() AS "uid")) AND ("a"."storage_path" = "objects"."name") AND ("a"."status" = 'active'::"text") AND ("a"."lease_expires_at" > "clock_timestamp"())))))));

ALTER TABLE public.coaching_records ADD CONSTRAINT trial_session_owner_unique UNIQUE ("r11_id", "r11_user_id");

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_processing_leases_pkey" UNIQUE ("r01_message_id");

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "financial_backup_snapshots_pkey" UNIQUE ("r02_backup_id");

ALTER TABLE "public"."account_records" ADD CONSTRAINT "account_access_pkey" UNIQUE ("r03_user_id");

ALTER TABLE "public"."account_records" ADD CONSTRAINT "admin_audit_logs_pkey" UNIQUE ("r04_id");

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_pkey" UNIQUE ("r05_id");

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_pkey" UNIQUE ("r06_id");

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_pkey" UNIQUE ("r07_id");

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "categories_pkey" UNIQUE ("r08_id");

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_pkey" UNIQUE ("r09_id");

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_pkey" UNIQUE ("r10_id");

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_sessions_pkey" UNIQUE ("r11_id");

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_pkey" UNIQUE ("r12_id");

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "export_contents_pkey" UNIQUE ("r13_export_id", "r13_content_type");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_documents_pkey" UNIQUE ("r14_id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_revisions_pkey" UNIQUE ("r15_id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_sources_pkey" UNIQUE ("r16_id");

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "monthly_budgets_pkey" UNIQUE ("r17_id");

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_pkey" UNIQUE ("r18_user_id");

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_pkey" UNIQUE ("r19_id");

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_pkey" UNIQUE ("r20_attempt_id");

ALTER TABLE "public"."report_records" ADD CONSTRAINT "reports_pkey" UNIQUE ("r21_id");

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_contributions_pkey" UNIQUE ("r22_id");

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_goals_pkey" UNIQUE ("r23_id");

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_pkey" UNIQUE ("r24_id");

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "user_categories_pkey" UNIQUE ("r25_user_id", "r25_category_id");

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_pkey" UNIQUE ("r26_id");

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_user_id_dedupe_key_key" UNIQUE ("r05_user_id", "r05_dedupe_key");

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_user_id_category_id_month_key" UNIQUE ("r07_user_id", "r07_category_id", "r07_month");

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_reply_to_message_id_key" UNIQUE ("r09_reply_to_message_id");

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_assistant_message_id_knowledge_document_key" UNIQUE ("r10_assistant_message_id", "r10_knowledge_document_id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_revisions_source_id_id_key" UNIQUE ("r15_source_id", "r15_id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_sources_source_key_key" UNIQUE ("r16_source_key");

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "monthly_budgets_user_id_month_key" UNIQUE ("r17_user_id", "r17_month");

ALTER TABLE "public"."report_records" ADD CONSTRAINT "reports_user_report_key_key" UNIQUE ("r21_user_id", "r21_report_key");

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_expo_push_token_key" UNIQUE ("r26_expo_push_token");

ALTER TABLE "public"."account_records" ADD CONSTRAINT "account_access_role_check" CHECK (_record_kind <> 'public.account_access' OR (("r03_role" = ANY (ARRAY['student'::text, 'admin'::text]))));

ALTER TABLE "public"."account_records" ADD CONSTRAINT "account_access_status_check" CHECK (_record_kind <> 'public.account_access' OR (("r03_status" = ANY (ARRAY['active'::text, 'suspended'::text]))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_dedupe_key_check" CHECK (_record_kind <> 'public.alerts' OR (((char_length(btrim("r05_dedupe_key")) >= 1) AND (char_length(btrim("r05_dedupe_key")) <= 200))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_delivery_attempt_count_check" CHECK (_record_kind <> 'public.alerts' OR ((("r05_delivery_attempt_count" >= 0) AND ("r05_delivery_attempt_count" <= 100))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_delivery_error_check" CHECK (_record_kind <> 'public.alerts' OR ((("r05_delivery_error" IS NULL) OR (char_length("r05_delivery_error") <= 1000))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_delivery_status_check" CHECK (_record_kind <> 'public.alerts' OR (("r05_delivery_status" = ANY (ARRAY['pending'::text, 'sending'::text, 'sent'::text, 'delivered'::text, 'partially_delivered'::text, 'retryable'::text, 'failed'::text, 'no_active_device'::text]))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_kind_check" CHECK (_record_kind <> 'public.alerts' OR (("r05_kind" = ANY (ARRAY['alert'::text, 'insight'::text]))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_message_check" CHECK (_record_kind <> 'public.alerts' OR (((char_length(btrim("r05_message")) >= 1) AND (char_length(btrim("r05_message")) <= 500))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_title_check" CHECK (_record_kind <> 'public.alerts' OR (((char_length(btrim("r05_title")) >= 1) AND (char_length(btrim("r05_title")) <= 100))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_type_check" CHECK (_record_kind <> 'public.alerts' OR (("r05_type" = ANY (ARRAY['budget_warning'::text, 'budget_exceeded'::text, 'savings_deadline'::text, 'savings_milestone'::text, 'spending_reminder'::text, 'bill_reminder'::text]))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_attachment_count_check" CHECK (_record_kind <> 'public.backups' OR (("r06_attachment_count" >= 0)));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_backup_type_check" CHECK (_record_kind <> 'public.backups' OR (("r06_backup_type" = ANY (ARRAY['manual'::text, 'automatic'::text]))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_checksum_sha256_check" CHECK (_record_kind <> 'public.backups' OR ((("r06_checksum_sha256" IS NULL) OR ("r06_checksum_sha256" ~ '^[a-f0-9]{64}$'::text))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_file_name_check" CHECK (_record_kind <> 'public.backups' OR (((char_length(btrim("r06_file_name")) >= 1) AND (char_length(btrim("r06_file_name")) <= 255))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_file_size_bytes_check" CHECK (_record_kind <> 'public.backups' OR ((("r06_file_size_bytes" IS NULL) OR ("r06_file_size_bytes" >= 0))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_last_restore_status_check" CHECK (_record_kind <> 'public.backups' OR ((("r06_last_restore_status" IS NULL) OR ("r06_last_restore_status" = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text])))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_schema_version_check" CHECK (_record_kind <> 'public.backups' OR (("r06_schema_version" > 0)));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_status_check" CHECK (_record_kind <> 'public.backups' OR (("r06_status" = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text]))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_storage_path_check" CHECK (_record_kind <> 'public.backups' OR ((("r06_storage_path" IS NULL) OR ((char_length("r06_storage_path") >= 1) AND (char_length("r06_storage_path") <= 512)))));

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_amount_positive_check" CHECK (_record_kind <> 'public.budgets' OR (("r07_amount" > (0)::numeric)));

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_month_first_day_check" CHECK (_record_kind <> 'public.budgets' OR (("r07_month" = (date_trunc('month'::text, ("r07_month")::timestamp with time zone))::date)));

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "categories_type_check" CHECK (_record_kind <> 'public.categories' OR (("r08_type" = ANY (ARRAY['expense'::text, 'income'::text]))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_prompt_tokens_check" CHECK (_record_kind <> 'public.coaching_messages' OR ((("r09_prompt_tokens" IS NULL) OR ("r09_prompt_tokens" >= 0))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_completion_tokens_check" CHECK (_record_kind <> 'public.coaching_messages' OR ((("r09_completion_tokens" IS NULL) OR ("r09_completion_tokens" >= 0))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_content_check" CHECK (_record_kind <> 'public.coaching_messages' OR (((char_length(btrim("r09_content")) >= 1) AND (char_length(btrim("r09_content")) <= 8000))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_feedback_check" CHECK (_record_kind <> 'public.coaching_messages' OR ((("r09_feedback" IS NULL) OR (("r09_role" = 'assistant'::text) AND ("r09_feedback" = ANY (ARRAY['helpful'::text, 'not_helpful'::text]))))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_reply_shape_check" CHECK (_record_kind <> 'public.coaching_messages' OR (((("r09_role" = 'user'::text) AND ("r09_reply_to_message_id" IS NULL)) OR (("r09_role" = 'assistant'::text) AND ("r09_reply_to_message_id" IS NOT NULL)))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_role_check" CHECK (_record_kind <> 'public.coaching_messages' OR (("r09_role" = ANY (ARRAY['user'::text, 'assistant'::text]))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_status_check" CHECK (_record_kind <> 'public.coaching_messages' OR (("r09_status" = ANY (ARRAY['completed'::text, 'failed'::text]))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_ui_payload_object_check" CHECK (_record_kind <> 'public.coaching_messages' OR ((jsonb_typeof("r09_ui_payload") = 'object'::text)));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_rank_check" CHECK (_record_kind <> 'public.coaching_retrievals' OR ((("r10_rank" >= 1) AND ("r10_rank" <= 10))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_similarity_check" CHECK (_record_kind <> 'public.coaching_retrievals' OR ((("r10_similarity" >= ('-1'::integer)::double precision) AND ("r10_similarity" <= (1)::double precision))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_sessions_title_check" CHECK (_record_kind <> 'public.coaching_sessions' OR (((char_length(btrim("r11_title")) >= 1) AND (char_length(btrim("r11_title")) <= 80))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_date_range_check" CHECK (_record_kind <> 'public.data_exports' OR (("r12_date_from" <= "r12_date_to")));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_file_name_check" CHECK (_record_kind <> 'public.data_exports' OR (((char_length(btrim("r12_file_name")) >= 1) AND (char_length(btrim("r12_file_name")) <= 255))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_file_size_bytes_check" CHECK (_record_kind <> 'public.data_exports' OR ((("r12_file_size_bytes" IS NULL) OR ("r12_file_size_bytes" >= 0))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_format_check" CHECK (_record_kind <> 'public.data_exports' OR (("r12_format" = ANY (ARRAY['csv'::text, 'pdf'::text]))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_status_check" CHECK (_record_kind <> 'public.data_exports' OR (("r12_status" = ANY (ARRAY['pending'::text, 'processing'::text, 'completed'::text, 'failed'::text]))));

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "export_contents_content_type_check" CHECK (_record_kind <> 'public.export_contents' OR (("r13_content_type" = ANY (ARRAY['transaction'::text, 'budget'::text, 'savings'::text, 'report'::text]))));

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_revisions_status_check" CHECK (_record_kind <> 'public.knowledge_revisions' OR (("r15_status" = ANY (ARRAY['draft'::text, 'queued'::text, 'processing'::text, 'ready'::text, 'published'::text, 'failed'::text]))));

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "monthly_budgets_limit_amount_check" CHECK (_record_kind <> 'public.monthly_budgets' OR (("r17_limit_amount" > (0)::numeric)));

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "monthly_budgets_month_first_day_check" CHECK (_record_kind <> 'public.monthly_budgets' OR (("r17_month" = (date_trunc('month'::text, ("r17_month")::timestamp with time zone))::date)));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_bill_lead_days_check" CHECK (_record_kind <> 'public.notification_preferences' OR ((("r18_default_bill_lead_days" >= 0) AND ("r18_default_bill_lead_days" <= 365))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_savings_lead_days_check" CHECK (_record_kind <> 'public.notification_preferences' OR ((("r18_savings_lead_days" >= 0) AND ("r18_savings_lead_days" <= 365))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_spending_frequency_check" CHECK (_record_kind <> 'public.notification_preferences' OR (("r18_spending_frequency" = ANY (ARRAY['daily'::text, 'weekly'::text]))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_spending_weekday_check" CHECK (_record_kind <> 'public.notification_preferences' OR ((("r18_spending_weekday" IS NULL) OR (("r18_spending_weekday" >= 0) AND ("r18_spending_weekday" <= 6)))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_timezone_check" CHECK (_record_kind <> 'public.notification_preferences' OR (((char_length(btrim("r18_timezone")) >= 1) AND (char_length(btrim("r18_timezone")) <= 100))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_amount_check" CHECK (_record_kind <> 'public.reminders' OR ((("r19_amount" IS NULL) OR ("r19_amount" > (0)::numeric))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_lead_days_check" CHECK (_record_kind <> 'public.reminders' OR ((("r19_lead_days" >= 0) AND ("r19_lead_days" <= 365))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_recurrence_anchor_day_check" CHECK (_record_kind <> 'public.reminders' OR ((("r19_recurrence_anchor_day" >= 1) AND ("r19_recurrence_anchor_day" <= 31))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_recurrence_check" CHECK (_record_kind <> 'public.reminders' OR (("r19_recurrence" = ANY (ARRAY['none'::text, 'weekly'::text, 'monthly'::text, 'yearly'::text]))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_title_check" CHECK (_record_kind <> 'public.reminders' OR (((char_length(btrim("r19_title")) >= 1) AND (char_length(btrim("r19_title")) <= 100))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_type_check" CHECK (_record_kind <> 'public.reminders' OR (("r19_type" = 'bill'::text)));

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_dates_check" CHECK (_record_kind <> 'public.report_attempts' OR (("r20_start_date" <= "r20_end_date")));

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_path_check" CHECK (_record_kind <> 'public.report_attempts' OR (("r20_storage_path" = (((("r20_user_id")::text || '/coach/'::text) || ("r20_attempt_id")::text) || '.pdf'::text))));

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_status_check" CHECK (_record_kind <> 'public.report_attempts' OR (("r20_status" = ANY (ARRAY['active'::text, 'completed'::text, 'cancelled'::text, 'superseded'::text]))));

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_type_check" CHECK (_record_kind <> 'public.report_attempts' OR (("r20_report_type" = ANY (ARRAY['monthly'::text, 'monthly_category'::text, 'multi_month'::text, 'multi_month_category'::text, 'custom'::text, 'custom_category'::text]))));

ALTER TABLE "public"."report_records" ADD CONSTRAINT "reports_pdf_metadata_check" CHECK (_record_kind <> 'public.reports' OR ((("r21_report_key" IS NULL) OR (("r21_title" IS NOT NULL) AND ("r21_file_name" IS NOT NULL) AND ("r21_storage_path" IS NOT NULL) AND ((char_length(btrim("r21_title")) >= 1) AND (char_length(btrim("r21_title")) <= 160)) AND ((char_length(btrim("r21_file_name")) >= 5) AND (char_length(btrim("r21_file_name")) <= 255)) AND ("r21_file_name" ~~ '%.pdf'::text) AND ((char_length(btrim("r21_storage_path")) >= 5) AND (char_length(btrim("r21_storage_path")) <= 512)) AND ("r21_storage_path" ~~ (("r21_user_id")::text || '/%'::text)) AND ("r21_start_date" IS NOT NULL) AND ("r21_end_date" IS NOT NULL) AND ("r21_start_date" <= "r21_end_date"))))) NOT VALID;

ALTER TABLE "public"."report_records" ADD CONSTRAINT "reports_period_length_check" CHECK (_record_kind <> 'public.reports' OR (((char_length(btrim("r21_period")) >= 7) AND (char_length(btrim("r21_period")) <= 50)))) NOT VALID;

ALTER TABLE "public"."report_records" ADD CONSTRAINT "reports_type_check" CHECK (_record_kind <> 'public.reports' OR (("r21_type" = ANY (ARRAY['monthly'::text, 'monthly_category'::text, 'multi_month'::text, 'multi_month_category'::text, 'custom'::text, 'custom_category'::text])))) NOT VALID;

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_contributions_amount_check" CHECK (_record_kind <> 'public.savings_contributions' OR (("r22_amount" > (0)::numeric)));

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_contributions_contributed_on_check" CHECK (_record_kind <> 'public.savings_contributions' OR (("r22_contributed_on" <= CURRENT_DATE)));

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_contributions_note_check" CHECK (_record_kind <> 'public.savings_contributions' OR ((("r22_note" IS NULL) OR (char_length("r22_note") <= 200))));

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_goals_current_nonnegative" CHECK (_record_kind <> 'public.savings_goals' OR (("r23_current_amount" >= (0)::numeric))) NOT VALID;

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_goals_name_not_blank" CHECK (_record_kind <> 'public.savings_goals' OR (((char_length(btrim("r23_name")) >= 1) AND (char_length(btrim("r23_name")) <= 100)))) NOT VALID;

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_goals_target_covers_current" CHECK (_record_kind <> 'public.savings_goals' OR (("r23_target_amount" >= "r23_current_amount"))) NOT VALID;

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_goals_target_positive" CHECK (_record_kind <> 'public.savings_goals' OR (("r23_target_amount" > (0)::numeric))) NOT VALID;

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_amount_check" CHECK (_record_kind <> 'public.transactions' OR (("r24_amount" > (0)::numeric)));

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_description_check" CHECK (_record_kind <> 'public.transactions' OR ((("r24_description" IS NULL) OR (char_length("r24_description") <= 300))));

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_receipt_image_path_check" CHECK (_record_kind <> 'public.transactions' OR ((("r24_receipt_image_path" IS NULL) OR ((char_length("r24_receipt_image_path") >= 1) AND (char_length("r24_receipt_image_path") <= 512)))));

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_receipt_items_valid" CHECK (_record_kind <> 'public.transactions' OR (private.valid_receipt_items("r24_receipt_items")));

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_source_check" CHECK (_record_kind <> 'public.transactions' OR (((char_length(btrim("r24_source")) >= 1) AND (char_length(btrim("r24_source")) <= 120))));

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_transaction_date_check" CHECK (_record_kind <> 'public.transactions' OR (("r24_transaction_date" <= CURRENT_DATE)));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_device_name_check" CHECK (_record_kind <> 'public.user_devices' OR ((("r26_device_name" IS NULL) OR (char_length("r26_device_name") <= 100))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_last_error_check" CHECK (_record_kind <> 'public.user_devices' OR ((("r26_last_error" IS NULL) OR (char_length("r26_last_error") <= 1000))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_platform_check" CHECK (_record_kind <> 'public.user_devices' OR (("r26_platform" = ANY (ARRAY['android'::text, 'ios'::text]))));

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_token_check" CHECK (_record_kind <> 'public.user_devices' OR (((char_length(btrim("r26_expo_push_token")) >= 20) AND (char_length(btrim("r26_expo_push_token")) <= 255))));

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_processing_leases_message_id_fkey" FOREIGN KEY ("r01_message_id") REFERENCES "public"."coaching_records" ("r09_id") ON DELETE CASCADE;

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "financial_backup_snapshots_backup_id_fkey" FOREIGN KEY ("r02_backup_id") REFERENCES "public"."export_backup_records" ("r06_id") ON DELETE CASCADE;

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "financial_backup_snapshots_user_id_fkey" FOREIGN KEY ("r02_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."account_records" ADD CONSTRAINT "account_access_user_id_fkey" FOREIGN KEY ("r03_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."account_records" ADD CONSTRAINT "admin_audit_logs_actor_id_fkey" FOREIGN KEY ("r04_actor_id") REFERENCES "auth"."users" ("id") ON DELETE SET NULL;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_budget_id_fkey" FOREIGN KEY ("r05_budget_id") REFERENCES "public"."budget_records" ("r17_id") ON DELETE SET NULL;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_category_limit_id_fkey" FOREIGN KEY ("r05_category_limit_id") REFERENCES "public"."budget_records" ("r07_id") ON DELETE SET NULL;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_reminder_id_fkey" FOREIGN KEY ("r05_reminder_id") REFERENCES "public"."alert_records" ("r19_id") ON DELETE SET NULL;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_savings_goal_id_fkey" FOREIGN KEY ("r05_savings_goal_id") REFERENCES "public"."savings_records" ("r23_id") ON DELETE SET NULL;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "alerts_user_id_fkey" FOREIGN KEY ("r05_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "backups_user_id_fkey" FOREIGN KEY ("r06_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_category_id_fkey" FOREIGN KEY ("r07_category_id") REFERENCES "public"."transaction_records" ("r08_id") ON DELETE CASCADE;

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_monthly_budget_fkey" FOREIGN KEY ("r07_user_id", "r07_month") REFERENCES "public"."budget_records" ("r17_user_id", "r17_month") ON DELETE CASCADE;

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "budgets_user_id_fkey" FOREIGN KEY ("r07_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "categories_user_id_fkey" FOREIGN KEY ("r08_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_reply_to_message_id_fkey" FOREIGN KEY ("r09_reply_to_message_id") REFERENCES "public"."coaching_records" ("r09_id") ON DELETE SET NULL;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_session_id_fkey" FOREIGN KEY ("r09_session_id", "r09_user_id") REFERENCES public.coaching_records ("r11_id", "r11_user_id") ON DELETE CASCADE;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_messages_user_id_fkey" FOREIGN KEY ("r09_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_assistant_message_id_fkey" FOREIGN KEY ("r10_assistant_message_id") REFERENCES "public"."coaching_records" ("r09_id") ON DELETE CASCADE;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_knowledge_document_id_fkey" FOREIGN KEY ("r10_knowledge_document_id") REFERENCES "public"."knowledge_records" ("r14_id") ON DELETE SET NULL;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_retrievals_user_id_fkey" FOREIGN KEY ("r10_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."coaching_records" ADD CONSTRAINT "coaching_sessions_user_id_fkey" FOREIGN KEY ("r11_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "data_exports_user_id_fkey" FOREIGN KEY ("r12_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."export_backup_records" ADD CONSTRAINT "export_contents_export_id_fkey" FOREIGN KEY ("r13_export_id") REFERENCES "public"."export_backup_records" ("r12_id") ON DELETE CASCADE;

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_documents_revision_id_fkey" FOREIGN KEY ("r14_revision_id") REFERENCES "public"."knowledge_records" ("r15_id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_revisions_created_by_fkey" FOREIGN KEY ("r15_created_by") REFERENCES "auth"."users" ("id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_revisions_source_id_fkey" FOREIGN KEY ("r15_source_id") REFERENCES "public"."knowledge_records" ("r16_id");

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_sources_id_latest_revision_id_fkey" FOREIGN KEY ("r16_id", "r16_latest_revision_id") REFERENCES "public"."knowledge_records" ("r15_source_id", "r15_id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE "public"."knowledge_records" ADD CONSTRAINT "knowledge_sources_id_published_revision_id_fkey" FOREIGN KEY ("r16_id", "r16_published_revision_id") REFERENCES "public"."knowledge_records" ("r15_source_id", "r15_id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE "public"."budget_records" ADD CONSTRAINT "monthly_budgets_user_id_fkey" FOREIGN KEY ("r17_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "notification_preferences_user_id_fkey" FOREIGN KEY ("r18_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "reminders_user_id_fkey" FOREIGN KEY ("r19_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_message_id_fkey" FOREIGN KEY ("r20_message_id") REFERENCES "public"."coaching_records" ("r09_id") ON DELETE CASCADE;

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_report_id_fkey" FOREIGN KEY ("r20_report_id") REFERENCES "public"."report_records" ("r21_id") ON DELETE SET NULL;

ALTER TABLE "public"."report_records" ADD CONSTRAINT "report_attempts_user_id_fkey" FOREIGN KEY ("r20_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."report_records" ADD CONSTRAINT "reports_user_id_fkey" FOREIGN KEY ("r21_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_contributions_goal_id_fkey" FOREIGN KEY ("r22_goal_id") REFERENCES "public"."savings_records" ("r23_id") ON DELETE CASCADE;

ALTER TABLE "public"."savings_records" ADD CONSTRAINT "savings_goals_user_id_fkey" FOREIGN KEY ("r23_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_category_id_fkey" FOREIGN KEY ("r24_category_id") REFERENCES "public"."transaction_records" ("r08_id");

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "transactions_user_id_fkey" FOREIGN KEY ("r24_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "user_categories_category_id_fkey" FOREIGN KEY ("r25_category_id") REFERENCES "public"."transaction_records" ("r08_id") ON DELETE CASCADE;

ALTER TABLE "public"."transaction_records" ADD CONSTRAINT "user_categories_user_id_fkey" FOREIGN KEY ("r25_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

ALTER TABLE "public"."alert_records" ADD CONSTRAINT "user_devices_user_id_fkey" FOREIGN KEY ("r26_user_id") REFERENCES "auth"."users" ("id") ON DELETE CASCADE;

CREATE INDEX alerts_inbox_idx ON "public"."alert_records" USING btree ("r05_user_id", "r05_created_at" DESC) WHERE ("r05_dismissed_at" IS NULL);

CREATE INDEX alerts_unread_idx ON "public"."alert_records" USING btree ("r05_user_id", "r05_created_at" DESC) WHERE (("r05_read_at" IS NULL) AND ("r05_dismissed_at" IS NULL));

CREATE INDEX alerts_reminder_source_idx ON "public"."alert_records" USING btree ("r05_reminder_id") WHERE ("r05_reminder_id" IS NOT NULL);

CREATE INDEX alerts_savings_source_idx ON "public"."alert_records" USING btree ("r05_savings_goal_id") WHERE ("r05_savings_goal_id" IS NOT NULL);

CREATE INDEX alerts_budget_source_idx ON "public"."alert_records" USING btree ("r05_budget_id", "r05_category_limit_id") WHERE (("r05_budget_id" IS NOT NULL) OR ("r05_category_limit_id" IS NOT NULL));

CREATE INDEX alerts_delivery_retry_idx ON "public"."alert_records" USING btree ("r05_next_delivery_attempt_at", "r05_created_at") WHERE ("r05_delivery_status" = ANY (ARRAY['pending'::text, 'retryable'::text, 'sent'::text]));

CREATE INDEX backups_user_created_idx ON "public"."export_backup_records" USING btree ("r06_user_id", "r06_created_at" DESC);

CREATE INDEX backups_user_automatic_idx ON "public"."export_backup_records" USING btree ("r06_user_id", "r06_backup_type", "r06_status", "r06_completed_at" DESC);

CREATE INDEX budgets_user_month_idx ON "public"."budget_records" USING btree ("r07_user_id", "r07_month" DESC);

CREATE UNIQUE INDEX categories_user_name_unique ON "public"."transaction_records" USING btree ("r08_user_id", lower("r08_name")) WHERE ("r08_user_id" IS NOT NULL);

CREATE UNIQUE INDEX categories_default_name_unique ON "public"."transaction_records" USING btree (lower("r08_name")) WHERE ("r08_user_id" IS NULL);

CREATE INDEX coaching_messages_history_cursor_idx ON "public"."coaching_records" USING btree ("r09_user_id", "r09_session_id", "r09_created_at" DESC, "r09_id" DESC);

CREATE INDEX coaching_messages_session_created_idx ON "public"."coaching_records" USING btree ("r09_session_id", "r09_created_at");

CREATE INDEX coaching_messages_user_created_idx ON "public"."coaching_records" USING btree ("r09_user_id", "r09_created_at" DESC) WHERE ("r09_role" = 'user'::text);

CREATE INDEX coaching_retrievals_message_rank_idx ON "public"."coaching_records" USING btree ("r10_assistant_message_id", "r10_rank");

CREATE INDEX coaching_sessions_user_last_message_idx ON "public"."coaching_records" USING btree ("r11_user_id", "r11_last_message_at" DESC);

CREATE INDEX data_exports_user_created_idx ON "public"."export_backup_records" USING btree ("r12_user_id", "r12_created_at" DESC);

CREATE INDEX data_exports_user_period_idx ON "public"."export_backup_records" USING btree ("r12_user_id", "r12_date_from", "r12_date_to");

CREATE INDEX knowledge_documents_revision_idx ON "public"."knowledge_records" USING btree ("r14_revision_id");

CREATE INDEX knowledge_documents_fts_idx ON "public"."knowledge_records" USING gin ((((setweight(to_tsvector('simple'::regconfig, COALESCE("r14_title", ''::text)), 'A'::"char") || setweight(to_tsvector('simple'::regconfig, COALESCE("r14_source", ''::text)), 'B'::"char")) || setweight(to_tsvector('simple'::regconfig, "r14_content"), 'C'::"char")))) WHERE "r14_is_published";

CREATE INDEX knowledge_documents_embedding_idx ON "public"."knowledge_records" USING hnsw ("r14_embedding" public.vector_cosine_ops) WHERE "r14_is_published";

CREATE INDEX knowledge_revisions_queue_idx ON "public"."knowledge_records" USING btree ("r15_status", "r15_lease_until", "r15_created_at");

CREATE INDEX monthly_budgets_user_month_idx ON "public"."budget_records" USING btree ("r17_user_id", "r17_month" DESC);

CREATE INDEX notification_preferences_user_updated_idx ON "public"."alert_records" USING btree ("r18_user_id", "r18_updated_at" DESC);

CREATE INDEX reminders_due_idx ON "public"."alert_records" USING btree ("r19_next_trigger_at") WHERE (("r19_enabled" = true) AND ("r19_next_trigger_at" IS NOT NULL));

CREATE INDEX reminders_user_due_idx ON "public"."alert_records" USING btree ("r19_user_id", "r19_due_at", "r19_created_at" DESC);

CREATE INDEX report_attempts_owner_path_idx ON "public"."report_records" USING btree ("r20_user_id", "r20_storage_path");

CREATE INDEX report_attempts_owner_message_idx ON "public"."report_records" USING btree ("r20_user_id", "r20_message_id");

CREATE UNIQUE INDEX report_attempts_active_action_idx ON "public"."report_records" USING btree ("r20_action_id") WHERE ("r20_status" = 'active'::text);

CREATE INDEX reports_user_generated_idx ON "public"."report_records" USING btree ("r21_user_id", "r21_generated_at" DESC);

CREATE INDEX savings_contributions_history_idx ON "public"."savings_records" USING btree ("r22_goal_id", "r22_contributed_on" DESC, "r22_created_at" DESC);

CREATE INDEX savings_goals_user_id_idx ON "public"."savings_records" USING btree ("r23_user_id");

CREATE INDEX transactions_user_category_date_idx ON "public"."transaction_records" USING btree ("r24_user_id", "r24_category_id", "r24_transaction_date" DESC);

CREATE INDEX transactions_user_date_idx ON "public"."transaction_records" USING btree ("r24_user_id", "r24_transaction_date" DESC, "r24_created_at" DESC);

CREATE INDEX user_devices_active_idx ON "public"."alert_records" USING btree ("r26_user_id", "r26_last_seen_at" DESC) WHERE ("r26_active" = true);

UPDATE "public"."savings_records" c SET _owner_id=p."r23_user_id" FROM "public"."savings_records" p WHERE c."r22_goal_id"=p."r23_id";

ALTER TABLE "public"."savings_records" ADD UNIQUE ("r23_id","r23_user_id");

ALTER TABLE "public"."savings_records" ADD FOREIGN KEY ("r22_goal_id",_owner_id) REFERENCES "public"."savings_records" ("r23_id","r23_user_id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "public"."savings_records" ADD CHECK (_record_kind<>'public.savings_contributions' OR _owner_id IS NOT NULL);

CREATE OR REPLACE FUNCTION private.trial_r22_owner() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
  IF NEW."r22_goal_id" IS NOT NULL THEN
    SELECT user_id INTO NEW._owner_id FROM "public"."savings_goals" WHERE "id"=NEW."r22_goal_id";
  END IF;
  RETURN NEW;
END $$;

REVOKE ALL ON FUNCTION private.trial_r22_owner() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER trial_owner_r22_ BEFORE INSERT OR UPDATE OF "r22_goal_id" ON "public"."savings_records" FOR EACH ROW EXECUTE FUNCTION private.trial_r22_owner();

UPDATE "public"."export_backup_records" c SET _owner_id=p."r12_user_id" FROM "public"."export_backup_records" p WHERE c."r13_export_id"=p."r12_id";

ALTER TABLE "public"."export_backup_records" ADD UNIQUE ("r12_id","r12_user_id");

ALTER TABLE "public"."export_backup_records" ADD FOREIGN KEY ("r13_export_id",_owner_id) REFERENCES "public"."export_backup_records" ("r12_id","r12_user_id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "public"."export_backup_records" ADD CHECK (_record_kind<>'public.export_contents' OR _owner_id IS NOT NULL);

CREATE OR REPLACE FUNCTION private.trial_r13_owner() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
  IF NEW."r13_export_id" IS NOT NULL THEN
    SELECT user_id INTO NEW._owner_id FROM "public"."data_exports" WHERE "id"=NEW."r13_export_id";
  END IF;
  RETURN NEW;
END $$;

REVOKE ALL ON FUNCTION private.trial_r13_owner() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER trial_owner_r13_ BEFORE INSERT OR UPDATE OF "r13_export_id" ON "public"."export_backup_records" FOR EACH ROW EXECUTE FUNCTION private.trial_r13_owner();

CREATE POLICY "r03_account_access_self" ON "public"."account_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.account_access' AND EXISTS (SELECT 1 FROM (SELECT "public"."account_records"."r03_user_id" AS "user_id", "public"."account_records"."r03_role" AS "role", "public"."account_records"."r03_status" AS "status", "public"."account_records"."r03_email" AS "email", "public"."account_records"."r03_display_name" AS "display_name", "public"."account_records"."r03_created_at" AS "created_at", "public"."account_records"."r03_last_sign_in_at" AS "last_sign_in_at", "public"."account_records"."r03_updated_at" AS "updated_at") AS "account_access" WHERE ((user_id = auth.uid())))));

CREATE POLICY "r05_Users can add own alerts" ON "public"."alert_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.alerts' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r05_id" AS "id", "public"."alert_records"."r05_user_id" AS "user_id", "public"."alert_records"."r05_type" AS "type", "public"."alert_records"."r05_kind" AS "kind", "public"."alert_records"."r05_title" AS "title", "public"."alert_records"."r05_message" AS "message", "public"."alert_records"."r05_budget_id" AS "budget_id", "public"."alert_records"."r05_category_limit_id" AS "category_limit_id", "public"."alert_records"."r05_savings_goal_id" AS "savings_goal_id", "public"."alert_records"."r05_reminder_id" AS "reminder_id", "public"."alert_records"."r05_source_data" AS "source_data", "public"."alert_records"."r05_dedupe_key" AS "dedupe_key", "public"."alert_records"."r05_scheduled_for" AS "scheduled_for", "public"."alert_records"."r05_delivered_at" AS "delivered_at", "public"."alert_records"."r05_read_at" AS "read_at", "public"."alert_records"."r05_dismissed_at" AS "dismissed_at", "public"."alert_records"."r05_delivery_status" AS "delivery_status", "public"."alert_records"."r05_delivery_error" AS "delivery_error", "public"."alert_records"."r05_delivery_attempt_count" AS "delivery_attempt_count", "public"."alert_records"."r05_delivery_claimed_at" AS "delivery_claimed_at", "public"."alert_records"."r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "public"."alert_records"."r05_delivery_receipts" AS "delivery_receipts", "public"."alert_records"."r05_created_at" AS "created_at") AS "alerts" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r05_Users can read own alerts" ON "public"."alert_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.alerts' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r05_id" AS "id", "public"."alert_records"."r05_user_id" AS "user_id", "public"."alert_records"."r05_type" AS "type", "public"."alert_records"."r05_kind" AS "kind", "public"."alert_records"."r05_title" AS "title", "public"."alert_records"."r05_message" AS "message", "public"."alert_records"."r05_budget_id" AS "budget_id", "public"."alert_records"."r05_category_limit_id" AS "category_limit_id", "public"."alert_records"."r05_savings_goal_id" AS "savings_goal_id", "public"."alert_records"."r05_reminder_id" AS "reminder_id", "public"."alert_records"."r05_source_data" AS "source_data", "public"."alert_records"."r05_dedupe_key" AS "dedupe_key", "public"."alert_records"."r05_scheduled_for" AS "scheduled_for", "public"."alert_records"."r05_delivered_at" AS "delivered_at", "public"."alert_records"."r05_read_at" AS "read_at", "public"."alert_records"."r05_dismissed_at" AS "dismissed_at", "public"."alert_records"."r05_delivery_status" AS "delivery_status", "public"."alert_records"."r05_delivery_error" AS "delivery_error", "public"."alert_records"."r05_delivery_attempt_count" AS "delivery_attempt_count", "public"."alert_records"."r05_delivery_claimed_at" AS "delivery_claimed_at", "public"."alert_records"."r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "public"."alert_records"."r05_delivery_receipts" AS "delivery_receipts", "public"."alert_records"."r05_created_at" AS "created_at") AS "alerts" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r05_Users can update own alerts" ON "public"."alert_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.alerts' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r05_id" AS "id", "public"."alert_records"."r05_user_id" AS "user_id", "public"."alert_records"."r05_type" AS "type", "public"."alert_records"."r05_kind" AS "kind", "public"."alert_records"."r05_title" AS "title", "public"."alert_records"."r05_message" AS "message", "public"."alert_records"."r05_budget_id" AS "budget_id", "public"."alert_records"."r05_category_limit_id" AS "category_limit_id", "public"."alert_records"."r05_savings_goal_id" AS "savings_goal_id", "public"."alert_records"."r05_reminder_id" AS "reminder_id", "public"."alert_records"."r05_source_data" AS "source_data", "public"."alert_records"."r05_dedupe_key" AS "dedupe_key", "public"."alert_records"."r05_scheduled_for" AS "scheduled_for", "public"."alert_records"."r05_delivered_at" AS "delivered_at", "public"."alert_records"."r05_read_at" AS "read_at", "public"."alert_records"."r05_dismissed_at" AS "dismissed_at", "public"."alert_records"."r05_delivery_status" AS "delivery_status", "public"."alert_records"."r05_delivery_error" AS "delivery_error", "public"."alert_records"."r05_delivery_attempt_count" AS "delivery_attempt_count", "public"."alert_records"."r05_delivery_claimed_at" AS "delivery_claimed_at", "public"."alert_records"."r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "public"."alert_records"."r05_delivery_receipts" AS "delivery_receipts", "public"."alert_records"."r05_created_at" AS "created_at") AS "alerts" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.alerts' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r05_id" AS "id", "public"."alert_records"."r05_user_id" AS "user_id", "public"."alert_records"."r05_type" AS "type", "public"."alert_records"."r05_kind" AS "kind", "public"."alert_records"."r05_title" AS "title", "public"."alert_records"."r05_message" AS "message", "public"."alert_records"."r05_budget_id" AS "budget_id", "public"."alert_records"."r05_category_limit_id" AS "category_limit_id", "public"."alert_records"."r05_savings_goal_id" AS "savings_goal_id", "public"."alert_records"."r05_reminder_id" AS "reminder_id", "public"."alert_records"."r05_source_data" AS "source_data", "public"."alert_records"."r05_dedupe_key" AS "dedupe_key", "public"."alert_records"."r05_scheduled_for" AS "scheduled_for", "public"."alert_records"."r05_delivered_at" AS "delivered_at", "public"."alert_records"."r05_read_at" AS "read_at", "public"."alert_records"."r05_dismissed_at" AS "dismissed_at", "public"."alert_records"."r05_delivery_status" AS "delivery_status", "public"."alert_records"."r05_delivery_error" AS "delivery_error", "public"."alert_records"."r05_delivery_attempt_count" AS "delivery_attempt_count", "public"."alert_records"."r05_delivery_claimed_at" AS "delivery_claimed_at", "public"."alert_records"."r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "public"."alert_records"."r05_delivery_receipts" AS "delivery_receipts", "public"."alert_records"."r05_created_at" AS "created_at") AS "alerts" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r05_account_must_be_active" ON "public"."alert_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.alerts' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r05_id" AS "id", "public"."alert_records"."r05_user_id" AS "user_id", "public"."alert_records"."r05_type" AS "type", "public"."alert_records"."r05_kind" AS "kind", "public"."alert_records"."r05_title" AS "title", "public"."alert_records"."r05_message" AS "message", "public"."alert_records"."r05_budget_id" AS "budget_id", "public"."alert_records"."r05_category_limit_id" AS "category_limit_id", "public"."alert_records"."r05_savings_goal_id" AS "savings_goal_id", "public"."alert_records"."r05_reminder_id" AS "reminder_id", "public"."alert_records"."r05_source_data" AS "source_data", "public"."alert_records"."r05_dedupe_key" AS "dedupe_key", "public"."alert_records"."r05_scheduled_for" AS "scheduled_for", "public"."alert_records"."r05_delivered_at" AS "delivered_at", "public"."alert_records"."r05_read_at" AS "read_at", "public"."alert_records"."r05_dismissed_at" AS "dismissed_at", "public"."alert_records"."r05_delivery_status" AS "delivery_status", "public"."alert_records"."r05_delivery_error" AS "delivery_error", "public"."alert_records"."r05_delivery_attempt_count" AS "delivery_attempt_count", "public"."alert_records"."r05_delivery_claimed_at" AS "delivery_claimed_at", "public"."alert_records"."r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "public"."alert_records"."r05_delivery_receipts" AS "delivery_receipts", "public"."alert_records"."r05_created_at" AS "created_at") AS "alerts" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.alerts' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r05_id" AS "id", "public"."alert_records"."r05_user_id" AS "user_id", "public"."alert_records"."r05_type" AS "type", "public"."alert_records"."r05_kind" AS "kind", "public"."alert_records"."r05_title" AS "title", "public"."alert_records"."r05_message" AS "message", "public"."alert_records"."r05_budget_id" AS "budget_id", "public"."alert_records"."r05_category_limit_id" AS "category_limit_id", "public"."alert_records"."r05_savings_goal_id" AS "savings_goal_id", "public"."alert_records"."r05_reminder_id" AS "reminder_id", "public"."alert_records"."r05_source_data" AS "source_data", "public"."alert_records"."r05_dedupe_key" AS "dedupe_key", "public"."alert_records"."r05_scheduled_for" AS "scheduled_for", "public"."alert_records"."r05_delivered_at" AS "delivered_at", "public"."alert_records"."r05_read_at" AS "read_at", "public"."alert_records"."r05_dismissed_at" AS "dismissed_at", "public"."alert_records"."r05_delivery_status" AS "delivery_status", "public"."alert_records"."r05_delivery_error" AS "delivery_error", "public"."alert_records"."r05_delivery_attempt_count" AS "delivery_attempt_count", "public"."alert_records"."r05_delivery_claimed_at" AS "delivery_claimed_at", "public"."alert_records"."r05_next_delivery_attempt_at" AS "next_delivery_attempt_at", "public"."alert_records"."r05_delivery_receipts" AS "delivery_receipts", "public"."alert_records"."r05_created_at" AS "created_at") AS "alerts" WHERE (private.is_active_account()))));

CREATE POLICY "r06_Users can create own backups" ON "public"."export_backup_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.backups' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r06_Users can delete own backups" ON "public"."export_backup_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.backups' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r06_Users can read own backups" ON "public"."export_backup_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.backups' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r06_Users can update own backups" ON "public"."export_backup_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.backups' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.backups' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r06_account_must_be_active" ON "public"."export_backup_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.backups' OR EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.backups' OR EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r06_id" AS "id", "public"."export_backup_records"."r06_user_id" AS "user_id", "public"."export_backup_records"."r06_backup_type" AS "backup_type", "public"."export_backup_records"."r06_status" AS "status", "public"."export_backup_records"."r06_file_name" AS "file_name", "public"."export_backup_records"."r06_storage_path" AS "storage_path", "public"."export_backup_records"."r06_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r06_checksum_sha256" AS "checksum_sha256", "public"."export_backup_records"."r06_schema_version" AS "schema_version", "public"."export_backup_records"."r06_last_restore_status" AS "last_restore_status", "public"."export_backup_records"."r06_last_restored_at" AS "last_restored_at", "public"."export_backup_records"."r06_completed_at" AS "completed_at", "public"."export_backup_records"."r06_created_at" AS "created_at", "public"."export_backup_records"."r06_data_counts" AS "data_counts", "public"."export_backup_records"."r06_attachment_count" AS "attachment_count", "public"."export_backup_records"."r06_cleanup_warning" AS "cleanup_warning") AS "backups" WHERE (private.is_active_account()))));

CREATE POLICY "r07_Users can create own category limits" ON "public"."budget_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (EXISTS ( SELECT 1
   FROM public.categories c
  WHERE ((c.id = budgets.category_id) AND (c.type = 'expense'::text) AND ((c.user_id IS NULL) OR (c.user_id = ( SELECT auth.uid() AS uid)))))))))));

CREATE POLICY "r07_Users can delete own category limits" ON "public"."budget_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r07_Users can read own category limits" ON "public"."budget_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r07_Users can update own category limits" ON "public"."budget_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (EXISTS ( SELECT 1
   FROM public.categories c
  WHERE ((c.id = budgets.category_id) AND (c.type = 'expense'::text) AND ((c.user_id IS NULL) OR (c.user_id = ( SELECT auth.uid() AS uid)))))))))));

CREATE POLICY "r07_account_must_be_active" ON "public"."budget_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.budgets' OR EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.budgets' OR EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r07_id" AS "id", "public"."budget_records"."r07_user_id" AS "user_id", "public"."budget_records"."r07_category_id" AS "category_id", "public"."budget_records"."r07_amount" AS "amount", "public"."budget_records"."r07_month" AS "month", "public"."budget_records"."r07_created_at" AS "created_at", "public"."budget_records"."r07_updated_at" AS "updated_at") AS "budgets" WHERE (private.is_active_account()))));

CREATE POLICY "r08_Users can create own custom categories" ON "public"."transaction_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (type = 'expense'::text))))));

CREATE POLICY "r08_Users can delete own custom categories" ON "public"."transaction_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r08_Users can read visible expense categories" ON "public"."transaction_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE (((user_id IS NULL) OR (( SELECT auth.uid() AS uid) = user_id))))));

CREATE POLICY "r08_Users can update own custom categories" ON "public"."transaction_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (type = 'expense'::text))))));

CREATE POLICY "r08_account_must_be_active" ON "public"."transaction_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.categories' OR EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.categories' OR EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r08_id" AS "id", "public"."transaction_records"."r08_name" AS "name", "public"."transaction_records"."r08_type" AS "type", "public"."transaction_records"."r08_icon" AS "icon", "public"."transaction_records"."r08_user_id" AS "user_id", "public"."transaction_records"."r08_color" AS "color", "public"."transaction_records"."r08_icon_image_path" AS "icon_image_path") AS "categories" WHERE (private.is_active_account()))));

CREATE POLICY "r09_Users can read own coaching messages" ON "public"."coaching_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.coaching_messages' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r09_id" AS "id", "public"."coaching_records"."r09_session_id" AS "session_id", "public"."coaching_records"."r09_user_id" AS "user_id", "public"."coaching_records"."r09_role" AS "role", "public"."coaching_records"."r09_content" AS "content", "public"."coaching_records"."r09_reply_to_message_id" AS "reply_to_message_id", "public"."coaching_records"."r09_status" AS "status", "public"."coaching_records"."r09_error_code" AS "error_code", "public"."coaching_records"."r09_model" AS "model", "public"."coaching_records"."r09_prompt_tokens" AS "prompt_tokens", "public"."coaching_records"."r09_completion_tokens" AS "completion_tokens", "public"."coaching_records"."r09_created_at" AS "created_at", "public"."coaching_records"."r09_feedback" AS "feedback", "public"."coaching_records"."r09_ui_payload" AS "ui_payload") AS "coaching_messages" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r09_Users can send own coaching messages" ON "public"."coaching_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind='public.coaching_messages' AND "r09_user_id"=(SELECT auth.uid()) AND "r09_role"='user'));

CREATE POLICY "r09_account_must_be_active" ON "public"."coaching_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.coaching_messages' OR EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r09_id" AS "id", "public"."coaching_records"."r09_session_id" AS "session_id", "public"."coaching_records"."r09_user_id" AS "user_id", "public"."coaching_records"."r09_role" AS "role", "public"."coaching_records"."r09_content" AS "content", "public"."coaching_records"."r09_reply_to_message_id" AS "reply_to_message_id", "public"."coaching_records"."r09_status" AS "status", "public"."coaching_records"."r09_error_code" AS "error_code", "public"."coaching_records"."r09_model" AS "model", "public"."coaching_records"."r09_prompt_tokens" AS "prompt_tokens", "public"."coaching_records"."r09_completion_tokens" AS "completion_tokens", "public"."coaching_records"."r09_created_at" AS "created_at", "public"."coaching_records"."r09_feedback" AS "feedback", "public"."coaching_records"."r09_ui_payload" AS "ui_payload") AS "coaching_messages" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.coaching_messages' OR EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r09_id" AS "id", "public"."coaching_records"."r09_session_id" AS "session_id", "public"."coaching_records"."r09_user_id" AS "user_id", "public"."coaching_records"."r09_role" AS "role", "public"."coaching_records"."r09_content" AS "content", "public"."coaching_records"."r09_reply_to_message_id" AS "reply_to_message_id", "public"."coaching_records"."r09_status" AS "status", "public"."coaching_records"."r09_error_code" AS "error_code", "public"."coaching_records"."r09_model" AS "model", "public"."coaching_records"."r09_prompt_tokens" AS "prompt_tokens", "public"."coaching_records"."r09_completion_tokens" AS "completion_tokens", "public"."coaching_records"."r09_created_at" AS "created_at", "public"."coaching_records"."r09_feedback" AS "feedback", "public"."coaching_records"."r09_ui_payload" AS "ui_payload") AS "coaching_messages" WHERE (private.is_active_account()))));

CREATE POLICY "r10_Users can read own coaching retrievals" ON "public"."coaching_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.coaching_retrievals' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r10_id" AS "id", "public"."coaching_records"."r10_user_id" AS "user_id", "public"."coaching_records"."r10_assistant_message_id" AS "assistant_message_id", "public"."coaching_records"."r10_knowledge_document_id" AS "knowledge_document_id", "public"."coaching_records"."r10_rank" AS "rank", "public"."coaching_records"."r10_similarity" AS "similarity", "public"."coaching_records"."r10_title" AS "title", "public"."coaching_records"."r10_source" AS "source", "public"."coaching_records"."r10_created_at" AS "created_at") AS "coaching_retrievals" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r10_account_must_be_active" ON "public"."coaching_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.coaching_retrievals' OR EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r10_id" AS "id", "public"."coaching_records"."r10_user_id" AS "user_id", "public"."coaching_records"."r10_assistant_message_id" AS "assistant_message_id", "public"."coaching_records"."r10_knowledge_document_id" AS "knowledge_document_id", "public"."coaching_records"."r10_rank" AS "rank", "public"."coaching_records"."r10_similarity" AS "similarity", "public"."coaching_records"."r10_title" AS "title", "public"."coaching_records"."r10_source" AS "source", "public"."coaching_records"."r10_created_at" AS "created_at") AS "coaching_retrievals" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.coaching_retrievals' OR EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r10_id" AS "id", "public"."coaching_records"."r10_user_id" AS "user_id", "public"."coaching_records"."r10_assistant_message_id" AS "assistant_message_id", "public"."coaching_records"."r10_knowledge_document_id" AS "knowledge_document_id", "public"."coaching_records"."r10_rank" AS "rank", "public"."coaching_records"."r10_similarity" AS "similarity", "public"."coaching_records"."r10_title" AS "title", "public"."coaching_records"."r10_source" AS "source", "public"."coaching_records"."r10_created_at" AS "created_at") AS "coaching_retrievals" WHERE (private.is_active_account()))));

CREATE POLICY "r11_Users can create own coaching sessions" ON "public"."coaching_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.coaching_sessions' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r11_Users can delete own coaching sessions" ON "public"."coaching_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.coaching_sessions' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r11_Users can read own coaching sessions" ON "public"."coaching_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.coaching_sessions' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r11_Users can update own coaching sessions" ON "public"."coaching_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.coaching_sessions' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.coaching_sessions' AND EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r11_account_must_be_active" ON "public"."coaching_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.coaching_sessions' OR EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.coaching_sessions' OR EXISTS (SELECT 1 FROM (SELECT "public"."coaching_records"."r11_id" AS "id", "public"."coaching_records"."r11_user_id" AS "user_id", "public"."coaching_records"."r11_title" AS "title", "public"."coaching_records"."r11_created_at" AS "created_at", "public"."coaching_records"."r11_updated_at" AS "updated_at", "public"."coaching_records"."r11_last_message_at" AS "last_message_at") AS "coaching_sessions" WHERE (private.is_active_account()))));

CREATE POLICY "r12_Users can create own data exports" ON "public"."export_backup_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.data_exports' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r12_Users can delete own data exports" ON "public"."export_backup_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.data_exports' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r12_Users can read own data exports" ON "public"."export_backup_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.data_exports' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r12_Users can update own data exports" ON "public"."export_backup_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.data_exports' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.data_exports' AND EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r12_account_must_be_active" ON "public"."export_backup_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.data_exports' OR EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.data_exports' OR EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r12_id" AS "id", "public"."export_backup_records"."r12_user_id" AS "user_id", "public"."export_backup_records"."r12_format" AS "format", "public"."export_backup_records"."r12_status" AS "status", "public"."export_backup_records"."r12_file_name" AS "file_name", "public"."export_backup_records"."r12_file_size_bytes" AS "file_size_bytes", "public"."export_backup_records"."r12_date_from" AS "date_from", "public"."export_backup_records"."r12_date_to" AS "date_to", "public"."export_backup_records"."r12_completed_at" AS "completed_at", "public"."export_backup_records"."r12_created_at" AS "created_at") AS "data_exports" WHERE (private.is_active_account()))));

CREATE POLICY "r13_Users can create own export contents" ON "public"."export_backup_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind='public.export_contents' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r13_Users can delete own export contents" ON "public"."export_backup_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind='public.export_contents' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r13_Users can read own export contents" ON "public"."export_backup_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind='public.export_contents' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r13_Users can update own export contents" ON "public"."export_backup_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind='public.export_contents' AND _owner_id=(SELECT auth.uid()))) WITH CHECK ((_record_kind='public.export_contents' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r13_account_must_be_active" ON "public"."export_backup_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.export_contents' OR EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r13_export_id" AS "export_id", "public"."export_backup_records"."r13_content_type" AS "content_type") AS "export_contents" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.export_contents' OR EXISTS (SELECT 1 FROM (SELECT "public"."export_backup_records"."r13_export_id" AS "export_id", "public"."export_backup_records"."r13_content_type" AS "content_type") AS "export_contents" WHERE (private.is_active_account()))));

CREATE POLICY "r17_Users can create own monthly budgets" ON "public"."budget_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.monthly_budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r17_Users can delete own monthly budgets" ON "public"."budget_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.monthly_budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r17_Users can read own monthly budgets" ON "public"."budget_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.monthly_budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r17_Users can update own monthly budgets" ON "public"."budget_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.monthly_budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.monthly_budgets' AND EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r17_account_must_be_active" ON "public"."budget_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.monthly_budgets' OR EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.monthly_budgets' OR EXISTS (SELECT 1 FROM (SELECT "public"."budget_records"."r17_id" AS "id", "public"."budget_records"."r17_user_id" AS "user_id", "public"."budget_records"."r17_month" AS "month", "public"."budget_records"."r17_limit_amount" AS "limit_amount", "public"."budget_records"."r17_created_at" AS "created_at", "public"."budget_records"."r17_updated_at" AS "updated_at") AS "monthly_budgets" WHERE (private.is_active_account()))));

CREATE POLICY "r18_Users can add own notification preferences" ON "public"."alert_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.notification_preferences' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r18_user_id" AS "user_id", "public"."alert_records"."r18_budget_enabled" AS "budget_enabled", "public"."alert_records"."r18_savings_enabled" AS "savings_enabled", "public"."alert_records"."r18_savings_lead_days" AS "savings_lead_days", "public"."alert_records"."r18_savings_reminder_time" AS "savings_reminder_time", "public"."alert_records"."r18_savings_milestones_enabled" AS "savings_milestones_enabled", "public"."alert_records"."r18_spending_enabled" AS "spending_enabled", "public"."alert_records"."r18_spending_frequency" AS "spending_frequency", "public"."alert_records"."r18_spending_weekday" AS "spending_weekday", "public"."alert_records"."r18_spending_reminder_time" AS "spending_reminder_time", "public"."alert_records"."r18_bills_enabled" AS "bills_enabled", "public"."alert_records"."r18_default_bill_lead_days" AS "default_bill_lead_days", "public"."alert_records"."r18_default_bill_reminder_time" AS "default_bill_reminder_time", "public"."alert_records"."r18_timezone" AS "timezone", "public"."alert_records"."r18_created_at" AS "created_at", "public"."alert_records"."r18_updated_at" AS "updated_at") AS "notification_preferences" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r18_account_must_be_active" ON "public"."alert_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.notification_preferences' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r18_user_id" AS "user_id", "public"."alert_records"."r18_budget_enabled" AS "budget_enabled", "public"."alert_records"."r18_savings_enabled" AS "savings_enabled", "public"."alert_records"."r18_savings_lead_days" AS "savings_lead_days", "public"."alert_records"."r18_savings_reminder_time" AS "savings_reminder_time", "public"."alert_records"."r18_savings_milestones_enabled" AS "savings_milestones_enabled", "public"."alert_records"."r18_spending_enabled" AS "spending_enabled", "public"."alert_records"."r18_spending_frequency" AS "spending_frequency", "public"."alert_records"."r18_spending_weekday" AS "spending_weekday", "public"."alert_records"."r18_spending_reminder_time" AS "spending_reminder_time", "public"."alert_records"."r18_bills_enabled" AS "bills_enabled", "public"."alert_records"."r18_default_bill_lead_days" AS "default_bill_lead_days", "public"."alert_records"."r18_default_bill_reminder_time" AS "default_bill_reminder_time", "public"."alert_records"."r18_timezone" AS "timezone", "public"."alert_records"."r18_created_at" AS "created_at", "public"."alert_records"."r18_updated_at" AS "updated_at") AS "notification_preferences" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.notification_preferences' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r18_user_id" AS "user_id", "public"."alert_records"."r18_budget_enabled" AS "budget_enabled", "public"."alert_records"."r18_savings_enabled" AS "savings_enabled", "public"."alert_records"."r18_savings_lead_days" AS "savings_lead_days", "public"."alert_records"."r18_savings_reminder_time" AS "savings_reminder_time", "public"."alert_records"."r18_savings_milestones_enabled" AS "savings_milestones_enabled", "public"."alert_records"."r18_spending_enabled" AS "spending_enabled", "public"."alert_records"."r18_spending_frequency" AS "spending_frequency", "public"."alert_records"."r18_spending_weekday" AS "spending_weekday", "public"."alert_records"."r18_spending_reminder_time" AS "spending_reminder_time", "public"."alert_records"."r18_bills_enabled" AS "bills_enabled", "public"."alert_records"."r18_default_bill_lead_days" AS "default_bill_lead_days", "public"."alert_records"."r18_default_bill_reminder_time" AS "default_bill_reminder_time", "public"."alert_records"."r18_timezone" AS "timezone", "public"."alert_records"."r18_created_at" AS "created_at", "public"."alert_records"."r18_updated_at" AS "updated_at") AS "notification_preferences" WHERE (private.is_active_account()))));

CREATE POLICY "r18_Users can read own notification preferences" ON "public"."alert_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.notification_preferences' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r18_user_id" AS "user_id", "public"."alert_records"."r18_budget_enabled" AS "budget_enabled", "public"."alert_records"."r18_savings_enabled" AS "savings_enabled", "public"."alert_records"."r18_savings_lead_days" AS "savings_lead_days", "public"."alert_records"."r18_savings_reminder_time" AS "savings_reminder_time", "public"."alert_records"."r18_savings_milestones_enabled" AS "savings_milestones_enabled", "public"."alert_records"."r18_spending_enabled" AS "spending_enabled", "public"."alert_records"."r18_spending_frequency" AS "spending_frequency", "public"."alert_records"."r18_spending_weekday" AS "spending_weekday", "public"."alert_records"."r18_spending_reminder_time" AS "spending_reminder_time", "public"."alert_records"."r18_bills_enabled" AS "bills_enabled", "public"."alert_records"."r18_default_bill_lead_days" AS "default_bill_lead_days", "public"."alert_records"."r18_default_bill_reminder_time" AS "default_bill_reminder_time", "public"."alert_records"."r18_timezone" AS "timezone", "public"."alert_records"."r18_created_at" AS "created_at", "public"."alert_records"."r18_updated_at" AS "updated_at") AS "notification_preferences" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r18_Users can update own notification preferences" ON "public"."alert_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.notification_preferences' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r18_user_id" AS "user_id", "public"."alert_records"."r18_budget_enabled" AS "budget_enabled", "public"."alert_records"."r18_savings_enabled" AS "savings_enabled", "public"."alert_records"."r18_savings_lead_days" AS "savings_lead_days", "public"."alert_records"."r18_savings_reminder_time" AS "savings_reminder_time", "public"."alert_records"."r18_savings_milestones_enabled" AS "savings_milestones_enabled", "public"."alert_records"."r18_spending_enabled" AS "spending_enabled", "public"."alert_records"."r18_spending_frequency" AS "spending_frequency", "public"."alert_records"."r18_spending_weekday" AS "spending_weekday", "public"."alert_records"."r18_spending_reminder_time" AS "spending_reminder_time", "public"."alert_records"."r18_bills_enabled" AS "bills_enabled", "public"."alert_records"."r18_default_bill_lead_days" AS "default_bill_lead_days", "public"."alert_records"."r18_default_bill_reminder_time" AS "default_bill_reminder_time", "public"."alert_records"."r18_timezone" AS "timezone", "public"."alert_records"."r18_created_at" AS "created_at", "public"."alert_records"."r18_updated_at" AS "updated_at") AS "notification_preferences" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.notification_preferences' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r18_user_id" AS "user_id", "public"."alert_records"."r18_budget_enabled" AS "budget_enabled", "public"."alert_records"."r18_savings_enabled" AS "savings_enabled", "public"."alert_records"."r18_savings_lead_days" AS "savings_lead_days", "public"."alert_records"."r18_savings_reminder_time" AS "savings_reminder_time", "public"."alert_records"."r18_savings_milestones_enabled" AS "savings_milestones_enabled", "public"."alert_records"."r18_spending_enabled" AS "spending_enabled", "public"."alert_records"."r18_spending_frequency" AS "spending_frequency", "public"."alert_records"."r18_spending_weekday" AS "spending_weekday", "public"."alert_records"."r18_spending_reminder_time" AS "spending_reminder_time", "public"."alert_records"."r18_bills_enabled" AS "bills_enabled", "public"."alert_records"."r18_default_bill_lead_days" AS "default_bill_lead_days", "public"."alert_records"."r18_default_bill_reminder_time" AS "default_bill_reminder_time", "public"."alert_records"."r18_timezone" AS "timezone", "public"."alert_records"."r18_created_at" AS "created_at", "public"."alert_records"."r18_updated_at" AS "updated_at") AS "notification_preferences" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r19_Users can add own reminders" ON "public"."alert_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.reminders' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r19_account_must_be_active" ON "public"."alert_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.reminders' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.reminders' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE (private.is_active_account()))));

CREATE POLICY "r19_Users can delete own reminders" ON "public"."alert_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.reminders' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r19_Users can read own reminders" ON "public"."alert_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.reminders' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r19_Users can update own reminders" ON "public"."alert_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.reminders' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.reminders' AND EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r19_id" AS "id", "public"."alert_records"."r19_user_id" AS "user_id", "public"."alert_records"."r19_type" AS "type", "public"."alert_records"."r19_title" AS "title", "public"."alert_records"."r19_amount" AS "amount", "public"."alert_records"."r19_due_at" AS "due_at", "public"."alert_records"."r19_lead_days" AS "lead_days", "public"."alert_records"."r19_recurrence" AS "recurrence", "public"."alert_records"."r19_recurrence_anchor_day" AS "recurrence_anchor_day", "public"."alert_records"."r19_enabled" AS "enabled", "public"."alert_records"."r19_next_trigger_at" AS "next_trigger_at", "public"."alert_records"."r19_last_triggered_at" AS "last_triggered_at", "public"."alert_records"."r19_created_at" AS "created_at", "public"."alert_records"."r19_updated_at" AS "updated_at") AS "reminders" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r20_account_must_be_active" ON "public"."report_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.report_attempts' OR EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r20_attempt_id" AS "attempt_id", "public"."report_records"."r20_user_id" AS "user_id", "public"."report_records"."r20_message_id" AS "message_id", "public"."report_records"."r20_action_id" AS "action_id", "public"."report_records"."r20_storage_path" AS "storage_path", "public"."report_records"."r20_period" AS "period", "public"."report_records"."r20_report_type" AS "report_type", "public"."report_records"."r20_start_date" AS "start_date", "public"."report_records"."r20_end_date" AS "end_date", "public"."report_records"."r20_category_id" AS "category_id", "public"."report_records"."r20_category_name" AS "category_name", "public"."report_records"."r20_arguments" AS "arguments", "public"."report_records"."r20_status" AS "status", "public"."report_records"."r20_report_id" AS "report_id", "public"."report_records"."r20_lease_expires_at" AS "lease_expires_at", "public"."report_records"."r20_lease_owner" AS "lease_owner", "public"."report_records"."r20_lease_renewed_at" AS "lease_renewed_at", "public"."report_records"."r20_lease_renewal_count" AS "lease_renewal_count", "public"."report_records"."r20_created_at" AS "created_at", "public"."report_records"."r20_updated_at" AS "updated_at") AS "report_attempts" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.report_attempts' OR EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r20_attempt_id" AS "attempt_id", "public"."report_records"."r20_user_id" AS "user_id", "public"."report_records"."r20_message_id" AS "message_id", "public"."report_records"."r20_action_id" AS "action_id", "public"."report_records"."r20_storage_path" AS "storage_path", "public"."report_records"."r20_period" AS "period", "public"."report_records"."r20_report_type" AS "report_type", "public"."report_records"."r20_start_date" AS "start_date", "public"."report_records"."r20_end_date" AS "end_date", "public"."report_records"."r20_category_id" AS "category_id", "public"."report_records"."r20_category_name" AS "category_name", "public"."report_records"."r20_arguments" AS "arguments", "public"."report_records"."r20_status" AS "status", "public"."report_records"."r20_report_id" AS "report_id", "public"."report_records"."r20_lease_expires_at" AS "lease_expires_at", "public"."report_records"."r20_lease_owner" AS "lease_owner", "public"."report_records"."r20_lease_renewed_at" AS "lease_renewed_at", "public"."report_records"."r20_lease_renewal_count" AS "lease_renewal_count", "public"."report_records"."r20_created_at" AS "created_at", "public"."report_records"."r20_updated_at" AS "updated_at") AS "report_attempts" WHERE (private.is_active_account()))));

CREATE POLICY "r20_Users can read own report attempts" ON "public"."report_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.report_attempts' AND EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r20_attempt_id" AS "attempt_id", "public"."report_records"."r20_user_id" AS "user_id", "public"."report_records"."r20_message_id" AS "message_id", "public"."report_records"."r20_action_id" AS "action_id", "public"."report_records"."r20_storage_path" AS "storage_path", "public"."report_records"."r20_period" AS "period", "public"."report_records"."r20_report_type" AS "report_type", "public"."report_records"."r20_start_date" AS "start_date", "public"."report_records"."r20_end_date" AS "end_date", "public"."report_records"."r20_category_id" AS "category_id", "public"."report_records"."r20_category_name" AS "category_name", "public"."report_records"."r20_arguments" AS "arguments", "public"."report_records"."r20_status" AS "status", "public"."report_records"."r20_report_id" AS "report_id", "public"."report_records"."r20_lease_expires_at" AS "lease_expires_at", "public"."report_records"."r20_lease_owner" AS "lease_owner", "public"."report_records"."r20_lease_renewed_at" AS "lease_renewed_at", "public"."report_records"."r20_lease_renewal_count" AS "lease_renewal_count", "public"."report_records"."r20_created_at" AS "created_at", "public"."report_records"."r20_updated_at" AS "updated_at") AS "report_attempts" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r21_Users can create own reports" ON "public"."report_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.reports' AND EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r21_id" AS "id", "public"."report_records"."r21_user_id" AS "user_id", "public"."report_records"."r21_period" AS "period", "public"."report_records"."r21_type" AS "type", "public"."report_records"."r21_generated_at" AS "generated_at", "public"."report_records"."r21_title" AS "title", "public"."report_records"."r21_file_name" AS "file_name", "public"."report_records"."r21_storage_path" AS "storage_path", "public"."report_records"."r21_report_key" AS "report_key", "public"."report_records"."r21_start_date" AS "start_date", "public"."report_records"."r21_end_date" AS "end_date", "public"."report_records"."r21_category_id" AS "category_id") AS "reports" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (COALESCE(report_key, ''::text) !~~ 'coach:%'::text) AND (COALESCE((storage.foldername(storage_path))[2], ''::text) <> 'coach'::text))))));

CREATE POLICY "r21_account_must_be_active" ON "public"."report_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.reports' OR EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r21_id" AS "id", "public"."report_records"."r21_user_id" AS "user_id", "public"."report_records"."r21_period" AS "period", "public"."report_records"."r21_type" AS "type", "public"."report_records"."r21_generated_at" AS "generated_at", "public"."report_records"."r21_title" AS "title", "public"."report_records"."r21_file_name" AS "file_name", "public"."report_records"."r21_storage_path" AS "storage_path", "public"."report_records"."r21_report_key" AS "report_key", "public"."report_records"."r21_start_date" AS "start_date", "public"."report_records"."r21_end_date" AS "end_date", "public"."report_records"."r21_category_id" AS "category_id") AS "reports" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.reports' OR EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r21_id" AS "id", "public"."report_records"."r21_user_id" AS "user_id", "public"."report_records"."r21_period" AS "period", "public"."report_records"."r21_type" AS "type", "public"."report_records"."r21_generated_at" AS "generated_at", "public"."report_records"."r21_title" AS "title", "public"."report_records"."r21_file_name" AS "file_name", "public"."report_records"."r21_storage_path" AS "storage_path", "public"."report_records"."r21_report_key" AS "report_key", "public"."report_records"."r21_start_date" AS "start_date", "public"."report_records"."r21_end_date" AS "end_date", "public"."report_records"."r21_category_id" AS "category_id") AS "reports" WHERE (private.is_active_account()))));

CREATE POLICY "r21_Users can read own reports" ON "public"."report_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.reports' AND EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r21_id" AS "id", "public"."report_records"."r21_user_id" AS "user_id", "public"."report_records"."r21_period" AS "period", "public"."report_records"."r21_type" AS "type", "public"."report_records"."r21_generated_at" AS "generated_at", "public"."report_records"."r21_title" AS "title", "public"."report_records"."r21_file_name" AS "file_name", "public"."report_records"."r21_storage_path" AS "storage_path", "public"."report_records"."r21_report_key" AS "report_key", "public"."report_records"."r21_start_date" AS "start_date", "public"."report_records"."r21_end_date" AS "end_date", "public"."report_records"."r21_category_id" AS "category_id") AS "reports" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r21_Users can update own reports" ON "public"."report_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.reports' AND EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r21_id" AS "id", "public"."report_records"."r21_user_id" AS "user_id", "public"."report_records"."r21_period" AS "period", "public"."report_records"."r21_type" AS "type", "public"."report_records"."r21_generated_at" AS "generated_at", "public"."report_records"."r21_title" AS "title", "public"."report_records"."r21_file_name" AS "file_name", "public"."report_records"."r21_storage_path" AS "storage_path", "public"."report_records"."r21_report_key" AS "report_key", "public"."report_records"."r21_start_date" AS "start_date", "public"."report_records"."r21_end_date" AS "end_date", "public"."report_records"."r21_category_id" AS "category_id") AS "reports" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (COALESCE(report_key, ''::text) !~~ 'coach:%'::text)))))) WITH CHECK ((_record_kind = 'public.reports' AND EXISTS (SELECT 1 FROM (SELECT "public"."report_records"."r21_id" AS "id", "public"."report_records"."r21_user_id" AS "user_id", "public"."report_records"."r21_period" AS "period", "public"."report_records"."r21_type" AS "type", "public"."report_records"."r21_generated_at" AS "generated_at", "public"."report_records"."r21_title" AS "title", "public"."report_records"."r21_file_name" AS "file_name", "public"."report_records"."r21_storage_path" AS "storage_path", "public"."report_records"."r21_report_key" AS "report_key", "public"."report_records"."r21_start_date" AS "start_date", "public"."report_records"."r21_end_date" AS "end_date", "public"."report_records"."r21_category_id" AS "category_id") AS "reports" WHERE (((( SELECT auth.uid() AS uid) = user_id) AND (COALESCE(report_key, ''::text) !~~ 'coach:%'::text) AND (COALESCE((storage.foldername(storage_path))[2], ''::text) <> 'coach'::text))))));

CREATE POLICY "r22_Users can add own savings contributions" ON "public"."savings_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind='public.savings_contributions' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r22_Users can delete own savings contributions" ON "public"."savings_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind='public.savings_contributions' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r22_account_must_be_active" ON "public"."savings_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.savings_contributions' OR EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r22_id" AS "id", "public"."savings_records"."r22_goal_id" AS "goal_id", "public"."savings_records"."r22_amount" AS "amount", "public"."savings_records"."r22_contributed_on" AS "contributed_on", "public"."savings_records"."r22_note" AS "note", "public"."savings_records"."r22_created_at" AS "created_at") AS "savings_contributions" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.savings_contributions' OR EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r22_id" AS "id", "public"."savings_records"."r22_goal_id" AS "goal_id", "public"."savings_records"."r22_amount" AS "amount", "public"."savings_records"."r22_contributed_on" AS "contributed_on", "public"."savings_records"."r22_note" AS "note", "public"."savings_records"."r22_created_at" AS "created_at") AS "savings_contributions" WHERE (private.is_active_account()))));

CREATE POLICY "r22_Users can read own savings contributions" ON "public"."savings_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind='public.savings_contributions' AND _owner_id=(SELECT auth.uid())));

CREATE POLICY "r23_Users can add own savings goals" ON "public"."savings_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r23_Users can delete own savings goals" ON "public"."savings_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r23_Users can read own savings goals" ON "public"."savings_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r23_account_must_be_active" ON "public"."savings_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.savings_goals' OR EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.savings_goals' OR EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE (private.is_active_account()))));

CREATE POLICY "r23_Users can update own savings goals" ON "public"."savings_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r23_savings_goals delete own" ON "public"."savings_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((auth.uid() = user_id)))));

CREATE POLICY "r23_savings_goals insert own" ON "public"."savings_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((auth.uid() = user_id)))));

CREATE POLICY "r23_savings_goals select own" ON "public"."savings_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((auth.uid() = user_id)))));

CREATE POLICY "r23_savings_goals update own" ON "public"."savings_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((auth.uid() = user_id))))) WITH CHECK ((_record_kind = 'public.savings_goals' AND EXISTS (SELECT 1 FROM (SELECT "public"."savings_records"."r23_id" AS "id", "public"."savings_records"."r23_user_id" AS "user_id", "public"."savings_records"."r23_name" AS "name", "public"."savings_records"."r23_target_amount" AS "target_amount", "public"."savings_records"."r23_current_amount" AS "current_amount", "public"."savings_records"."r23_created_at" AS "created_at", "public"."savings_records"."r23_updated_at" AS "updated_at", "public"."savings_records"."r23_deadline" AS "deadline") AS "savings_goals" WHERE ((auth.uid() = user_id)))));

CREATE POLICY "r24_Users can add own transactions" ON "public"."transaction_records" AS PERMISSIVE FOR INSERT TO "authenticated" WITH CHECK ((_record_kind = 'public.transactions' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r24_Users can delete own transactions" ON "public"."transaction_records" AS PERMISSIVE FOR DELETE TO "authenticated" USING ((_record_kind = 'public.transactions' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r24_Users can read own transactions" ON "public"."transaction_records" AS PERMISSIVE FOR SELECT TO "authenticated" USING ((_record_kind = 'public.transactions' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r24_account_must_be_active" ON "public"."transaction_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.transactions' OR EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.transactions' OR EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE (private.is_active_account()))));

CREATE POLICY "r24_Users can update own transactions" ON "public"."transaction_records" AS PERMISSIVE FOR UPDATE TO "authenticated" USING ((_record_kind = 'public.transactions' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE ((( SELECT auth.uid() AS uid) = user_id))))) WITH CHECK ((_record_kind = 'public.transactions' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r24_id" AS "id", "public"."transaction_records"."r24_user_id" AS "user_id", "public"."transaction_records"."r24_category_id" AS "category_id", "public"."transaction_records"."r24_amount" AS "amount", "public"."transaction_records"."r24_transaction_date" AS "transaction_date", "public"."transaction_records"."r24_description" AS "description", "public"."transaction_records"."r24_source" AS "source", "public"."transaction_records"."r24_receipt_image_path" AS "receipt_image_path", "public"."transaction_records"."r24_created_at" AS "created_at", "public"."transaction_records"."r24_updated_at" AS "updated_at", "public"."transaction_records"."r24_receipt_items" AS "receipt_items") AS "transactions" WHERE ((( SELECT auth.uid() AS uid) = user_id)))));

CREATE POLICY "r25_account_must_be_active" ON "public"."transaction_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.user_categories' OR EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r25_user_id" AS "user_id", "public"."transaction_records"."r25_category_id" AS "category_id", "public"."transaction_records"."r25_created_at" AS "created_at") AS "user_categories" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.user_categories' OR EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r25_user_id" AS "user_id", "public"."transaction_records"."r25_category_id" AS "category_id", "public"."transaction_records"."r25_created_at" AS "created_at") AS "user_categories" WHERE (private.is_active_account()))));

CREATE POLICY "r25_Users manage own tracked categories" ON "public"."transaction_records" AS PERMISSIVE FOR ALL TO "authenticated" USING ((_record_kind = 'public.user_categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r25_user_id" AS "user_id", "public"."transaction_records"."r25_category_id" AS "category_id", "public"."transaction_records"."r25_created_at" AS "created_at") AS "user_categories" WHERE ((auth.uid() = user_id))))) WITH CHECK ((_record_kind = 'public.user_categories' AND EXISTS (SELECT 1 FROM (SELECT "public"."transaction_records"."r25_user_id" AS "user_id", "public"."transaction_records"."r25_category_id" AS "category_id", "public"."transaction_records"."r25_created_at" AS "created_at") AS "user_categories" WHERE ((auth.uid() = user_id)))));

CREATE POLICY "r26_account_must_be_active" ON "public"."alert_records" AS RESTRICTIVE FOR ALL TO "authenticated" USING ((_record_kind <> 'public.user_devices' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r26_id" AS "id", "public"."alert_records"."r26_user_id" AS "user_id", "public"."alert_records"."r26_expo_push_token" AS "expo_push_token", "public"."alert_records"."r26_platform" AS "platform", "public"."alert_records"."r26_device_name" AS "device_name", "public"."alert_records"."r26_active" AS "active", "public"."alert_records"."r26_last_seen_at" AS "last_seen_at", "public"."alert_records"."r26_last_error" AS "last_error", "public"."alert_records"."r26_created_at" AS "created_at", "public"."alert_records"."r26_updated_at" AS "updated_at") AS "user_devices" WHERE (private.is_active_account())))) WITH CHECK ((_record_kind <> 'public.user_devices' OR EXISTS (SELECT 1 FROM (SELECT "public"."alert_records"."r26_id" AS "id", "public"."alert_records"."r26_user_id" AS "user_id", "public"."alert_records"."r26_expo_push_token" AS "expo_push_token", "public"."alert_records"."r26_platform" AS "platform", "public"."alert_records"."r26_device_name" AS "device_name", "public"."alert_records"."r26_active" AS "active", "public"."alert_records"."r26_last_seen_at" AS "last_seen_at", "public"."alert_records"."r26_last_error" AS "last_error", "public"."alert_records"."r26_created_at" AS "created_at", "public"."alert_records"."r26_updated_at" AS "updated_at") AS "user_devices" WHERE (private.is_active_account()))));

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

REVOKE ALL ON FUNCTION private.trial_r05_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER deliver_inserted_alert AFTER INSERT ON "public"."alert_records" FOR EACH ROW WHEN (NEW."r05_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r05_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r07_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER validate_category_budget_allocations BEFORE INSERT OR UPDATE OF "r07_user_id", "r07_month", "r07_amount" ON "public"."budget_records" FOR EACH ROW WHEN (NEW."r07_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r07_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r11_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER coaching_sessions_set_updated_at BEFORE UPDATE ON "public"."coaching_records" FOR EACH ROW WHEN (NEW."r11_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r11_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r16_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER fincoach_knowledge_publication AFTER UPDATE OF "r16_published_revision_id", "r16_archived" ON "public"."knowledge_records" FOR EACH ROW WHEN (NEW."r16_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r16_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r17_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER validate_monthly_budget_allocations BEFORE INSERT OR UPDATE OF "r17_user_id", "r17_month", "r17_limit_amount" ON "public"."budget_records" FOR EACH ROW WHEN (NEW."r17_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r17_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r18_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER notification_preferences_set_updated_at BEFORE UPDATE ON "public"."alert_records" FOR EACH ROW WHEN (NEW."r18_user_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r18_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r19_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER reminders_refresh_schedule BEFORE INSERT OR UPDATE OF "r19_title", "r19_due_at", "r19_lead_days", "r19_recurrence_anchor_day", "r19_enabled" ON "public"."alert_records" FOR EACH ROW WHEN (NEW."r19_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r19_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r19_trigger_1() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER reminders_set_updated_at BEFORE UPDATE ON "public"."alert_records" FOR EACH ROW WHEN (NEW."r19_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r19_trigger_1();

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

REVOKE ALL ON FUNCTION private.trial_r22_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER refresh_savings_goal_amount AFTER INSERT OR DELETE ON "public"."savings_records" FOR EACH ROW EXECUTE FUNCTION private.trial_r22_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r24_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER validate_transaction_category BEFORE INSERT OR UPDATE OF "r24_user_id", "r24_category_id", "r24_source", "r24_description" ON "public"."transaction_records" FOR EACH ROW WHEN (NEW."r24_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r24_trigger_0();

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

REVOKE ALL ON FUNCTION private.trial_r26_trigger_0() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER user_devices_set_updated_at BEFORE UPDATE ON "public"."alert_records" FOR EACH ROW WHEN (NEW."r26_id" IS NOT NULL) EXECUTE FUNCTION private.trial_r26_trigger_0();

REVOKE ALL ON TABLE "private"."coaching_processing_leases" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "private"."financial_backup_snapshots" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."account_access" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."admin_audit_logs" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."alerts" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."backups" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."budgets" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."categories" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."coaching_messages" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."coaching_retrievals" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."coaching_sessions" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."data_exports" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."export_contents" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."knowledge_documents" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."knowledge_revisions" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."knowledge_sources" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."monthly_budgets" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."notification_preferences" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."profiles" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."reminders" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."report_attempts" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."reports" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."savings_contributions" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."savings_goals" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."transactions" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."user_categories" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON TABLE "public"."user_devices" FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.handle_new_user_profile() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.is_active_account() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.notify_inserted_alert() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.refresh_reminder_schedule() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.refresh_savings_goal_amount() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.require_admin(uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.restore_financial_backup_v1(jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.set_updated_at() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.sync_account_access() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.sync_knowledge_publication() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.sync_profile_account_name() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.valid_receipt_items(jsonb) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.validate_budget_allocations() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.validate_financial_backup_data(jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION private.validate_transaction_category() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_claim_knowledge_revision() FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_fail_knowledge_revision(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_finish_knowledge_revision(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_knowledge_action(uuid,uuid,uuid,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.deactivate_user_device(uuid,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_recoverable_alerts(timestamp with time zone,integer) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_renew_knowledge_lease(uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_save_knowledge_revision(uuid,uuid,text,text,jsonb,date,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.admin_set_account_status(uuid,uuid,text,text,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.auth_methods_for_email(text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.begin_financial_backup_delete_v2(uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.claim_alert_delivery(uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.complete_coaching_turn_leased(uuid,uuid,uuid,jsonb,jsonb,text,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.claim_bill_reminder_occurrence(uuid,timestamp with time zone,timestamp with time zone,text,text,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.claim_coach_report_attempt(uuid,uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.claim_coaching_message(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.complete_coach_report_attempt(uuid,uuid,uuid,uuid,boolean,jsonb,jsonb) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.complete_coaching_turn(uuid,uuid,uuid,jsonb,jsonb,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.complete_financial_backup_v2(uuid,jsonb,text,bigint,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.fail_coaching_message(uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.financial_backup_snapshot_v2(uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.list_abandoned_coach_report_artifacts(timestamp with time zone,uuid,uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.match_knowledge_documents(public.vector,integer) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.match_knowledge_documents_hybrid(text,public.vector,integer) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.reassign_user_device(uuid,text,text,text) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.renew_report_attempt(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.replace_tracked_categories(uuid,bigint[]) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.restore_financial_backup_v1(jsonb,uuid) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.restore_financial_backup_v2(jsonb,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;

REVOKE ALL ON FUNCTION public.save_budget_month(uuid,date,numeric,jsonb) FROM PUBLIC,anon,authenticated,service_role;

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

GRANT SELECT ("r05_id", "r05_user_id", "r05_type", "r05_kind", "r05_title", "r05_message", "r05_budget_id", "r05_category_limit_id", "r05_savings_goal_id", "r05_reminder_id", "r05_source_data", "r05_dedupe_key", "r05_scheduled_for", "r05_delivered_at", "r05_read_at", "r05_dismissed_at", "r05_delivery_status", "r05_delivery_error", "r05_delivery_attempt_count", "r05_delivery_claimed_at", "r05_next_delivery_attempt_at", "r05_delivery_receipts", "r05_created_at") ON "public"."alert_records" TO "authenticated";

GRANT INSERT ("r05_id", "r05_user_id", "r05_type", "r05_kind", "r05_title", "r05_message", "r05_budget_id", "r05_category_limit_id", "r05_savings_goal_id", "r05_reminder_id", "r05_source_data", "r05_dedupe_key", "r05_scheduled_for", "r05_delivered_at", "r05_read_at", "r05_dismissed_at", "r05_delivery_status", "r05_delivery_error", "r05_delivery_attempt_count", "r05_delivery_claimed_at", "r05_next_delivery_attempt_at", "r05_delivery_receipts", "r05_created_at") ON "public"."alert_records" TO "authenticated";

GRANT DELETE ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT ALL ON TABLE "public"."alerts" TO "service_role";

GRANT INSERT("user_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_user_id") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("type") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_type") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("kind") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_kind") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("title") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_title") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("message") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_message") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("budget_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_budget_id") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("category_limit_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_category_limit_id") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("savings_goal_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_savings_goal_id") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("reminder_id") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_reminder_id") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("source_data") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_source_data") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("dedupe_key") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_dedupe_key") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT INSERT("scheduled_for") ON TABLE "public"."alerts" TO "authenticated";

GRANT INSERT ("r05_scheduled_for") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT UPDATE("read_at") ON TABLE "public"."alerts" TO "authenticated";

GRANT UPDATE ("r05_read_at") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT UPDATE("dismissed_at") ON TABLE "public"."alerts" TO "authenticated";

GRANT UPDATE ("r05_dismissed_at") ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

REVOKE ALL ON FUNCTION "public"."claim_alert_delivery"("p_alert_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_alert_delivery"("p_alert_id" "uuid") TO "service_role";

REVOKE ALL ON FUNCTION "public"."claim_bill_reminder_occurrence"("p_reminder_id" "uuid", "p_expected_trigger_at" timestamp with time zone, "p_next_due_at" timestamp with time zone, "p_title" "text", "p_message" "text", "p_dedupe_key" "text") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_bill_reminder_occurrence"("p_reminder_id" "uuid", "p_expected_trigger_at" timestamp with time zone, "p_next_due_at" timestamp with time zone, "p_title" "text", "p_message" "text", "p_dedupe_key" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."claim_coach_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid", "p_attempt_id" "uuid") FROM PUBLIC;

GRANT ALL ON FUNCTION "public"."claim_coach_report_attempt"("p_user_id" "uuid", "p_message_id" "uuid", "p_action_id" "uuid", "p_attempt_id" "uuid") TO "service_role";

GRANT ALL ON TABLE "public"."coaching_messages" TO "anon";

GRANT SELECT ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") ON "public"."coaching_records" TO "anon";

GRANT INSERT ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") ON "public"."coaching_records" TO "anon";

GRANT UPDATE ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") ON "public"."coaching_records" TO "anon";

GRANT DELETE ON "public"."coaching_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."coaching_records" TO "anon";

GRANT ALL ON TABLE "public"."coaching_messages" TO "authenticated";

GRANT SELECT ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") ON "public"."coaching_records" TO "authenticated";

GRANT INSERT ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") ON "public"."coaching_records" TO "authenticated";

GRANT UPDATE ("r09_id", "r09_session_id", "r09_user_id", "r09_role", "r09_content", "r09_reply_to_message_id", "r09_status", "r09_error_code", "r09_model", "r09_prompt_tokens", "r09_completion_tokens", "r09_created_at", "r09_feedback", "r09_ui_payload") ON "public"."coaching_records" TO "authenticated";

GRANT DELETE ON "public"."coaching_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."coaching_records" TO "authenticated";

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

GRANT SELECT ("r20_attempt_id", "r20_user_id", "r20_message_id", "r20_action_id", "r20_storage_path", "r20_period", "r20_report_type", "r20_start_date", "r20_end_date", "r20_category_id", "r20_category_name", "r20_arguments", "r20_status", "r20_report_id", "r20_lease_expires_at", "r20_lease_owner", "r20_lease_renewed_at", "r20_lease_renewal_count", "r20_created_at", "r20_updated_at") ON "public"."report_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."report_records" TO "authenticated";

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

GRANT SELECT ("r03_user_id") ON "public"."account_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."account_records" TO "authenticated";

GRANT SELECT("role") ON TABLE "public"."account_access" TO "authenticated";

GRANT SELECT ("r03_role") ON "public"."account_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."account_records" TO "authenticated";

GRANT SELECT("status") ON TABLE "public"."account_access" TO "authenticated";

GRANT SELECT ("r03_status") ON "public"."account_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."account_records" TO "authenticated";

GRANT ALL ON TABLE "public"."admin_audit_logs" TO "service_role";

GRANT ALL ON SEQUENCE "public"."admin_audit_logs_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."admin_audit_logs_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."admin_audit_logs_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."backups" TO "authenticated";

GRANT SELECT ("r06_id", "r06_user_id", "r06_backup_type", "r06_status", "r06_file_name", "r06_storage_path", "r06_file_size_bytes", "r06_checksum_sha256", "r06_schema_version", "r06_last_restore_status", "r06_last_restored_at", "r06_completed_at", "r06_created_at", "r06_data_counts", "r06_attachment_count", "r06_cleanup_warning") ON "public"."export_backup_records" TO "authenticated";

GRANT INSERT ("r06_id", "r06_user_id", "r06_backup_type", "r06_status", "r06_file_name", "r06_storage_path", "r06_file_size_bytes", "r06_checksum_sha256", "r06_schema_version", "r06_last_restore_status", "r06_last_restored_at", "r06_completed_at", "r06_created_at", "r06_data_counts", "r06_attachment_count", "r06_cleanup_warning") ON "public"."export_backup_records" TO "authenticated";

GRANT UPDATE ("r06_id", "r06_user_id", "r06_backup_type", "r06_status", "r06_file_name", "r06_storage_path", "r06_file_size_bytes", "r06_checksum_sha256", "r06_schema_version", "r06_last_restore_status", "r06_last_restored_at", "r06_completed_at", "r06_created_at", "r06_data_counts", "r06_attachment_count", "r06_cleanup_warning") ON "public"."export_backup_records" TO "authenticated";

GRANT DELETE ON "public"."export_backup_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."export_backup_records" TO "authenticated";

GRANT ALL ON TABLE "public"."backups" TO "service_role";

GRANT ALL ON TABLE "public"."budgets" TO "anon";

GRANT SELECT ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") ON "public"."budget_records" TO "anon";

GRANT INSERT ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") ON "public"."budget_records" TO "anon";

GRANT UPDATE ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") ON "public"."budget_records" TO "anon";

GRANT DELETE ON "public"."budget_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."budget_records" TO "anon";

GRANT ALL ON TABLE "public"."budgets" TO "authenticated";

GRANT SELECT ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") ON "public"."budget_records" TO "authenticated";

GRANT INSERT ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") ON "public"."budget_records" TO "authenticated";

GRANT UPDATE ("r07_id", "r07_user_id", "r07_category_id", "r07_amount", "r07_month", "r07_created_at", "r07_updated_at") ON "public"."budget_records" TO "authenticated";

GRANT DELETE ON "public"."budget_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."budget_records" TO "authenticated";

GRANT ALL ON TABLE "public"."budgets" TO "service_role";

GRANT ALL ON SEQUENCE "public"."budgets_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."budgets_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."budgets_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."categories" TO "anon";

GRANT SELECT ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") ON "public"."transaction_records" TO "anon";

GRANT INSERT ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") ON "public"."transaction_records" TO "anon";

GRANT UPDATE ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") ON "public"."transaction_records" TO "anon";

GRANT DELETE ON "public"."transaction_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."transaction_records" TO "anon";

GRANT ALL ON TABLE "public"."categories" TO "authenticated";

GRANT SELECT ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") ON "public"."transaction_records" TO "authenticated";

GRANT INSERT ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") ON "public"."transaction_records" TO "authenticated";

GRANT UPDATE ("r08_id", "r08_name", "r08_type", "r08_icon", "r08_user_id", "r08_color", "r08_icon_image_path") ON "public"."transaction_records" TO "authenticated";

GRANT DELETE ON "public"."transaction_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."transaction_records" TO "authenticated";

GRANT ALL ON TABLE "public"."categories" TO "service_role";

GRANT ALL ON SEQUENCE "public"."categories_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."categories_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."categories_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."coaching_retrievals" TO "anon";

GRANT SELECT ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") ON "public"."coaching_records" TO "anon";

GRANT INSERT ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") ON "public"."coaching_records" TO "anon";

GRANT UPDATE ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") ON "public"."coaching_records" TO "anon";

GRANT DELETE ON "public"."coaching_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."coaching_records" TO "anon";

GRANT ALL ON TABLE "public"."coaching_retrievals" TO "authenticated";

GRANT SELECT ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") ON "public"."coaching_records" TO "authenticated";

GRANT INSERT ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") ON "public"."coaching_records" TO "authenticated";

GRANT UPDATE ("r10_id", "r10_user_id", "r10_assistant_message_id", "r10_knowledge_document_id", "r10_rank", "r10_similarity", "r10_title", "r10_source", "r10_created_at") ON "public"."coaching_records" TO "authenticated";

GRANT DELETE ON "public"."coaching_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."coaching_records" TO "authenticated";

GRANT ALL ON TABLE "public"."coaching_retrievals" TO "service_role";

GRANT ALL ON SEQUENCE "public"."coaching_retrievals_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."coaching_retrievals_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."coaching_retrievals_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."coaching_sessions" TO "anon";

GRANT SELECT ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") ON "public"."coaching_records" TO "anon";

GRANT INSERT ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") ON "public"."coaching_records" TO "anon";

GRANT UPDATE ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") ON "public"."coaching_records" TO "anon";

GRANT DELETE ON "public"."coaching_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."coaching_records" TO "anon";

GRANT ALL ON TABLE "public"."coaching_sessions" TO "authenticated";

GRANT SELECT ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") ON "public"."coaching_records" TO "authenticated";

GRANT INSERT ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") ON "public"."coaching_records" TO "authenticated";

GRANT UPDATE ("r11_id", "r11_user_id", "r11_title", "r11_created_at", "r11_updated_at", "r11_last_message_at") ON "public"."coaching_records" TO "authenticated";

GRANT DELETE ON "public"."coaching_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."coaching_records" TO "authenticated";

GRANT ALL ON TABLE "public"."coaching_sessions" TO "service_role";

GRANT ALL ON TABLE "public"."data_exports" TO "authenticated";

GRANT SELECT ("r12_id", "r12_user_id", "r12_format", "r12_status", "r12_file_name", "r12_file_size_bytes", "r12_date_from", "r12_date_to", "r12_completed_at", "r12_created_at") ON "public"."export_backup_records" TO "authenticated";

GRANT INSERT ("r12_id", "r12_user_id", "r12_format", "r12_status", "r12_file_name", "r12_file_size_bytes", "r12_date_from", "r12_date_to", "r12_completed_at", "r12_created_at") ON "public"."export_backup_records" TO "authenticated";

GRANT UPDATE ("r12_id", "r12_user_id", "r12_format", "r12_status", "r12_file_name", "r12_file_size_bytes", "r12_date_from", "r12_date_to", "r12_completed_at", "r12_created_at") ON "public"."export_backup_records" TO "authenticated";

GRANT DELETE ON "public"."export_backup_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."export_backup_records" TO "authenticated";

GRANT ALL ON TABLE "public"."data_exports" TO "service_role";

GRANT ALL ON TABLE "public"."export_contents" TO "authenticated";

GRANT SELECT ("r13_export_id", "r13_content_type") ON "public"."export_backup_records" TO "authenticated";

GRANT INSERT ("r13_export_id", "r13_content_type") ON "public"."export_backup_records" TO "authenticated";

GRANT UPDATE ("r13_export_id", "r13_content_type") ON "public"."export_backup_records" TO "authenticated";

GRANT DELETE ON "public"."export_backup_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."export_backup_records" TO "authenticated";

GRANT ALL ON TABLE "public"."export_contents" TO "service_role";

GRANT ALL ON TABLE "public"."knowledge_documents" TO "service_role";

GRANT ALL ON SEQUENCE "public"."knowledge_documents_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."knowledge_documents_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."knowledge_documents_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."knowledge_revisions" TO "service_role";

GRANT ALL ON TABLE "public"."knowledge_sources" TO "service_role";

GRANT ALL ON TABLE "public"."monthly_budgets" TO "anon";

GRANT SELECT ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") ON "public"."budget_records" TO "anon";

GRANT INSERT ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") ON "public"."budget_records" TO "anon";

GRANT UPDATE ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") ON "public"."budget_records" TO "anon";

GRANT DELETE ON "public"."budget_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."budget_records" TO "anon";

GRANT ALL ON TABLE "public"."monthly_budgets" TO "authenticated";

GRANT SELECT ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") ON "public"."budget_records" TO "authenticated";

GRANT INSERT ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") ON "public"."budget_records" TO "authenticated";

GRANT UPDATE ("r17_id", "r17_user_id", "r17_month", "r17_limit_amount", "r17_created_at", "r17_updated_at") ON "public"."budget_records" TO "authenticated";

GRANT DELETE ON "public"."budget_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."budget_records" TO "authenticated";

GRANT ALL ON TABLE "public"."monthly_budgets" TO "service_role";

GRANT ALL ON TABLE "public"."notification_preferences" TO "authenticated";

GRANT SELECT ("r18_user_id", "r18_budget_enabled", "r18_savings_enabled", "r18_savings_lead_days", "r18_savings_reminder_time", "r18_savings_milestones_enabled", "r18_spending_enabled", "r18_spending_frequency", "r18_spending_weekday", "r18_spending_reminder_time", "r18_bills_enabled", "r18_default_bill_lead_days", "r18_default_bill_reminder_time", "r18_timezone", "r18_created_at", "r18_updated_at") ON "public"."alert_records" TO "authenticated";

GRANT INSERT ("r18_user_id", "r18_budget_enabled", "r18_savings_enabled", "r18_savings_lead_days", "r18_savings_reminder_time", "r18_savings_milestones_enabled", "r18_spending_enabled", "r18_spending_frequency", "r18_spending_weekday", "r18_spending_reminder_time", "r18_bills_enabled", "r18_default_bill_lead_days", "r18_default_bill_reminder_time", "r18_timezone", "r18_created_at", "r18_updated_at") ON "public"."alert_records" TO "authenticated";

GRANT UPDATE ("r18_user_id", "r18_budget_enabled", "r18_savings_enabled", "r18_savings_lead_days", "r18_savings_reminder_time", "r18_savings_milestones_enabled", "r18_spending_enabled", "r18_spending_frequency", "r18_spending_weekday", "r18_spending_reminder_time", "r18_bills_enabled", "r18_default_bill_lead_days", "r18_default_bill_reminder_time", "r18_timezone", "r18_created_at", "r18_updated_at") ON "public"."alert_records" TO "authenticated";

GRANT DELETE ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT ALL ON TABLE "public"."notification_preferences" TO "service_role";

GRANT ALL ON TABLE "public"."profiles" TO "anon";

GRANT ALL ON TABLE "public"."profiles" TO "authenticated";

GRANT ALL ON TABLE "public"."profiles" TO "service_role";

GRANT ALL ON TABLE "public"."published_knowledge_documents" TO "service_role";

GRANT ALL ON TABLE "public"."reminders" TO "authenticated";

GRANT SELECT ("r19_id", "r19_user_id", "r19_type", "r19_title", "r19_amount", "r19_due_at", "r19_lead_days", "r19_recurrence", "r19_recurrence_anchor_day", "r19_enabled", "r19_next_trigger_at", "r19_last_triggered_at", "r19_created_at", "r19_updated_at") ON "public"."alert_records" TO "authenticated";

GRANT INSERT ("r19_id", "r19_user_id", "r19_type", "r19_title", "r19_amount", "r19_due_at", "r19_lead_days", "r19_recurrence", "r19_recurrence_anchor_day", "r19_enabled", "r19_next_trigger_at", "r19_last_triggered_at", "r19_created_at", "r19_updated_at") ON "public"."alert_records" TO "authenticated";

GRANT UPDATE ("r19_id", "r19_user_id", "r19_type", "r19_title", "r19_amount", "r19_due_at", "r19_lead_days", "r19_recurrence", "r19_recurrence_anchor_day", "r19_enabled", "r19_next_trigger_at", "r19_last_triggered_at", "r19_created_at", "r19_updated_at") ON "public"."alert_records" TO "authenticated";

GRANT DELETE ON "public"."alert_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."alert_records" TO "authenticated";

GRANT ALL ON TABLE "public"."reminders" TO "service_role";

GRANT SELECT,INSERT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN,UPDATE ON TABLE "public"."reports" TO "authenticated";

GRANT SELECT ("r21_id", "r21_user_id", "r21_period", "r21_type", "r21_generated_at", "r21_title", "r21_file_name", "r21_storage_path", "r21_report_key", "r21_start_date", "r21_end_date", "r21_category_id") ON "public"."report_records" TO "authenticated";

GRANT INSERT ("r21_id", "r21_user_id", "r21_period", "r21_type", "r21_generated_at", "r21_title", "r21_file_name", "r21_storage_path", "r21_report_key", "r21_start_date", "r21_end_date", "r21_category_id") ON "public"."report_records" TO "authenticated";

GRANT UPDATE ("r21_id", "r21_user_id", "r21_period", "r21_type", "r21_generated_at", "r21_title", "r21_file_name", "r21_storage_path", "r21_report_key", "r21_start_date", "r21_end_date", "r21_category_id") ON "public"."report_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."report_records" TO "authenticated";

GRANT ALL ON TABLE "public"."reports" TO "service_role";

GRANT ALL ON SEQUENCE "public"."reports_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."reports_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."reports_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."savings_contributions" TO "authenticated";

GRANT SELECT ("r22_id", "r22_goal_id", "r22_amount", "r22_contributed_on", "r22_note", "r22_created_at") ON "public"."savings_records" TO "authenticated";

GRANT INSERT ("r22_id", "r22_goal_id", "r22_amount", "r22_contributed_on", "r22_note", "r22_created_at") ON "public"."savings_records" TO "authenticated";

GRANT UPDATE ("r22_id", "r22_goal_id", "r22_amount", "r22_contributed_on", "r22_note", "r22_created_at") ON "public"."savings_records" TO "authenticated";

GRANT DELETE ON "public"."savings_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "authenticated";

GRANT ALL ON TABLE "public"."savings_contributions" TO "service_role";

GRANT ALL ON SEQUENCE "public"."savings_contributions_id_seq" TO "anon";

GRANT ALL ON SEQUENCE "public"."savings_contributions_id_seq" TO "authenticated";

GRANT ALL ON SEQUENCE "public"."savings_contributions_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."savings_goals" TO "anon";

GRANT SELECT ("r23_id", "r23_user_id", "r23_name", "r23_target_amount", "r23_current_amount", "r23_created_at", "r23_updated_at", "r23_deadline") ON "public"."savings_records" TO "anon";

GRANT INSERT ("r23_id", "r23_user_id", "r23_name", "r23_target_amount", "r23_current_amount", "r23_created_at", "r23_updated_at", "r23_deadline") ON "public"."savings_records" TO "anon";

GRANT UPDATE ("r23_id", "r23_user_id", "r23_name", "r23_target_amount", "r23_current_amount", "r23_created_at", "r23_updated_at", "r23_deadline") ON "public"."savings_records" TO "anon";

GRANT DELETE ON "public"."savings_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "anon";

GRANT SELECT,INSERT,REFERENCES,DELETE,TRIGGER,TRUNCATE,MAINTAIN ON TABLE "public"."savings_goals" TO "authenticated";

GRANT SELECT ("r23_id", "r23_user_id", "r23_name", "r23_target_amount", "r23_current_amount", "r23_created_at", "r23_updated_at", "r23_deadline") ON "public"."savings_records" TO "authenticated";

GRANT INSERT ("r23_id", "r23_user_id", "r23_name", "r23_target_amount", "r23_current_amount", "r23_created_at", "r23_updated_at", "r23_deadline") ON "public"."savings_records" TO "authenticated";

GRANT DELETE ON "public"."savings_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "authenticated";

GRANT ALL ON TABLE "public"."savings_goals" TO "service_role";

GRANT UPDATE("name") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE ("r23_name") ON "public"."savings_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "authenticated";

GRANT UPDATE("target_amount") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE ("r23_target_amount") ON "public"."savings_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "authenticated";

GRANT UPDATE("updated_at") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE ("r23_updated_at") ON "public"."savings_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "authenticated";

GRANT UPDATE("deadline") ON TABLE "public"."savings_goals" TO "authenticated";

GRANT UPDATE ("r23_deadline") ON "public"."savings_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."savings_records" TO "authenticated";

GRANT ALL ON TABLE "public"."transactions" TO "authenticated";

GRANT SELECT ("r24_id", "r24_user_id", "r24_category_id", "r24_amount", "r24_transaction_date", "r24_description", "r24_source", "r24_receipt_image_path", "r24_created_at", "r24_updated_at", "r24_receipt_items") ON "public"."transaction_records" TO "authenticated";

GRANT INSERT ("r24_id", "r24_user_id", "r24_category_id", "r24_amount", "r24_transaction_date", "r24_description", "r24_source", "r24_receipt_image_path", "r24_created_at", "r24_updated_at", "r24_receipt_items") ON "public"."transaction_records" TO "authenticated";

GRANT UPDATE ("r24_id", "r24_user_id", "r24_category_id", "r24_amount", "r24_transaction_date", "r24_description", "r24_source", "r24_receipt_image_path", "r24_created_at", "r24_updated_at", "r24_receipt_items") ON "public"."transaction_records" TO "authenticated";

GRANT DELETE ON "public"."transaction_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."transaction_records" TO "authenticated";

GRANT ALL ON TABLE "public"."transactions" TO "service_role";

GRANT ALL ON TABLE "public"."user_categories" TO "anon";

GRANT SELECT ("r25_user_id", "r25_category_id", "r25_created_at") ON "public"."transaction_records" TO "anon";

GRANT INSERT ("r25_user_id", "r25_category_id", "r25_created_at") ON "public"."transaction_records" TO "anon";

GRANT UPDATE ("r25_user_id", "r25_category_id", "r25_created_at") ON "public"."transaction_records" TO "anon";

GRANT DELETE ON "public"."transaction_records" TO "anon";

GRANT SELECT (_record_kind) ON "public"."transaction_records" TO "anon";

GRANT ALL ON TABLE "public"."user_categories" TO "authenticated";

GRANT SELECT ("r25_user_id", "r25_category_id", "r25_created_at") ON "public"."transaction_records" TO "authenticated";

GRANT INSERT ("r25_user_id", "r25_category_id", "r25_created_at") ON "public"."transaction_records" TO "authenticated";

GRANT UPDATE ("r25_user_id", "r25_category_id", "r25_created_at") ON "public"."transaction_records" TO "authenticated";

GRANT DELETE ON "public"."transaction_records" TO "authenticated";

GRANT SELECT (_record_kind) ON "public"."transaction_records" TO "authenticated";

GRANT ALL ON TABLE "public"."user_categories" TO "service_role";

GRANT SELECT ON public."transaction_records" TO authenticated;

GRANT SELECT ON public."budget_records" TO authenticated;

GRANT SELECT ON public."savings_records" TO authenticated;

GRANT SELECT ON public."export_backup_records" TO authenticated;

GRANT SELECT ON public."coaching_records" TO authenticated;

GRANT SELECT ON public."report_records" TO authenticated;

GRANT SELECT ON public."alert_records" TO authenticated;

GRANT SELECT ON public."account_records" TO authenticated;

GRANT EXECUTE ON FUNCTION private.set_updated_at() TO PUBLIC;

GRANT EXECUTE ON FUNCTION private.handle_new_user_profile() TO PUBLIC;

GRANT EXECUTE ON FUNCTION private.refresh_reminder_schedule() TO PUBLIC;

DO $$ BEGIN IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private') AND c.relkind IN ('r','p'))<>10 THEN RAISE EXCEPTION 'Expected exactly 10 physical application tables'; END IF; END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "private"."coaching_processing_leases" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='private.coaching_processing_leases' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: private.coaching_processing_leases'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "private"."financial_backup_snapshots" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='private.financial_backup_snapshots' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: private.financial_backup_snapshots'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."account_access" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.account_access' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.account_access'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."admin_audit_logs" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.admin_audit_logs' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.admin_audit_logs'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."alerts" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.alerts' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.alerts'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."backups" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.backups' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.backups'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."budgets" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.budgets' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.budgets'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."categories" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.categories' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.categories'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."coaching_messages" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.coaching_messages' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.coaching_messages'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."coaching_retrievals" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.coaching_retrievals' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.coaching_retrievals'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."coaching_sessions" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.coaching_sessions' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.coaching_sessions'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."data_exports" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.data_exports' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.data_exports'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."export_contents" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.export_contents' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.export_contents'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."knowledge_documents" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.knowledge_documents' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.knowledge_documents'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."knowledge_revisions" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.knowledge_revisions' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.knowledge_revisions'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."knowledge_sources" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.knowledge_sources' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.knowledge_sources'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."monthly_budgets" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.monthly_budgets' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.monthly_budgets'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."notification_preferences" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.notification_preferences' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.notification_preferences'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."profiles" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.profiles' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.profiles'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."reminders" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.reminders' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.reminders'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."report_attempts" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.report_attempts' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.report_attempts'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."reports" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.reports' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.reports'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."savings_contributions" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.savings_contributions' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.savings_contributions'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."savings_goals" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.savings_goals' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.savings_goals'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."transactions" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.transactions' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.transactions'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."user_categories" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.user_categories' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.user_categories'; END IF;
    END $$;

DO $$ DECLARE actual_count bigint; actual_digest text; BEGIN
      SELECT count(*),md5(coalesce(string_agg(row::text,E'\n' ORDER BY row::text),'')) INTO actual_count,actual_digest FROM (SELECT to_jsonb(t) row FROM "public"."user_devices" t)s;
      IF NOT EXISTS (SELECT 1 FROM trial_expected_rows WHERE name='public.user_devices' AND rows=actual_count AND digest=actual_digest)
      THEN RAISE EXCEPTION 'Row fidelity failure: public.user_devices'; END IF;
    END $$;

NOTIFY pgrst,'reload schema';

COMMIT;
