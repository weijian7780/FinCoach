export type ExpoPushMessage = {
  to: string;
  title: string;
  body: string;
  data: { alertId: string; type: string; url: string };
  channelId: string;
  sound: 'default';
  priority: 'high';
};

export type DeviceDeliveryState = 'sent' | 'delivered' | 'retryable' | 'failed';
export type AggregateDeliveryStatus =
  | 'sent'
  | 'delivered'
  | 'retryable'
  | 'failed'
  | 'partially_delivered'
  | 'no_active_device';

type ExpoTicket = {
  status: 'ok' | 'error';
  id?: string;
  message?: string;
  details?: { error?: string };
};

function channelForType(type: string): string {
  if (type.startsWith('budget_')) return 'budget';
  if (type.startsWith('savings_')) return 'savings';
  if (type === 'spending_reminder') return 'spending';
  if (type === 'bill_reminder') return 'bills';
  return 'general';
}

export function buildExpoPushMessage(
  alert: { id: string; type: string; title: string; message: string; route: string },
  expoPushToken: string,
): ExpoPushMessage {
  return {
    to: expoPushToken,
    title: alert.title,
    body: alert.message,
    data: { alertId: alert.id, type: alert.type, url: alert.route },
    channelId: channelForType(alert.type),
    sound: 'default',
    priority: 'high',
  };
}

export function chunkExpoMessages<T>(messages: T[], size = 100): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < messages.length; index += size) {
    chunks.push(messages.slice(index, index + size));
  }
  return chunks;
}

export function classifyExpoError(error: string | undefined): 'permanent' | 'retryable' {
  return ['DeviceNotRegistered', 'MismatchSenderId', 'InvalidCredentials', 'MessageTooBig'].includes(
    error ?? '',
  )
    ? 'permanent'
    : 'retryable';
}

export function mapExpoTicketsToDevices(
  deviceIds: string[],
  tickets: ExpoTicket[],
): Record<
  string,
  | { status: 'sent'; ticketId: string }
  | { status: 'failed' | 'retryable'; error: string; retryable: boolean }
> {
  return Object.fromEntries(
    deviceIds.map((deviceId, index) => {
      const ticket = tickets[index];
      if (ticket?.status === 'ok' && ticket.id) {
        return [deviceId, { status: 'sent' as const, ticketId: ticket.id }];
      }

      const error = ticket?.details?.error ?? 'UnknownExpoError';
      const retryable = classifyExpoError(error) === 'retryable';
      return [
        deviceId,
        {
          status: retryable ? ('retryable' as const) : ('failed' as const),
          error,
          retryable,
        },
      ];
    }),
  );
}

export function nextRetryDelayMilliseconds(attempt: number): number {
  const safeAttempt = Math.max(1, Math.floor(attempt));
  return Math.min(30_000 * 2 ** (safeAttempt - 1), 6 * 60 * 60 * 1000);
}

export function aggregateDeliveryStatus(states: DeviceDeliveryState[]): AggregateDeliveryStatus {
  if (states.length === 0) return 'no_active_device';
  if (states.includes('retryable')) return 'retryable';
  if (states.every((state) => state === 'delivered')) return 'delivered';
  if (states.every((state) => state === 'failed')) return 'failed';
  if (states.includes('delivered') && states.includes('failed')) return 'partially_delivered';
  if (states.includes('sent')) return 'sent';
  return 'partially_delivered';
}
