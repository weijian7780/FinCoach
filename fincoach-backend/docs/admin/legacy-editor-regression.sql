-- Transactional regression against the installed save function.
-- All fixtures and audit rows roll back inside the exception subtransaction.
DO $regression$
DECLARE
  actor uuid; source_id uuid; original_revision uuid; saved jsonb;
  current_revision uuid; file_source uuid; file_revision uuid; web_source uuid;
BEGIN
  SELECT user_id INTO actor FROM public.account_access
    WHERE role='admin' AND status='active' ORDER BY user_id LIMIT 1;
  IF actor IS NULL THEN RAISE EXCEPTION 'An existing active administrator is required'; END IF;
  BEGIN
    INSERT INTO public.knowledge_sources(source_key,title)
      VALUES ('legacy-editor-regression-'||gen_random_uuid()::text,'Legacy editor regression')
      RETURNING id INTO source_id;
    INSERT INTO public.knowledge_revisions(source_id,title,content,source_urls,status,chunk_count)
      VALUES(source_id,'Existing legacy document','Existing source text.','[]','published',1)
      RETURNING id INTO original_revision;
    UPDATE public.knowledge_sources SET latest_revision_id=original_revision,
      published_revision_id=original_revision WHERE id=source_id;

    -- Existing text without inherited provenance can create an unpublished draft.
    saved:=public.admin_save_knowledge_revision(actor,source_id,'Updated legacy document',
      'Edited existing source text.','[]',NULL,NULL,original_revision);
    current_revision:=(saved->>'revision_id')::uuid;
    IF NOT EXISTS(SELECT 1 FROM public.knowledge_revisions WHERE id=current_revision
      AND status='draft' AND source_urls='[]'::jsonb AND file_path IS NULL)
      OR NOT EXISTS(SELECT 1 FROM public.knowledge_sources WHERE id=source_id
        AND published_revision_id=original_revision AND latest_revision_id=current_revision)
      THEN RAISE EXCEPTION 'Legacy save did not preserve publication and honest missing provenance'; END IF;
    saved:=public.admin_save_knowledge_revision(actor,source_id,'Second legacy draft',
      'Another edit of existing text.','[]',NULL,NULL,current_revision);
    current_revision:=(saved->>'revision_id')::uuid;

    BEGIN
      PERFORM public.admin_save_knowledge_revision(actor,source_id,'Stale update','Body',
        '[]',NULL,NULL,original_revision);
      RAISE EXCEPTION 'Expected ADMIN_CONFLICT';
    EXCEPTION WHEN raise_exception THEN
      IF SQLERRM<>'ADMIN_CONFLICT' THEN RAISE; END IF;
    END;

    BEGIN
      PERFORM public.admin_save_knowledge_revision(actor,NULL,'Missing import','Body',
        '[]',NULL,NULL,NULL);
      RAISE EXCEPTION 'Expected missing-import rejection';
    EXCEPTION WHEN raise_exception THEN
      IF SQLERRM<>'ADMIN_INVALID' THEN RAISE; END IF;
    END;

    saved:=public.admin_save_knowledge_revision(actor,NULL,'Imported webpage','Web content',
      '["https://example.org/financial-guidance"]',NULL,NULL,NULL);
    web_source:=(saved->>'source_id')::uuid;
    BEGIN
      PERFORM public.admin_save_knowledge_revision(actor,web_source,'Dropped link','Edited',
        '[]',NULL,NULL,(saved->>'revision_id')::uuid);
      RAISE EXCEPTION 'Expected existing-source provenance retention';
    EXCEPTION WHEN raise_exception THEN
      IF SQLERRM<>'ADMIN_INVALID' THEN RAISE; END IF;
    END;

    saved:=public.admin_save_knowledge_revision(actor,NULL,'Uploaded file','File content',
      '[]',NULL,actor::text||'/regression/original.md',NULL);
    file_source:=(saved->>'source_id')::uuid;
    file_revision:=(saved->>'revision_id')::uuid;
    saved:=public.admin_save_knowledge_revision(actor,file_source,'Edited file','Edited file content',
      '[]',NULL,NULL,file_revision);
    IF NOT EXISTS(SELECT 1 FROM public.knowledge_revisions WHERE id=(saved->>'revision_id')::uuid
      AND file_path=actor::text||'/regression/original.md')
      THEN RAISE EXCEPTION 'Original file reference was not inherited'; END IF;

    BEGIN
      PERFORM public.admin_save_knowledge_revision(actor,NULL,'Foreign file','Body','[]',
        NULL,gen_random_uuid()::text||'/foreign.md',NULL);
      RAISE EXCEPTION 'Expected foreign-file rejection';
    EXCEPTION WHEN raise_exception THEN
      IF SQLERRM<>'ADMIN_FORBIDDEN' THEN RAISE; END IF;
    END;
    BEGIN
      PERFORM public.admin_save_knowledge_revision(actor,source_id,'Future date','Body','[]',
        (now() AT TIME ZONE 'Asia/Kuala_Lumpur')::date+1,NULL,current_revision);
      RAISE EXCEPTION 'Expected future-date rejection';
    EXCEPTION WHEN raise_exception THEN
      IF SQLERRM<>'ADMIN_INVALID' THEN RAISE; END IF;
    END;
    BEGIN
      PERFORM public.admin_save_knowledge_revision(gen_random_uuid(),source_id,
        'Unauthorised edit','Body','[]',NULL,NULL,current_revision);
      RAISE EXCEPTION 'Expected administrator enforcement';
    EXCEPTION WHEN insufficient_privilege THEN
      IF SQLERRM<>'ADMIN_FORBIDDEN' THEN RAISE; END IF;
    END;
    -- Force rollback even when every assertion passes.
    RAISE SQLSTATE 'P0099' USING MESSAGE='legacy_editor_regression_pass';
  EXCEPTION WHEN SQLSTATE 'P0099' THEN
    IF SQLERRM<>'legacy_editor_regression_pass' THEN RAISE; END IF;
  END;
  RAISE NOTICE 'Legacy editor regression passed; all fixture writes rolled back.';
END $regression$;
