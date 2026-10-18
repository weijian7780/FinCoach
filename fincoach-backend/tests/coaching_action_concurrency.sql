\set decision random(0,1)
set role service_role;
select public.test_racing_action(:decision=1);
