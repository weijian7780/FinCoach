export const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers':
    'authorization, x-client-info, apikey, content-type, x-fincoach-webhook-secret, x-fincoach-cron-secret',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

export function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}

export function errorResponse(message: string, status = 400, code = 'request_error'): Response {
  return jsonResponse({ error: { code, message } }, status);
}

export async function readJsonBody(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const value = await request.json();
    return value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function timingSafeEqual(left: string, right: string): boolean {
  const encoder = new TextEncoder();
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  const length = Math.max(leftBytes.length, rightBytes.length);
  let difference = leftBytes.length ^ rightBytes.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (leftBytes[index] ?? 0) ^ (rightBytes[index] ?? 0);
  }
  return difference === 0;
}
