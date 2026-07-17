import type {
  AlertFilter,
  AlertRecord,
  ReminderRecurrence,
} from './types';

export type BudgetThreshold = 'warning' | 'exceeded';

export type BillReminderValidationInput = {
  title: string;
  amount: string;
  dueAt: string;
  leadDays: number;
  recurrence: ReminderRecurrence;
};

export type BillReminderValidationErrors = Partial<
  Record<'title' | 'amount' | 'dueAt' | 'leadDays' | 'recurrence', string>
>;

const DAY_MS = 24 * 60 * 60 * 1000;
const MILESTONES = [25, 50, 75, 100] as const;

export function normalizeReminderTime(value: string): string | null {
  const match = /^([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d(?:\.\d+)?)?$/.exec(value.trim());
  return match ? `${match[1]}:${match[2]}` : null;
}

function toCents(value: number): number {
  return Math.round(value * 100);
}

export function getCrossedBudgetThreshold(
  previousUsed: number,
  currentUsed: number,
  limit: number,
): BudgetThreshold | null {
  const previous = toCents(previousUsed);
  const current = toCents(currentUsed);
  const limitCents = toCents(limit);

  if (limitCents <= 0 || current <= previous) return null;
  if (previous < limitCents && current >= limitCents) return 'exceeded';

  const warningAt = Math.round(limitCents * 0.8);
  if (previous < warningAt && current >= warningAt && current < limitCents) return 'warning';
  return null;
}

export function getCrossedSavingsMilestones(
  previousAmount: number,
  currentAmount: number,
  targetAmount: number,
): number[] {
  const previous = toCents(previousAmount);
  const current = toCents(currentAmount);
  const target = toCents(targetAmount);
  if (target <= 0 || current <= previous) return [];

  return MILESTONES.filter((milestone) => {
    const threshold = Math.round((target * milestone) / 100);
    return previous < threshold && current >= threshold;
  });
}

export function buildBudgetDedupeKey(input: {
  scope: 'overall' | 'category';
  sourceId: string | number;
  month: string;
  threshold: BudgetThreshold;
}): string {
  return `budget:${input.scope}:${input.sourceId}:${input.month}:${input.threshold}`;
}

export function buildSavingsDedupeKey(
  goalId: string,
  event: 'milestone' | 'deadline',
  value: string | number,
): string {
  return `savings:${goalId}:${event}:${value}`;
}

export function buildSpendingPeriodKey(
  frequency: 'daily' | 'weekly',
  periodStart: string,
): string {
  return `spending:${frequency}:${periodStart}`;
}

export function buildBillDedupeKey(reminderId: string, scheduledFor: string): string {
  return `bill:${reminderId}:${scheduledFor}`;
}

function daysInUtcMonth(year: number, monthIndex: number): number {
  return new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
}

export function advanceRecurringDate(
  dueAt: string,
  recurrence: ReminderRecurrence,
  anchorDay?: number,
): string | null {
  if (recurrence === 'none') return null;

  const current = new Date(dueAt);
  if (Number.isNaN(current.getTime())) return null;

  if (recurrence === 'weekly') {
    return new Date(current.getTime() + 7 * DAY_MS).toISOString();
  }

  const targetYear = current.getUTCFullYear() + (recurrence === 'yearly' ? 1 : 0);
  const targetMonth = current.getUTCMonth() + (recurrence === 'monthly' ? 1 : 0);
  const normalizedYear = targetYear + Math.floor(targetMonth / 12);
  const normalizedMonth = ((targetMonth % 12) + 12) % 12;
  const day = Math.min(
    anchorDay ?? current.getUTCDate(),
    daysInUtcMonth(normalizedYear, normalizedMonth),
  );

  return new Date(
    Date.UTC(
      normalizedYear,
      normalizedMonth,
      day,
      current.getUTCHours(),
      current.getUTCMinutes(),
      current.getUTCSeconds(),
      current.getUTCMilliseconds(),
    ),
  ).toISOString();
}

export function calculateNextBillTrigger(dueAt: string, leadDays: number): string | null {
  const due = new Date(dueAt);
  if (Number.isNaN(due.getTime()) || !Number.isInteger(leadDays) || leadDays < 0) return null;
  return new Date(due.getTime() - leadDays * DAY_MS).toISOString();
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
  const representedAsUtc = Date.UTC(
    Number(values.year),
    Number(values.month) - 1,
    Number(values.day),
    Number(values.hour),
    Number(values.minute),
    Number(values.second),
  );
  return representedAsUtc - date.getTime();
}

function zonedDateTimeToUtc(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  timeZone: string,
): Date | null {
  try {
    const localAsUtc = Date.UTC(year, month - 1, day, hour, minute);
    let result = localAsUtc;
    for (let index = 0; index < 2; index += 1) {
      result = localAsUtc - timeZoneOffsetMilliseconds(new Date(result), timeZone);
    }
    return new Date(result);
  } catch {
    return null;
  }
}

export function calculateSavingsReminderAt(
  deadline: string,
  leadDays: number,
  reminderTime: string,
  timeZone: string,
): string | null {
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(deadline);
  const timeMatch = /^(\d{2}):(\d{2})(?::\d{2})?$/.exec(reminderTime);
  if (!dateMatch || !timeMatch || !Number.isInteger(leadDays) || leadDays < 0) return null;

  const localDate = new Date(
    Date.UTC(Number(dateMatch[1]), Number(dateMatch[2]) - 1, Number(dateMatch[3])),
  );
  localDate.setUTCDate(localDate.getUTCDate() - leadDays);
  const utc = zonedDateTimeToUtc(
    localDate.getUTCFullYear(),
    localDate.getUTCMonth() + 1,
    localDate.getUTCDate(),
    Number(timeMatch[1]),
    Number(timeMatch[2]),
    timeZone,
  );
  return utc?.toISOString() ?? null;
}

export function validateBillReminderInput(
  input: BillReminderValidationInput,
  now = new Date().toISOString(),
): BillReminderValidationErrors {
  const errors: BillReminderValidationErrors = {};
  const title = input.title.trim();
  if (!title) errors.title = 'Enter a bill title.';
  else if (title.length > 100) errors.title = 'Bill title must be 100 characters or fewer.';

  const amount = input.amount.trim();
  if (amount && (!/^\d+(?:\.\d{1,2})?$/.test(amount) || Number(amount) <= 0)) {
    errors.amount = 'Enter a valid amount greater than RM 0.';
  }

  const due = new Date(input.dueAt);
  const reference = new Date(now);
  if (Number.isNaN(due.getTime())) {
    errors.dueAt = 'Choose a valid future due date and time.';
  } else if (Number.isNaN(reference.getTime()) || due.getTime() <= reference.getTime()) {
    errors.dueAt = 'Choose a future due date and time.';
  }

  if (!Number.isInteger(input.leadDays) || input.leadDays < 0 || input.leadDays > 365) {
    errors.leadDays = 'Lead time must be between 0 and 365 days.';
  }

  if (!['none', 'weekly', 'monthly', 'yearly'].includes(input.recurrence)) {
    errors.recurrence = 'Choose a valid recurrence.';
  }
  return errors;
}

function zonedDateKey(value: string | Date, timeZone: string): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function previousDateKey(dateKey: string): string {
  const [year, month, day] = dateKey.split('-').map(Number);
  const previous = new Date(Date.UTC(year, month - 1, day - 1));
  return [
    previous.getUTCFullYear(),
    String(previous.getUTCMonth() + 1).padStart(2, '0'),
    String(previous.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

export function groupAlertsByDate(
  alerts: AlertRecord[],
  now = new Date().toISOString(),
  timeZone = 'Asia/Kuala_Lumpur',
): { today: AlertRecord[]; yesterday: AlertRecord[]; earlier: AlertRecord[] } {
  const todayKey = zonedDateKey(now, timeZone);
  const yesterdayKey = previousDateKey(todayKey);
  const groups = { today: [] as AlertRecord[], yesterday: [] as AlertRecord[], earlier: [] as AlertRecord[] };

  for (const item of alerts) {
    const key = zonedDateKey(item.created_at, timeZone);
    if (key === todayKey) groups.today.push(item);
    else if (key === yesterdayKey) groups.yesterday.push(item);
    else groups.earlier.push(item);
  }
  return groups;
}

export function filterAlerts(alerts: AlertRecord[], filter: AlertFilter): AlertRecord[] {
  if (filter === 'all') return alerts;
  const kind = filter === 'insights' ? 'insight' : 'alert';
  return alerts.filter((item) => item.kind === kind);
}

export function routeForAlert(item: AlertRecord): string {
  if (item.type === 'budget_warning' || item.type === 'budget_exceeded') {
    const month = item.source_data.month;
    return item.budget_id && typeof month === 'string'
      ? `/budget?month=${encodeURIComponent(month)}`
      : '/alerts';
  }
  if (
    (item.type === 'savings_deadline' || item.type === 'savings_milestone') &&
    item.savings_goal_id
  ) {
    return `/savings/${item.savings_goal_id}`;
  }
  if (item.type === 'bill_reminder' && item.reminder_id) {
    return `/alerts/reminders/manage?id=${item.reminder_id}`;
  }
  if (item.type === 'spending_reminder') return '/transactions/manage';
  return '/alerts';
}
