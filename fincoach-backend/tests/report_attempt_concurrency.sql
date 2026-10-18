\set decision random(0,1)
set role service_role;
select public.test_racing_report_attempt(:decision=1,'00000000-0000-0000-0000-000000001111',:client_id);
