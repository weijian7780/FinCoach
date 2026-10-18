-- Minimal Supabase boundary fixture in an isolated PostgreSQL container.
-- Exercises real roles/RLS/storage/RPC transactions, not hosted Auth or Storage.
do $$begin
 if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin;end if;
 if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin;end if;
 if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls;end if;
end$$;
create schema auth;
create schema storage;
create schema extensions;
create extension vector;
create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}',created_at timestamptz default now(),last_sign_in_at timestamptz);
create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
grant usage on schema auth,storage to authenticated,service_role;
grant execute on function auth.uid() to authenticated,service_role;
create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid default gen_random_uuid(),user_id uuid,name text);
alter table storage.objects enable row level security;
create policy storage_owner on storage.objects for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
grant all on storage.objects to authenticated,service_role;
create table public.transactions(id uuid default gen_random_uuid(),user_id uuid,amount numeric);
alter table public.transactions enable row level security;
create policy transaction_owner on public.transactions for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
grant all on public.transactions to authenticated,service_role;
create function public.restore_financial_backup_v1(payload jsonb,backup_record_id uuid) returns jsonb language plpgsql security definer as $$begin insert into public.transactions(user_id,amount) values(auth.uid(),1);return '{"restored":true}'::jsonb;end$$;
insert into auth.users(id,email) values('00000000-0000-0000-0000-000000000001','admin@test.invalid'),('00000000-0000-0000-0000-000000000002','student@test.invalid'),('00000000-0000-0000-0000-000000000003','other@test.invalid');
insert into public.transactions(user_id,amount) values('00000000-0000-0000-0000-000000000002',10),('00000000-0000-0000-0000-000000000003',20);
insert into storage.objects(user_id,name) values('00000000-0000-0000-0000-000000000002','receipt.png');
