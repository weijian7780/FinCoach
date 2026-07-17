import { corsHeaders, errorResponse, jsonResponse, readJsonBody } from '../_shared/http.ts';
import { createCallerClient, createServiceClient } from '../_shared/supabase.ts';

type DeviceAction = 'register' | 'refresh' | 'deactivate';

function validExpoPushToken(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]+\]$/.test(value)
  );
}

Deno.serve(async (request) => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (request.method !== 'POST') return errorResponse('Method not allowed.', 405, 'method_not_allowed');

  const authorization = request.headers.get('Authorization');
  const token = authorization?.replace('Bearer ', '');
  if (!authorization || !token) return errorResponse('Authentication is required.', 401, 'unauthorized');

  const caller = createCallerClient(authorization);
  const { data: authData, error: authError } = await caller.auth.getUser(token);
  if (authError || !authData.user) return errorResponse('Authentication is invalid.', 401, 'unauthorized');

  const body = await readJsonBody(request);
  const action = body?.action as DeviceAction | undefined;
  const expoPushToken = body?.expoPushToken;
  if (!body || !validExpoPushToken(expoPushToken)) {
    return errorResponse('A valid Expo push token is required.', 422, 'invalid_token');
  }
  if (action !== 'register' && action !== 'refresh' && action !== 'deactivate') {
    return errorResponse('A valid device action is required.', 422, 'invalid_action');
  }

  const service = createServiceClient();
  try {
    if (action === 'register') {
      const platform = body.platform;
      const deviceName = typeof body.deviceName === 'string' ? body.deviceName.trim() : null;
      if (platform !== 'android' && platform !== 'ios') {
        return errorResponse('Platform must be android or ios.', 422, 'invalid_platform');
      }
      if (deviceName && deviceName.length > 100) {
        return errorResponse('Device name is too long.', 422, 'invalid_device_name');
      }

      const { data, error } = await service.rpc('reassign_user_device', {
        p_user_id: authData.user.id,
        p_expo_push_token: expoPushToken,
        p_platform: platform,
        p_device_name: deviceName,
      });
      if (error) throw error;
      const row = Array.isArray(data) ? data[0] : data;
      return jsonResponse({ active: true, lastSeenAt: row?.last_seen_at ?? new Date().toISOString() });
    }

    if (action === 'deactivate') {
      const { error } = await service.rpc('deactivate_user_device', {
        p_user_id: authData.user.id,
        p_expo_push_token: expoPushToken,
      });
      if (error) throw error;
      return jsonResponse({ active: false });
    }

    if (action === 'refresh') {
      const lastSeenAt = new Date().toISOString();
      const { data, error } = await service
        .from('user_devices')
        .update({ last_seen_at: lastSeenAt })
        .eq('user_id', authData.user.id)
        .eq('expo_push_token', expoPushToken)
        .eq('active', true)
        .select('active,last_seen_at')
        .maybeSingle();
      if (error) throw error;
      return jsonResponse({
        active: data?.active === true,
        lastSeenAt: data?.last_seen_at ?? lastSeenAt,
      });
    }

    return errorResponse('Unsupported device action.', 422, 'invalid_action');
  } catch {
    return errorResponse('Device registration could not be updated.', 500, 'registration_failed');
  }
});
