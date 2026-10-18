import type { SupabaseClient } from 'npm:@supabase/supabase-js@2.108.1';

/** Service-role operations bypass RLS, so notifications and device writes must
 * independently check the live account status. Errors fail closed. */
export async function isAccountActive(service: SupabaseClient, userId: string): Promise<boolean> {
  // Enable only after the database migration, alongside FastAPI enforcement.
  if (Deno.env.get('ACCOUNT_ACCESS_ENFORCED') !== 'true') return true;
  const { data, error } = await service.from('account_access').select('status').eq('user_id', userId).maybeSingle();
  if (error) throw error;
  return data?.status === 'active';
}
