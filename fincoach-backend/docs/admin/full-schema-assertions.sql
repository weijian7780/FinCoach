\set ON_ERROR_STOP on
update public.account_access set role='admin' where user_id='00000000-0000-0000-0000-000000000001';
-- Every actual financial table has the additional restrictive active check.
do $$declare t text;begin
 foreach t in array array['profiles','categories','user_categories','monthly_budgets','budgets','savings_goals','savings_contributions','transactions','reports','notification_preferences','reminders','alerts','user_devices','data_exports','export_contents','backups','coaching_sessions','coaching_messages','coaching_retrievals'] loop
  if not exists(select 1 from pg_policies where schemaname='public' and tablename=t and policyname='account_must_be_active' and permissive='RESTRICTIVE') then raise exception 'Missing active policy: %',t;end if;
 end loop;
end$$;
set role authenticated;
set request.jwt.claim.sub='00000000-0000-0000-0000-000000000002';
do $$begin if (select count(*) from public.profiles)<>1 then raise exception 'Profile owner isolation failed';end if;end$$;
reset role;
set role service_role;
select public.admin_set_account_status('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','suspended','full schema test','active');
reset role;
set role authenticated;
do $$begin
 if exists(select 1 from public.profiles) then raise exception 'Suspended profile readable';end if;
 begin perform public.restore_financial_backup_v1('{}',null);raise exception 'Real restore bypassed suspension';exception when insufficient_privilege then null;end;
 begin perform private.restore_financial_backup_v1('{}',null);raise exception 'Original restore directly callable';exception when insufficient_privilege then null;end;
end$$;
reset role;
-- A full suspended batch must not starve the active user's recovery slot.
insert into public.alerts(user_id,type,title,message,dedupe_key,created_at)
select '00000000-0000-0000-0000-000000000002','spending_reminder','Local test','Local test','suspended-'||n,now()-interval '1 day' from generate_series(1,101) n;
insert into public.alerts(user_id,type,title,message,dedupe_key,created_at)
values('00000000-0000-0000-0000-000000000001','spending_reminder','Local active test','Local test','active-test',now()-interval '1 hour');
set role service_role;
do $$declare result jsonb;begin
 result:=public.admin_recoverable_alerts(now(),100);
 if jsonb_array_length(result)<>1 then raise exception 'Suspended recovery starvation';end if;
 if not exists(select 1 from public.alerts where id=(result->0->>'id')::uuid and dedupe_key='active-test') then raise exception 'Wrong recovery owner';end if;
end$$;
reset role;
select 'FULL REPOSITORY SCHEMA ASSERTIONS PASSED' as result;
