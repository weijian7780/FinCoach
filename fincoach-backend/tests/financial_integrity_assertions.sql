-- Tests execute only in a new local disposable database.
insert into auth.users(id,email) values('00000000-0000-0000-0000-000000000001','one@test.invalid'),('00000000-0000-0000-0000-000000000002','two@test.invalid');
create function public.test_assert(ok boolean,label text) returns void language plpgsql as $$begin if ok is distinct from true then raise exception 'ASSERTION: %',label;end if;end$$;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
-- Dedicated shared expense categories avoid relying on seed IDs.
insert into public.categories(id,user_id,name,type,icon,color) overriding system value values(90001,null,'A','expense','restaurant','#000000'),(90002,null,'B','expense','restaurant','#000000');
set role authenticated;
select public.save_budget_month(auth.uid(),'2026-10-01',100,'[{"category_id":90001,"amount":50},{"category_id":90002,"amount":50}]');
select public.save_budget_month(auth.uid(),'2026-10-01',100,'[{"category_id":90001,"amount":60},{"category_id":90002,"amount":40}]');
select public.test_assert((select amount=60 from public.budgets where category_id=90001),'reallocation 60');
select public.test_assert((select amount=40 from public.budgets where category_id=90002),'reallocation 40');
select public.replace_tracked_categories(auth.uid(),array[90001,90002]::bigint[]);
do $$begin
  begin
    perform public.replace_tracked_categories(auth.uid(),array[90001,999999]::bigint[]);
    raise exception 'expected category validation failure';
  exception when raise_exception then
    if SQLERRM <> 'Invalid tracked category' then raise;end if;
  end;
end$$;
select public.test_assert((select count(*)=2 from public.user_categories where user_id=auth.uid()),'tracked categories survive invalid replacement');
-- Force a late failure AFTER prior category changes, proving full transaction rollback.
reset role;
create function public.test_fail_budget() returns trigger language plpgsql as $$begin if new.category_id=90001 and new.amount=70 then raise exception 'injected late failure';end if;return new;end$$;
create trigger test_budget_failure before update on public.budgets for each row execute function public.test_fail_budget();
set role authenticated;
do $$begin
  begin
    perform public.save_budget_month(auth.uid(),'2026-10-01',120,'[{"category_id":90001,"amount":70},{"category_id":90002,"amount":30}]');
    raise exception 'expected injected failure';
  exception when raise_exception then
    if SQLERRM <> 'injected late failure' then raise;end if;
  end;
end$$;
select public.test_assert((select amount=40 from public.budgets where category_id=90002),'earlier category decrease rolled back');
select public.test_assert((select limit_amount=100 from public.monthly_budgets where user_id=auth.uid()),'parent increase rolled back');
do $$begin
  begin
    perform public.save_budget_month('00000000-0000-0000-0000-000000000002','2026-10-01',500,'[]');
    raise exception 'owner bypass';
  exception when insufficient_privilege then null;end;
end$$;
update public.profiles set full_name='Canonical profile' where id=auth.uid();
reset role;
select public.test_assert((select display_name='Canonical profile' from public.account_access where user_id=auth.uid()),'profile name sync');
update auth.users set raw_user_meta_data='{"full_name":"Stale auth name"}',last_sign_in_at=now() where id=auth.uid();
select public.test_assert((select display_name='Canonical profile' from public.account_access where user_id=auth.uid()),'sign in preserves canonical name');
select public.test_assert((select role='student' and status='active' from public.account_access where user_id=auth.uid()),'name sync preserves privileges');

insert into public.coaching_sessions(id,user_id,title) values('00000000-0000-0000-0000-000000000010',auth.uid(),'New conversation');
set role service_role;
select public.test_assert((select count(*)=1 from public.claim_coaching_message('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000020','00000000-0000-0000-0000-000000000030','00000000-0000-0000-0000-000000000010','Help')),'first claim');
select public.test_assert((select count(*)=0 from public.claim_coaching_message('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000020','00000000-0000-0000-0000-000000000031')),'active claim cannot be stolen');
reset role;
update private.coaching_processing_leases set expires_at=now()-interval '1 second';
set role service_role;
select public.test_assert((select count(*)=1 from public.claim_coaching_message('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000020','00000000-0000-0000-0000-000000000031')),'expired claim reclaimed');
select public.test_assert((select count(*)=0 from public.fail_coaching_message('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000020','00000000-0000-0000-0000-000000000030','timeout')),'old worker cannot fail successor');
do $$begin
  begin
    perform public.complete_coaching_turn_leased('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000020','{"id":"00000000-0000-0000-0000-000000000040","content":"Reply"}','[]',null,'00000000-0000-0000-0000-000000000030');
    raise exception 'old worker completed';
  exception when raise_exception then
    if SQLERRM<>'Processing claim expired or was replaced' then raise;end if;
  end;
end$$;
select public.complete_coaching_turn_leased('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000020','{"id":"00000000-0000-0000-0000-000000000040","content":"Reply"}','[]',null,'00000000-0000-0000-0000-000000000031');
select public.test_assert((select count(*)=0 from public.claim_coaching_message('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000020','00000000-0000-0000-0000-000000000032')),'completed reply not regenerated');
reset role;
select public.test_assert((select count(*)=1 from public.coaching_messages where reply_to_message_id='00000000-0000-0000-0000-000000000020'),'exactly one reply');
select public.test_assert(not has_function_privilege('authenticated','public.claim_coaching_message(uuid,uuid,uuid,uuid,text)','execute'),'mobile cannot claim server leases');
