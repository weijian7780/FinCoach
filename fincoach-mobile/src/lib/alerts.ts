import { supabase } from './supabase';
import type {
  AlertRecord,
  AlertWriteInput,
  BillReminder,
  BillReminderWriteInput,
  NotificationPreferences,
  NotificationPreferencesUpdate,
} from './types';

type QueryResult = { data: unknown; error: unknown; count?: number | null };

type AlertQuery = PromiseLike<QueryResult> & {
  delete: () => AlertQuery;
  eq: (column: string, value: unknown) => AlertQuery;
  insert: (value: Record<string, unknown>) => AlertQuery;
  is: (column: string, value: unknown) => AlertQuery;
  limit: (count: number) => AlertQuery;
  maybeSingle: () => Promise<QueryResult>;
  order: (column: string, options: Record<string, unknown>) => AlertQuery;
  select: (columns?: string, options?: Record<string, unknown>) => AlertQuery;
  single: () => Promise<QueryResult>;
  update: (value: Record<string, unknown>) => AlertQuery;
  upsert: (value: Record<string, unknown>, options?: Record<string, unknown>) => AlertQuery;
};

type FunctionResult = { data: unknown; error: unknown };

export type AlertDataClient = {
  from: (table: string) => AlertQuery;
  functions: {
    invoke: (name: string, options: { body: Record<string, unknown> }) => Promise<FunctionResult>;
  };
};

const defaultClient = supabase as unknown as AlertDataClient;

export const DEFAULT_NOTIFICATION_PREFERENCES = {
  budget_enabled: true,
  savings_enabled: true,
  savings_lead_days: 7,
  savings_reminder_time: '09:00',
  savings_milestones_enabled: true,
  spending_enabled: true,
  spending_frequency: 'weekly' as const,
  spending_weekday: 1,
  spending_reminder_time: '20:00',
  bills_enabled: true,
  default_bill_lead_days: 3,
  default_bill_reminder_time: '09:00',
  timezone: 'Asia/Kuala_Lumpur',
};

function throwIfError(error: unknown): void {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string): T {
  if (!data) throw new Error(message);
  return data as T;
}

function reminderPayload(input: BillReminderWriteInput): Record<string, unknown> {
  return {
    type: 'bill',
    title: input.title.trim(),
    amount: input.amount,
    due_at: input.due_at,
    lead_days: input.lead_days,
    recurrence: input.recurrence,
    recurrence_anchor_day: input.recurrence_anchor_day,
    enabled: input.enabled,
  };
}

export async function fetchNotificationPreferences(
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<NotificationPreferences | null> {
  const { data, error } = await client
    .from('notification_preferences')
    .select('*')
    .eq('user_id', userId)
    .maybeSingle();
  throwIfError(error);
  return data as NotificationPreferences | null;
}

export async function ensureNotificationPreferences(
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<NotificationPreferences> {
  const existing = await fetchNotificationPreferences(userId, client);
  if (existing) return existing;

  const { data, error } = await client
    .from('notification_preferences')
    .insert({ user_id: userId, ...DEFAULT_NOTIFICATION_PREFERENCES })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<NotificationPreferences>(
    data,
    'Notification settings were created but no row was returned.',
  );
}

export async function saveNotificationPreferences(
  userId: string,
  updates: NotificationPreferencesUpdate,
  client: AlertDataClient = defaultClient,
): Promise<NotificationPreferences> {
  const { data, error } = await client
    .from('notification_preferences')
    .upsert({ user_id: userId, ...updates }, { onConflict: 'user_id' })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<NotificationPreferences>(
    data,
    'Notification settings were saved but no row was returned.',
  );
}

export async function fetchReminders(
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<BillReminder[]> {
  const { data, error } = await client
    .from('reminders')
    .select('*')
    .eq('user_id', userId)
    .order('next_trigger_at', { ascending: true, nullsFirst: false })
    .order('due_at', { ascending: true });
  throwIfError(error);
  return (data ?? []) as BillReminder[];
}

export async function fetchReminder(
  reminderId: string,
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<BillReminder | null> {
  const { data, error } = await client
    .from('reminders')
    .select('*')
    .eq('id', reminderId)
    .eq('user_id', userId)
    .maybeSingle();
  throwIfError(error);
  return data as BillReminder | null;
}

export async function createReminder(
  userId: string,
  input: BillReminderWriteInput,
  client: AlertDataClient = defaultClient,
): Promise<BillReminder> {
  const { data, error } = await client
    .from('reminders')
    .insert({ user_id: userId, ...reminderPayload(input) })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<BillReminder>(data, 'Reminder was created but no row was returned.');
}

export async function updateReminder(
  reminderId: string,
  userId: string,
  input: BillReminderWriteInput,
  client: AlertDataClient = defaultClient,
): Promise<BillReminder> {
  const { data, error } = await client
    .from('reminders')
    .update(reminderPayload(input))
    .eq('id', reminderId)
    .eq('user_id', userId)
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<BillReminder>(data, 'Reminder was updated but no row was returned.');
}

export async function setReminderEnabled(
  reminderId: string,
  userId: string,
  enabled: boolean,
  client: AlertDataClient = defaultClient,
): Promise<void> {
  const { error } = await client
    .from('reminders')
    .update({ enabled })
    .eq('id', reminderId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function deleteReminder(
  reminderId: string,
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<void> {
  const { error } = await client
    .from('reminders')
    .delete()
    .eq('id', reminderId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function fetchAlerts(
  userId: string,
  client: AlertDataClient = defaultClient,
  limit = 100,
): Promise<AlertRecord[]> {
  const { data, error } = await client
    .from('alerts')
    .select('*')
    .eq('user_id', userId)
    .is('dismissed_at', null)
    .order('created_at', { ascending: false })
    .limit(limit);
  throwIfError(error);
  return (data ?? []) as AlertRecord[];
}

export async function fetchUnreadAlertCount(
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<number> {
  const { count, error } = await client
    .from('alerts')
    .select('id', { count: 'exact', head: true })
    .eq('user_id', userId)
    .is('read_at', null)
    .is('dismissed_at', null);
  throwIfError(error);
  return count ?? 0;
}

export async function markAlertRead(
  alertId: string,
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<void> {
  const { error } = await client
    .from('alerts')
    .update({ read_at: new Date().toISOString() })
    .eq('id', alertId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function markAllAlertsRead(
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<void> {
  const { error } = await client
    .from('alerts')
    .update({ read_at: new Date().toISOString() })
    .eq('user_id', userId)
    .is('read_at', null)
    .is('dismissed_at', null);
  throwIfError(error);
}

export async function dismissAlert(
  alertId: string,
  userId: string,
  client: AlertDataClient = defaultClient,
): Promise<void> {
  const timestamp = new Date().toISOString();
  const { error } = await client
    .from('alerts')
    .update({ read_at: timestamp, dismissed_at: timestamp })
    .eq('id', alertId)
    .eq('user_id', userId);
  throwIfError(error);
}

function isUniqueViolation(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && 'code' in error && error.code === '23505');
}

export async function createIdempotentAlert(
  userId: string,
  input: AlertWriteInput,
  client: AlertDataClient = defaultClient,
): Promise<AlertRecord> {
  const { data, error } = await client
    .from('alerts')
    .insert({ user_id: userId, ...input })
    .select('*')
    .single();

  if (!error) {
    return requireRow<AlertRecord>(data, 'Alert was created but no row was returned.');
  }
  if (!isUniqueViolation(error)) throw error;

  const { data: existing, error: lookupError } = await client
    .from('alerts')
    .select('*')
    .eq('user_id', userId)
    .eq('dedupe_key', input.dedupe_key)
    .maybeSingle();
  throwIfError(lookupError);
  return requireRow<AlertRecord>(existing, 'The existing alert could not be loaded.');
}

type DeviceRegistrationResponse = {
  active: boolean;
  lastSeenAt?: string;
};

async function invokeDeviceAction(
  body: Record<string, unknown>,
  client: AlertDataClient,
): Promise<DeviceRegistrationResponse> {
  const { data, error } = await client.functions.invoke('register-device', { body });
  throwIfError(error);
  return requireRow<DeviceRegistrationResponse>(data, 'Device registration returned no result.');
}

export function registerDevice(
  expoPushToken: string,
  platform: 'android' | 'ios',
  deviceName: string | null,
  client: AlertDataClient = defaultClient,
): Promise<DeviceRegistrationResponse> {
  return invokeDeviceAction(
    { action: 'register', expoPushToken, platform, deviceName },
    client,
  );
}

export function refreshDeviceRegistration(
  expoPushToken: string,
  client: AlertDataClient = defaultClient,
): Promise<DeviceRegistrationResponse> {
  return invokeDeviceAction({ action: 'refresh', expoPushToken }, client);
}

export function deactivateDevice(
  expoPushToken: string,
  client: AlertDataClient = defaultClient,
): Promise<DeviceRegistrationResponse> {
  return invokeDeviceAction({ action: 'deactivate', expoPushToken }, client);
}
