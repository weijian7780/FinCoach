import { deliverAlert } from '../_shared/deliver-alerts.ts';
import {
  corsHeaders,
  errorResponse,
  jsonResponse,
  readJsonBody,
  timingSafeEqual,
} from '../_shared/http.ts';
import { createServiceClient } from '../_shared/supabase.ts';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

Deno.serve(async (request) => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (request.method !== 'POST') return errorResponse('Method not allowed.', 405, 'method_not_allowed');

  const suppliedSecret = request.headers.get('x-fincoach-webhook-secret') ?? '';
  const expectedSecret = Deno.env.get('ALERT_WEBHOOK_SECRET') ?? '';
  if (!expectedSecret || !timingSafeEqual(suppliedSecret, expectedSecret)) {
    return errorResponse('Webhook authentication failed.', 401, 'unauthorized');
  }

  const body = await readJsonBody(request);
  const alertId = body?.alertId;
  if (typeof alertId !== 'string' || !UUID_PATTERN.test(alertId)) {
    return errorResponse('A valid alertId is required.', 422, 'invalid_alert_id');
  }

  try {
    const result = await deliverAlert(createServiceClient(), alertId);
    return jsonResponse(result);
  } catch {
    return errorResponse('Alert delivery failed and may be retried.', 500, 'delivery_failed');
  }
});
