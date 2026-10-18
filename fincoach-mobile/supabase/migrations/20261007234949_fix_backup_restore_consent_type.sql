-- Derive the consent value's type from the deployed profile row type.
-- Older projects use text; fresh projects may use the consent enum.
-- Patch the implementation in either schema without changing the account-access
-- wrapper or its existing privileges. Existing financial rows are not modified.
do $repair$
declare
  target regprocedure;
  definition text;
  old_expression text := $old$(profile_data ->> 'spending_records_consent')::public.spending_records_consent$old$;
  new_expression text := $new$(jsonb_populate_record(null::public.profiles,
            jsonb_build_object('spending_records_consent',
              profile_data -> 'spending_records_consent'))).spending_records_consent$new$;
  patched boolean := false;
begin
  for target in
    select p.oid::regprocedure
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('public', 'private')
      and p.proname = 'restore_financial_backup_v1'
      and pg_get_function_identity_arguments(p.oid) = 'payload jsonb, backup_record_id uuid'
  loop
    definition := pg_get_functiondef(target);
    if position(old_expression in definition) > 0 then
      execute replace(definition, old_expression, new_expression);
      patched := true;
    elsif position(new_expression in definition) > 0 then
      patched := true;
    end if;
  end loop;
  if not patched then
    raise exception 'Restore implementation differs from the expected consent expression.';
  end if;
end
$repair$;
