-- Existing RPCs remain available to older workers. These functions use the
-- existing revision view; no tables, columns, or publication rules are changed.
CREATE OR REPLACE FUNCTION public.admin_pick_knowledge_revision_v2()
RETURNS jsonb LANGUAGE sql SET search_path = '' AS $function$
    SELECT pg_catalog.jsonb_build_object(
        'id', r.id,
        'deadline', pg_catalog.clock_timestamp() + interval '60 seconds'
    )
    FROM public.knowledge_revisions AS r
    WHERE r.status = 'queued'
       OR (r.status = 'processing' AND r.lease_until < pg_catalog.clock_timestamp())
    ORDER BY r.created_at, r.id
    LIMIT 1
$function$;

CREATE OR REPLACE FUNCTION public.admin_claim_knowledge_revision_v2(
    p_revision uuid, p_token uuid, p_deadline timestamptz
) RETURNS jsonb LANGUAGE plpgsql SET search_path = '' AS $function$
DECLARE
    r public.knowledge_revisions;
BEGIN
    IF p_revision IS NULL OR p_token IS NULL OR p_deadline IS NULL THEN
        RAISE EXCEPTION 'ADMIN_INVALID';
    END IF;
    -- Serialize retries for this token. Check expiry after the lock in case a
    -- delayed request waited behind another attempt past the ticket deadline.
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_token::text, 0));
    IF p_deadline <= pg_catalog.clock_timestamp() THEN
        RAISE EXCEPTION 'ADMIN_CLAIM_TICKET_EXPIRED';
    END IF;
    IF p_deadline > pg_catalog.clock_timestamp() + interval '90 seconds' THEN
        RAISE EXCEPTION 'ADMIN_INVALID_CLAIM_DEADLINE';
    END IF;

    -- Binding the ticket to one revision prevents a late retry from claiming a
    -- different document even if the original revision has already finished.
    SELECT * INTO r FROM public.knowledge_revisions
      WHERE id = p_revision FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN RETURN NULL; END IF;

    IF r.status = 'processing' AND r.lease_token = p_token
       AND r.lease_until > pg_catalog.clock_timestamp() THEN
        RETURN pg_catalog.to_jsonb(r) || pg_catalog.jsonb_build_object(
            'source_key', (SELECT source_key FROM public.knowledge_sources WHERE id = r.source_id));
    END IF;
    IF r.status = 'processing' AND r.lease_until < pg_catalog.clock_timestamp()
       AND r.attempts >= 3 THEN
        UPDATE public.knowledge_revisions
          SET status = 'failed', error_message = 'Processing retries exhausted.',
              lease_token = NULL, lease_until = NULL
          WHERE id = r.id;
        RETURN NULL;
    END IF;
    IF r.status = 'queued' OR (r.status = 'processing'
       AND r.lease_until < pg_catalog.clock_timestamp() AND r.attempts < 3) THEN
        UPDATE public.knowledge_revisions
          SET status = 'processing', lease_token = p_token,
              lease_until = pg_catalog.clock_timestamp() + interval '10 minutes',
              attempts = attempts + 1
          WHERE id = r.id RETURNING * INTO r;
        RETURN pg_catalog.to_jsonb(r) || pg_catalog.jsonb_build_object(
            'source_key', (SELECT source_key FROM public.knowledge_sources WHERE id = r.source_id));
    END IF;
    RETURN NULL;
END
$function$;

CREATE OR REPLACE FUNCTION public.admin_renew_knowledge_lease_v2(
    p_revision uuid, p_lease uuid
) RETURNS void LANGUAGE plpgsql SET search_path = '' AS $function$
BEGIN
    UPDATE public.knowledge_revisions
      -- Renew only after a completed batch. Preserve the existing lease budget
      -- instead of shortening it based on an unmeasured inference deadline.
      SET lease_until = pg_catalog.clock_timestamp() + interval '10 minutes'
      WHERE id = p_revision AND status = 'processing' AND lease_token = p_lease
        AND lease_until > pg_catalog.clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'ADMIN_CONFLICT'; END IF;
END
$function$;

REVOKE ALL ON FUNCTION public.admin_pick_knowledge_revision_v2() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.admin_claim_knowledge_revision_v2(uuid, uuid, timestamptz)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.admin_renew_knowledge_lease_v2(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_pick_knowledge_revision_v2() TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_claim_knowledge_revision_v2(uuid, uuid, timestamptz) TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_renew_knowledge_lease_v2(uuid, uuid) TO service_role;
-- Make the new function signatures visible to PostgREST after deployment.
NOTIFY pgrst, 'reload schema';
