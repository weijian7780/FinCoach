import type { SupabaseClient } from 'npm:@supabase/supabase-js@2.108.1';
import { isAccountActive } from './account-access.ts';

import {
  aggregateDeliveryStatus,
  buildExpoPushMessage,
  chunkExpoMessages,
  mapExpoTicketsToDevices,
  nextRetryDelayMilliseconds,
  type DeviceDeliveryState,
} from './push-domain.ts';

type DeliveryReceipt = {
  status: DeviceDeliveryState;
  ticketId?: string;
  error?: string;
  retryable?: boolean;
};

type ClaimedAlert = {
  id: string;
  user_id: string;
  type: string;
  title: string;
  message: string;
  budget_id: string | null;
  savings_goal_id: string | null;
  reminder_id: string | null;
  source_data: Record<string, unknown> | null;
  delivery_attempt_count: number;
  delivery_receipts: Record<string, DeliveryReceipt> | null;
};

type RegisteredDevice = {
  id: string;
  expo_push_token: string;
};

function routeForPushAlert(alert: ClaimedAlert): string {
  if (alert.type.startsWith('budget_')) {
    const month = alert.source_data?.month;
    return alert.budget_id && typeof month === 'string'
      ? `/budget?month=${encodeURIComponent(month)}`
      : '/alerts';
  }
  if (alert.type.startsWith('savings_') && alert.savings_goal_id) {
    return `/savings/${alert.savings_goal_id}`;
  }
  if (alert.type === 'bill_reminder' && alert.reminder_id) {
    return `/alerts/reminders/manage?id=${alert.reminder_id}`;
  }
  return alert.type === 'spending_reminder' ? '/transactions/manage' : '/alerts';
}

function normalizeClaimedAlert(data: unknown): ClaimedAlert | null {
  if (Array.isArray(data)) return (data[0] as ClaimedAlert | undefined) ?? null;
  return (data as ClaimedAlert | null) ?? null;
}

function retryableDevice(receipt: DeliveryReceipt | undefined): boolean {
  return !receipt || receipt.status === 'retryable';
}

export async function deliverAlert(
  service: SupabaseClient,
  alertId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<{ status: string; attemptedDevices: number }> {
  // Avoid consuming a delivery attempt while an account is suspended.
  const { data: owner, error: ownerError } = await service.from('alerts').select('user_id').eq('id', alertId).maybeSingle();
  if (ownerError) throw ownerError;
  if (!owner || !await isAccountActive(service, owner.user_id)) return { status: 'skipped', attemptedDevices: 0 };
  const { data: claimData, error: claimError } = await service.rpc('claim_alert_delivery', {
    p_alert_id: alertId,
  });
  if (claimError) throw claimError;

  const alert = normalizeClaimedAlert(claimData);
  if (!alert) return { status: 'skipped', attemptedDevices: 0 };
  if (!await isAccountActive(service, alert.user_id)) {
    // Suspension can race the claim. Release it for recovery after restoration.
    const { error } = await service.from('alerts').update({ delivery_status: 'retryable', delivery_attempt_count: Math.max(0, alert.delivery_attempt_count - 1), next_delivery_attempt_at: new Date(Date.now() + 60000).toISOString(), delivery_error: 'Account suspended.' }).eq('id', alert.id).eq('delivery_status', 'sending');
    if (error) throw error;
    return { status: 'skipped', attemptedDevices: 0 };
  }

  const { data: deviceData, error: deviceError } = await service
    .from('user_devices')
    .select('id,expo_push_token')
    .eq('user_id', alert.user_id)
    .eq('active', true);
  if (deviceError) throw deviceError;

  const devices = (deviceData ?? []) as RegisteredDevice[];
  const receipts: Record<string, DeliveryReceipt> = { ...(alert.delivery_receipts ?? {}) };
  const eligibleDevices = devices.filter((device) => retryableDevice(receipts[device.id]));

  if (devices.length === 0) {
    const { error } = await service
      .from('alerts')
      .update({
        delivery_status: 'no_active_device',
        delivery_error: null,
        next_delivery_attempt_at: null,
      })
      .eq('id', alert.id);
    if (error) throw error;
    return { status: 'no_active_device', attemptedDevices: 0 };
  }

  const prepared = eligibleDevices.map((device) => ({
    deviceId: device.id,
    message: buildExpoPushMessage(
      {
        id: alert.id,
        type: alert.type,
        title: alert.title,
        message: alert.message,
        route: routeForPushAlert(alert),
      },
      device.expo_push_token,
    ),
  }));

  const expoAccessToken = Deno.env.get('EXPO_ACCESS_TOKEN');
  for (const chunk of chunkExpoMessages(prepared)) {
    const response = await fetchImpl('https://exp.host/--/api/v2/push/send', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Accept-Encoding': 'gzip, deflate',
        'Content-Type': 'application/json',
        ...(expoAccessToken ? { Authorization: `Bearer ${expoAccessToken}` } : {}),
      },
      body: JSON.stringify(chunk.map((item) => item.message)),
    });

    let tickets: Array<{
      status: 'ok' | 'error';
      id?: string;
      details?: { error?: string };
    }> = [];
    if (response.ok) {
      const payload = (await response.json()) as { data?: typeof tickets };
      tickets = payload.data ?? [];
    }

    const mapped = mapExpoTicketsToDevices(
      chunk.map((item) => item.deviceId),
      response.ok
        ? tickets
        : chunk.map(() => ({
            status: 'error' as const,
            details: { error: `ExpoHttp${response.status}` },
          })),
    );
    Object.assign(receipts, mapped);
  }

  const permanentlyInvalidDeviceIds = Object.entries(receipts)
    .filter(([, receipt]) => receipt.error === 'DeviceNotRegistered')
    .map(([deviceId]) => deviceId);
  await Promise.all(
    permanentlyInvalidDeviceIds.map((deviceId) =>
      service
        .from('user_devices')
        .update({ active: false, last_error: 'DeviceNotRegistered' })
        .eq('id', deviceId),
    ),
  );

  const states = Object.values(receipts).map((receipt) => receipt.status);
  const deliveryStatus = aggregateDeliveryStatus(states);
  const retryErrors = Object.values(receipts)
    .filter((receipt) => receipt.status === 'retryable')
    .map((receipt) => receipt.error ?? 'TemporaryExpoError');
  const nextRetryAt =
    deliveryStatus === 'retryable'
      ? new Date(
          Date.now() + nextRetryDelayMilliseconds(alert.delivery_attempt_count),
        ).toISOString()
      : null;

  const { error: updateError } = await service
    .from('alerts')
    .update({
      delivery_status: deliveryStatus,
      delivery_receipts: receipts,
      delivery_error: retryErrors.length > 0 ? [...new Set(retryErrors)].join(', ') : null,
      next_delivery_attempt_at: nextRetryAt,
    })
    .eq('id', alert.id);
  if (updateError) throw updateError;

  return { status: deliveryStatus, attemptedDevices: eligibleDevices.length };
}
