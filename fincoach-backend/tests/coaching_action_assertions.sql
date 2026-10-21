-- Real SQL boundaries for coach confirmations, cancellations, and report completion.
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',false);
create table public.test_action_payloads(id uuid primary key,payload jsonb);
insert into public.test_action_payloads
select ('00000000-0000-0000-0000-' || lpad((1000+n)::text,12,'0'))::uuid,
 jsonb_build_object('type','action','action_type','create_reminder','action_id',('00000000-0000-0000-0000-' || lpad((2000+n)::text,12,'0')),
 'status','pending','arguments',jsonb_build_object('title','Synthetic bill','due_at','2030-01-15T08:00:00+08:00','amount',25,'recurrence','monthly'))
from generate_series(1,4) n;
insert into public.coaching_messages(id,user_id,session_id,role,content)
select ('00000000-0000-0000-0000-'||lpad((3000+n)::text,12,'0'))::uuid,auth.uid(),
 '00000000-0000-0000-0000-000000000010','user','Synthetic action request' from generate_series(1,4) n;
insert into public.coaching_messages(id,user_id,session_id,role,content,ui_payload,reply_to_message_id)
select id,auth.uid(),'00000000-0000-0000-0000-000000000010','assistant','Confirm synthetic test?',payload,
 ('00000000-0000-0000-0000-'||lpad((right(id::text,12)::bigint+2000)::text,12,'0'))::uuid
 from public.test_action_payloads;
grant select on public.test_action_payloads to service_role;
create function public.test_reminder_json(p jsonb) returns jsonb language sql as $$select jsonb_build_object('id',p->>'action_id','user_id','00000000-0000-0000-0000-000000000001',
  'title','Synthetic bill','amount',25,'due_at','2030-01-15T08:00:00+08:00','lead_days',0,'recurrence','monthly','recurrence_anchor_day',15,'next_trigger_at','2030-01-15T08:00:00+08:00')$$;
set role service_role;
do $$declare item record; next jsonb; begin
  select * into item from public.test_action_payloads where id='00000000-0000-0000-0000-000000001001';
  perform public.commit_coach_action('00000000-0000-0000-0000-000000000001',item.id,item.payload,item.payload||'{"status":"cancelled"}',null);
  begin
    next:=item.payload||jsonb_build_object('status','executed','result',jsonb_build_object('reminder_id',item.payload->>'action_id'));
    perform public.commit_coach_action('00000000-0000-0000-0000-000000000001',item.id,item.payload,next,public.test_reminder_json(item.payload));
    raise exception 'stale confirmation accepted';
  exception when raise_exception then if SQLERRM<>'Action state changed. Reload and try again.' then raise;end if;end;
  perform public.test_assert(not exists(select 1 from public.reminders where id=(item.payload->>'action_id')::uuid),'cancel winner has no reminder');
  select * into item from public.test_action_payloads where id='00000000-0000-0000-0000-000000001002';
  next:=item.payload||jsonb_build_object('status','executed','result',jsonb_build_object('reminder_id',item.payload->>'action_id'));
  perform public.commit_coach_action('00000000-0000-0000-0000-000000000001',item.id,item.payload,next,public.test_reminder_json(item.payload));
  begin
    perform public.commit_coach_action('00000000-0000-0000-0000-000000000001',item.id,item.payload,item.payload||'{"status":"cancelled"}',null);
    raise exception 'stale cancellation accepted';
  exception when raise_exception then if SQLERRM<>'Action state changed. Reload and try again.' then raise;end if;end;
  perform public.test_assert((select count(*)=1 from public.reminders where id=(item.payload->>'action_id')::uuid),'confirm winner creates one reminder');
  begin
    perform public.commit_coach_action('00000000-0000-0000-0000-000000000002',item.id,item.payload,next,null);
    raise exception 'cross owner accepted';
  exception when no_data_found then null;end;
end$$;
reset role;
-- Force failure after the effect INSERT but before message commit: neither survives.
create function public.test_reject_action_update() returns trigger language plpgsql as $$begin if new.id='00000000-0000-0000-0000-000000001003' then raise exception 'injected message failure';end if;return new;end$$;
create trigger test_reject_action_update before update on public.coaching_messages for each row execute function public.test_reject_action_update();
set role service_role;
do $$declare item record; begin
 select * into item from public.test_action_payloads where id='00000000-0000-0000-0000-000000001003';
 begin
  perform public.commit_coach_action('00000000-0000-0000-0000-000000000001',item.id,item.payload,
    item.payload||jsonb_build_object('status','executed','result',jsonb_build_object('reminder_id',item.payload->>'action_id')),public.test_reminder_json(item.payload));
  raise exception 'injected failure missing';
 exception when raise_exception then if SQLERRM<>'injected message failure' then raise;end if;end;
 perform public.test_assert(not exists(select 1 from public.reminders where id=(item.payload->>'action_id')::uuid),'failed commit leaves no reminder');
 perform public.test_assert((select ui_payload->>'status'='pending' from public.coaching_messages where id=item.id),'failed commit retains pending action');
end$$;
reset role;
select public.test_assert(not has_function_privilege('authenticated','public.commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb)','execute'),'mobile cannot bypass server action authorization');
-- Report approval/history assertions now exercise the dedicated claim/completion
-- protocol in report_attempt_assertions.sql (the old generic signature is removed).
-- pgbench calls alternate decisions against the same original snapshot.
create function public.test_racing_action(confirm boolean) returns void language plpgsql as $$declare item record; next jsonb; begin
 select * into item from public.test_action_payloads where id='00000000-0000-0000-0000-000000001004';
 next:=case when confirm then item.payload||jsonb_build_object('status','executed','result',jsonb_build_object('reminder_id',item.payload->>'action_id')) else item.payload||'{"status":"cancelled"}' end;
 begin
  perform public.commit_coach_action('00000000-0000-0000-0000-000000000001',item.id,item.payload,next,case when confirm then public.test_reminder_json(item.payload) else null end);
 exception when raise_exception then if SQLERRM<>'Action state changed. Reload and try again.' then raise;end if;end;
end$$;
