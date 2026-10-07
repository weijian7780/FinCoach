-- Supabase infrastructure stand-ins; all FinCoach tables/functions are loaded
-- unchanged from the repository's full schema in this second integration run.
do $$begin
 if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin;end if;
 if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin;end if;
 if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls;end if;
end$$;
create schema auth;create schema storage;create schema extensions;
-- Hosted extension services are not exercised by this local schema test.
create schema vault;
create table vault.decrypted_secrets(name text,decrypted_secret text);
create table auth.users(id uuid primary key,email text,raw_user_meta_data jsonb default '{}',created_at timestamptz default now(),last_sign_in_at timestamptz);
create table auth.identities(user_id uuid,provider text);
create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
grant usage on schema auth,storage to authenticated,service_role;
grant execute on function auth.uid() to authenticated,service_role;
create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,name text);
alter table storage.objects enable row level security;
grant all on storage.objects to authenticated,service_role;
create function storage.foldername(name text) returns text[] language sql immutable as $$select (string_to_array(name,'/'))[1:array_length(string_to_array(name,'/'),1)-1]$$;
