import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createIdempotentAlert,
  createReminder,
  deactivateDevice,
  deleteReminder,
  dismissAlert,
  ensureNotificationPreferences,
  fetchAlerts,
  fetchNotificationPreferences,
  fetchReminders,
  fetchUnreadAlertCount,
  markAlertRead,
  markAllAlertsRead,
  refreshDeviceRegistration,
  registerDevice,
  saveNotificationPreferences,
  setReminderEnabled,
  updateReminder,
} from './alerts';
import type { AlertRecord, BillReminder, NotificationPreferences } from './types';

vi.mock('./supabase', () => ({ supabase: {} }));

const preferences: NotificationPreferences = {
  user_id: 'user-1',
  budget_enabled: true,
  savings_enabled: true,
  savings_lead_days: 7,
  savings_reminder_time: '09:00:00',
  savings_milestones_enabled: true,
  spending_enabled: true,
  spending_frequency: 'weekly',
  spending_weekday: 1,
  spending_reminder_time: '20:00:00',
  bills_enabled: true,
  default_bill_lead_days: 3,
  default_bill_reminder_time: '09:00:00',
  timezone: 'Asia/Kuala_Lumpur',
  created_at: '2026-07-15T00:00:00.000Z',
  updated_at: '2026-07-15T00:00:00.000Z',
};

const reminder: BillReminder = {
  id: 'reminder-1',
  user_id: 'user-1',
  type: 'bill',
  title: 'Internet bill',
  amount: 129.9,
  due_at: '2026-07-20T01:00:00.000Z',
  lead_days: 3,
  recurrence: 'monthly',
  recurrence_anchor_day: 20,
  enabled: true,
  next_trigger_at: '2026-07-17T01:00:00.000Z',
  last_triggered_at: null,
  created_at: '2026-07-15T00:00:00.000Z',
  updated_at: '2026-07-15T00:00:00.000Z',
};

const alert: AlertRecord = {
  id: 'alert-1',
  user_id: 'user-1',
  type: 'budget_warning',
  kind: 'alert',
  title: 'Budget almost reached',
  message: 'You have used 80% of your July budget.',
  budget_id: 'budget-1',
  category_limit_id: null,
  savings_goal_id: null,
  reminder_id: null,
  source_data: { month: '2026-07-01' },
  dedupe_key: 'budget:overall:budget-1:2026-07-01:warning',
  scheduled_for: null,
  delivered_at: null,
  read_at: null,
  dismissed_at: null,
  delivery_status: 'pending',
  delivery_error: null,
  delivery_attempt_count: 0,
  delivery_claimed_at: null,
  next_delivery_attempt_at: null,
  delivery_receipts: {},
  created_at: '2026-07-15T00:00:00.000Z',
};

type Result = { data?: unknown; error?: unknown; count?: number | null };

function createClient(options: {
  result?: Result;
  single?: Result;
  maybeSingle?: Result;
  invoke?: Result;
} = {}) {
  const base = {
    data: options.result?.data ?? null,
    error: options.result?.error ?? null,
    count: options.result?.count ?? null,
  };
  const builder: Record<string, ReturnType<typeof vi.fn>> & {
    then?: (
      resolve: (value: typeof base) => unknown,
      reject?: (reason: unknown) => unknown,
    ) => Promise<unknown>;
  } = {
    select: vi.fn(),
    eq: vi.fn(),
    is: vi.fn(),
    order: vi.fn(),
    limit: vi.fn(),
    insert: vi.fn(),
    upsert: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    single: vi.fn(),
    maybeSingle: vi.fn(),
  };

  for (const method of [
    'select',
    'eq',
    'is',
    'order',
    'limit',
    'insert',
    'upsert',
    'update',
    'delete',
  ] as const) {
    builder[method].mockReturnValue(builder);
  }
  builder.single.mockResolvedValue({
    data: options.single?.data ?? base.data,
    error: options.single?.error ?? base.error,
    count: options.single?.count ?? base.count,
  });
  builder.maybeSingle.mockResolvedValue({
    data: options.maybeSingle?.data ?? base.data,
    error: options.maybeSingle?.error ?? base.error,
    count: options.maybeSingle?.count ?? base.count,
  });
  builder.then = (resolve, reject) => Promise.resolve(base).then(resolve, reject);

  const client = {
    from: vi.fn().mockReturnValue(builder),
    functions: {
      invoke: vi.fn().mockResolvedValue({
        data: options.invoke?.data ?? null,
        error: options.invoke?.error ?? null,
      }),
    },
  };
  return { builder, client };
}

beforeEach(() => {
  vi.useRealTimers();
});

describe('notification preferences', () => {
  it('fetches the signed-in owner preference row', async () => {
    const { builder, client } = createClient({ maybeSingle: { data: preferences } });
    await expect(fetchNotificationPreferences('user-1', client)).resolves.toEqual(preferences);
    expect(client.from).toHaveBeenCalledWith('notification_preferences');
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });

  it('creates approved defaults when no row exists', async () => {
    const { builder, client } = createClient({
      maybeSingle: { data: null },
      single: { data: preferences },
    });

    await expect(ensureNotificationPreferences('user-1', client)).resolves.toEqual(preferences);
    expect(builder.insert).toHaveBeenCalledWith({
      user_id: 'user-1',
      budget_enabled: true,
      savings_enabled: true,
      savings_lead_days: 7,
      savings_reminder_time: '09:00',
      savings_milestones_enabled: true,
      spending_enabled: true,
      spending_frequency: 'weekly',
      spending_weekday: 1,
      spending_reminder_time: '20:00',
      bills_enabled: true,
      default_bill_lead_days: 3,
      default_bill_reminder_time: '09:00',
      timezone: 'Asia/Kuala_Lumpur',
    });
  });

  it('upserts only the selected notification-type settings', async () => {
    const { builder, client } = createClient({ single: { data: preferences } });
    await saveNotificationPreferences(
      'user-1',
      { spending_enabled: false, spending_frequency: 'daily' },
      client,
    );
    expect(builder.upsert).toHaveBeenCalledWith(
      { user_id: 'user-1', spending_enabled: false, spending_frequency: 'daily' },
      { onConflict: 'user_id' },
    );
  });
});

describe('bill reminders', () => {
  it('lists owner reminders in next-trigger order', async () => {
    const { builder, client } = createClient({ result: { data: [reminder] } });
    await expect(fetchReminders('user-1', client)).resolves.toEqual([reminder]);
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builder.order).toHaveBeenNthCalledWith(1, 'next_trigger_at', {
      ascending: true,
      nullsFirst: false,
    });
    expect(builder.order).toHaveBeenNthCalledWith(2, 'due_at', { ascending: true });
  });

  it('creates a normalized owner reminder', async () => {
    const { builder, client } = createClient({ single: { data: reminder } });
    await createReminder(
      'user-1',
      {
        title: ' Internet bill ',
        amount: 129.9,
        due_at: reminder.due_at,
        lead_days: 3,
        recurrence: 'monthly',
        recurrence_anchor_day: 20,
        enabled: true,
      },
      client,
    );
    expect(builder.insert).toHaveBeenCalledWith({
      user_id: 'user-1',
      type: 'bill',
      title: 'Internet bill',
      amount: 129.9,
      due_at: reminder.due_at,
      lead_days: 3,
      recurrence: 'monthly',
      recurrence_anchor_day: 20,
      enabled: true,
    });
  });

  it('updates, toggles, and deletes only an owner reminder', async () => {
    const { builder, client } = createClient({ single: { data: reminder } });
    await updateReminder('reminder-1', 'user-1', { ...reminder, title: 'WiFi' }, client);
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');

    builder.eq.mockClear();
    await setReminderEnabled('reminder-1', 'user-1', false, client);
    expect(builder.update).toHaveBeenLastCalledWith({ enabled: false });
    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', 'reminder-1');
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');

    builder.eq.mockClear();
    await deleteReminder('reminder-1', 'user-1', client);
    expect(builder.delete).toHaveBeenCalled();
    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', 'reminder-1');
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');
  });
});

describe('alert inbox persistence', () => {
  it('lists visible owner alerts newest first', async () => {
    const { builder, client } = createClient({ result: { data: [alert] } });
    await expect(fetchAlerts('user-1', client)).resolves.toEqual([alert]);
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builder.is).toHaveBeenCalledWith('dismissed_at', null);
    expect(builder.order).toHaveBeenCalledWith('created_at', { ascending: false });
    expect(builder.limit).toHaveBeenCalledWith(100);
  });

  it('counts only unread and non-dismissed alerts', async () => {
    const { builder, client } = createClient({ result: { count: 4 } });
    await expect(fetchUnreadAlertCount('user-1', client)).resolves.toBe(4);
    expect(builder.select).toHaveBeenCalledWith('id', { count: 'exact', head: true });
    expect(builder.is).toHaveBeenCalledWith('read_at', null);
    expect(builder.is).toHaveBeenCalledWith('dismissed_at', null);
  });

  it('marks one, all, and dismissed alerts using only allowed state columns', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T03:00:00.000Z'));
    const { builder, client } = createClient();

    await markAlertRead('alert-1', 'user-1', client);
    expect(builder.update).toHaveBeenLastCalledWith({ read_at: '2026-07-15T03:00:00.000Z' });

    await markAllAlertsRead('user-1', client);
    expect(builder.update).toHaveBeenLastCalledWith({ read_at: '2026-07-15T03:00:00.000Z' });
    expect(builder.is).toHaveBeenCalledWith('read_at', null);

    await dismissAlert('alert-1', 'user-1', client);
    expect(builder.update).toHaveBeenLastCalledWith({
      read_at: '2026-07-15T03:00:00.000Z',
      dismissed_at: '2026-07-15T03:00:00.000Z',
    });
  });

  it('treats a duplicate alert as idempotent and returns the existing row', async () => {
    const duplicate = { code: '23505', message: 'duplicate key value' };
    const { builder, client } = createClient({
      single: { error: duplicate },
      maybeSingle: { data: alert },
    });

    await expect(
      createIdempotentAlert(
        'user-1',
        {
          type: alert.type,
          kind: alert.kind,
          title: alert.title,
          message: alert.message,
          budget_id: alert.budget_id,
          category_limit_id: null,
          savings_goal_id: null,
          reminder_id: null,
          source_data: alert.source_data,
          dedupe_key: alert.dedupe_key,
          scheduled_for: null,
        },
        client,
      ),
    ).resolves.toEqual(alert);
    expect(builder.maybeSingle).toHaveBeenCalled();
  });
});

describe('authenticated device function calls', () => {
  it('registers and refreshes without accepting a user id', async () => {
    const response = { active: true, lastSeenAt: '2026-07-15T03:00:00.000Z' };
    const { client } = createClient({ invoke: { data: response } });
    await expect(
      registerDevice('ExponentPushToken[token]', 'android', 'Honor 200', client),
    ).resolves.toEqual(response);
    expect(client.functions.invoke).toHaveBeenLastCalledWith('register-device', {
      body: {
        action: 'register',
        expoPushToken: 'ExponentPushToken[token]',
        platform: 'android',
        deviceName: 'Honor 200',
      },
    });

    await refreshDeviceRegistration('ExponentPushToken[token]', client);
    expect(client.functions.invoke).toHaveBeenLastCalledWith('register-device', {
      body: { action: 'refresh', expoPushToken: 'ExponentPushToken[token]' },
    });
  });

  it('deactivates the current installation through the function', async () => {
    const { client } = createClient({ invoke: { data: { active: false } } });
    await deactivateDevice('ExponentPushToken[token]', client);
    expect(client.functions.invoke).toHaveBeenCalledWith('register-device', {
      body: { action: 'deactivate', expoPushToken: 'ExponentPushToken[token]' },
    });
  });

  it('propagates Supabase and Edge Function errors', async () => {
    const databaseError = new Error('RLS denied');
    const functionError = new Error('Function unavailable');
    const database = createClient({ result: { error: databaseError } });
    const edge = createClient({ invoke: { error: functionError } });
    await expect(fetchAlerts('user-1', database.client)).rejects.toBe(databaseError);
    await expect(deactivateDevice('ExponentPushToken[token]', edge.client)).rejects.toBe(
      functionError,
    );
  });
});
