import { aggregateDeliveryStatus, type DeviceDeliveryState } from './push-domain.ts';


export const PENDING_ALERT_RECOVERY_DELAY_MS = 2 * 60 * 1000;

type LocalDate = { year: number; month: number; day: number };

function localDate(value: string, timeZone: string): LocalDate {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return { year: Number(values.year), month: Number(values.month), day: Number(values.day) };
}

function dateKey(value: LocalDate): string {
  return [
    value.year,
    String(value.month).padStart(2, '0'),
    String(value.day).padStart(2, '0'),
  ].join('-');
}

function addDays(value: LocalDate, days: number): LocalDate {
  const date = new Date(Date.UTC(value.year, value.month - 1, value.day + days));
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() };
}

function weekday(value: LocalDate): number {
  return new Date(Date.UTC(value.year, value.month - 1, value.day)).getUTCDay();
}

function timeZoneOffsetMilliseconds(date: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return (
    Date.UTC(
      Number(values.year),
      Number(values.month) - 1,
      Number(values.day),
      Number(values.hour),
      Number(values.minute),
      Number(values.second),
    ) - date.getTime()
  );
}

function localInstant(value: LocalDate, time: string, timeZone: string): Date | null {
  const match = /^(\d{2}):(\d{2})(?::\d{2})?$/.exec(time);
  if (!match) return null;
  try {
    const representedAsUtc = Date.UTC(
      value.year,
      value.month - 1,
      value.day,
      Number(match[1]),
      Number(match[2]),
    );
    let result = representedAsUtc;
    for (let index = 0; index < 2; index += 1) {
      result = representedAsUtc - timeZoneOffsetMilliseconds(new Date(result), timeZone);
    }
    return new Date(result);
  } catch {
    return null;
  }
}

export function spendingPeriod(
  now: string,
  timeZone: string,
  frequency: 'daily' | 'weekly',
): { startDate: string; endDate: string; periodKey: string } {
  const today = localDate(now, timeZone);
  const start =
    frequency === 'weekly' ? addDays(today, -((weekday(today) + 6) % 7)) : today;
  const end = addDays(start, frequency === 'weekly' ? 7 : 1);
  return { startDate: dateKey(start), endDate: dateKey(end), periodKey: dateKey(start) };
}

export function spendingScheduleIsDue(
  now: string,
  timeZone: string,
  frequency: 'daily' | 'weekly',
  configuredWeekday: number | null,
  reminderTime: string,
): boolean {
  const nowDate = new Date(now);
  if (Number.isNaN(nowDate.getTime())) return false;
  const today = localDate(now, timeZone);
  const scheduleDate =
    frequency === 'daily'
      ? today
      : addDays(
          addDays(today, -((weekday(today) + 6) % 7)),
          (((configuredWeekday ?? 1) + 6) % 7),
        );
  const scheduled = localInstant(scheduleDate, reminderTime, timeZone);
  if (!scheduled) return false;
  const elapsed = nowDate.getTime() - scheduled.getTime();
  return elapsed >= 0 && elapsed <= 36 * 60 * 60 * 1000;
}

export function savingsDeadlineReminderAt(
  deadline: string,
  leadDays: number,
  reminderTime: string,
  timeZone: string,
): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(deadline);
  if (!match || !Number.isInteger(leadDays) || leadDays < 0) return null;
  const reminderDate = addDays(
    { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) },
    -leadDays,
  );
  return localInstant(reminderDate, reminderTime, timeZone)?.toISOString() ?? null;
}

function daysInMonth(year: number, monthIndex: number): number {
  return new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
}

export function advanceRecurrence(
  dueAt: string,
  recurrence: 'none' | 'weekly' | 'monthly' | 'yearly',
  anchorDay: number,
  timeZone = 'Asia/Kuala_Lumpur',
): string | null {
  if (recurrence === 'none') return null;
  const current = new Date(dueAt);
  if (Number.isNaN(current.getTime()) || !Number.isInteger(anchorDay) || anchorDay < 1 || anchorDay > 31) return null;
  const local = localDate(dueAt, timeZone);
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(current).map(part => [part.type, part.value]));
  // Advance the local calendar first; UTC dates differ before 08:00 in Malaysia.
  const rawMonth = local.month - 1 + (recurrence === 'monthly' ? 1 : 0);
  const year = local.year + (recurrence === 'yearly' ? 1 : 0) + Math.floor(rawMonth / 12);
  const month = rawMonth % 12;
  const next = recurrence === 'weekly' ? addDays(local, 7)
    : { year, month: month + 1, day: Math.min(anchorDay, daysInMonth(year, month)) };
  const instant = localInstant(next, `${parts.hour}:${parts.minute}`, timeZone);
  return instant ? new Date(instant.getTime() + current.getUTCSeconds() * 1000 + current.getUTCMilliseconds()).toISOString() : null;
}

export function shouldAttemptAlertDelivery(
  alert: {
    deliveryStatus: string;
    createdAt: string;
    nextDeliveryAttemptAt: string | null;
  },
  now: string,
): boolean {
  const current = Date.parse(now);
  if (!Number.isFinite(current)) return false;

  if (alert.deliveryStatus === 'pending') {
    const createdAt = Date.parse(alert.createdAt);
    return (
      Number.isFinite(createdAt) && createdAt <= current - PENDING_ALERT_RECOVERY_DELAY_MS
    );
  }

  if (alert.deliveryStatus === 'retryable') {
    if (!alert.nextDeliveryAttemptAt) return false;
    const retryAt = Date.parse(alert.nextDeliveryAttemptAt);
    return Number.isFinite(retryAt) && retryAt <= current;
  }

  return false;
}

export function summarizeReceipts(
  receipts: Record<string, { status: DeviceDeliveryState; error?: string }>,
): {
  deliveryStatus: ReturnType<typeof aggregateDeliveryStatus>;
  invalidDeviceIds: string[];
  retryableDeviceIds: string[];
} {
  const entries = Object.entries(receipts);
  return {
    deliveryStatus: aggregateDeliveryStatus(entries.map(([, receipt]) => receipt.status)),
    invalidDeviceIds: entries
      .filter(([, receipt]) => receipt.error === 'DeviceNotRegistered')
      .map(([deviceId]) => deviceId),
    retryableDeviceIds: entries
      .filter(([, receipt]) => receipt.status === 'retryable')
      .map(([deviceId]) => deviceId),
  };
}
