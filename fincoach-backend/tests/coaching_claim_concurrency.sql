set role service_role;
insert into public.test_concurrent_claims(message_id)
select id from public.claim_coaching_message('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000070',gen_random_uuid(),'00000000-0000-0000-0000-000000000010','Concurrent retry');
