import { createClient } from 'npm:@supabase/supabase-js@2.108.1';

const clientOptions = {
  auth: { persistSession: false, autoRefreshToken: false },
};

function requiredEnvironment(name: string): string {
  const value = Deno.env.get(name);
  if (!value) throw new Error(`Missing required Edge Function environment: ${name}`);
  return value;
}

export function createCallerClient(authorization: string) {
  return createClient(
    requiredEnvironment('SUPABASE_URL'),
    requiredEnvironment('SUPABASE_ANON_KEY'),
    {
      ...clientOptions,
      global: { headers: { Authorization: authorization } },
    },
  );
}

export function createServiceClient() {
  return createClient(
    requiredEnvironment('SUPABASE_URL'),
    requiredEnvironment('SUPABASE_SERVICE_ROLE_KEY'),
    clientOptions,
  );
}
