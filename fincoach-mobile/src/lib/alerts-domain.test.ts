import { describe, expect, it } from 'vitest';

import type { AlertRecord } from './types';
import {
  advanceRecurringDate,
  buildBillDedupeKey,
  buildBudgetDedupeKey,
  buildSavingsDedupeKey,
  buildSpendingPeriodKey,
  calculateNextBillTrigger,
  calculateSavingsReminderAt,
  filterAlerts,
  formatLeadDays,
  formatNotificationTime,
  formatReminderDue,
  formatSpendingSchedule,
  getCrossedBudgetThreshold,
  getReachedBudgetThreshold,
  summarizeBudgetAlerts,
  getCrossedSavingsMilestones,
  groupAlertsByDate,
  groupUpcomingReminders,
  normalizeReminderTime,
  routeForAlert,
  validateBillReminderInput,
} from './alerts-domain';

function reminder(overrides: Partial<import('./types').BillReminder> = {}) {
  return {
    id: 'reminder-1',
    user_id: 'user-1',
    type: 'bill' as const,
    title: 'Wi-Fi bill',
    amount: 60,
    due_at: '2026-07-16T13:00:00.000Z',
    lead_days: 0,
    recurrence: 'none' as const,
    recurrence_anchor_day: 16,
    enabled: true,
    next_trigger_at: '2026-07-16T13:00:00.000Z',
    last_triggered_at: null,
    created_at: '2026-07-15T02:00:00.000Z',
    updated_at: '2026-07-15T02:00:00.000Z',
    ...overrides,
  };
}

describe('notification preference times', () => {
  it('normalizes PostgreSQL time values to the HH:MM form used by the settings UI', () => {
    expect(normalizeReminderTime('20:00:00')).toBe('20:00');
    expect(normalizeReminderTime('09:30')).toBe('09:30');
    expect(normalizeReminderTime('25:00:00')).toBeNull();
  });

  it('formats compact preference summaries for progressive disclosure rows', () => {
    expect(formatNotificationTime('20:00:00')).toBe('8:00 PM');
    expect(formatSpendingSchedule('weekly', 4, '20:00')).toBe(
      'Weekly · Thursday · 8:00 PM',
    );
    expect(formatSpendingSchedule('daily', null, '09:30')).toBe('Daily · 9:30 AM');
    expect(formatLeadDays(0)).toBe('On the day');
    expect(formatLeadDays(1)).toBe('1 day');
    expect(formatLeadDays(7)).toBe('7 days');
  });
});

function alert(overrides: Partial<AlertRecord>): AlertRecord {
  return {
    id: 'alert-1',
    user_id: 'user-1',
    type: 'spending_reminder',
    kind: 'insight',
    title: 'Record spending',
    message: 'Keep your records up to date.',
    budget_id: null,
    category_limit_id: null,
    savings_goal_id: null,
    reminder_id: null,
    source_data: {},
    dedupe_key: 'spending:daily:2026-07-15',
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
    created_at: '2026-07-15T02:00:00.000Z',
    ...overrides,
  };
}

describe('budget threshold crossings', () => {
  it('fires warning only when usage newly crosses 80 percent', () => {
    expect(getCrossedBudgetThreshold(799.99, 800, 1000)).toBe('warning');
    expect(getCrossedBudgetThreshold(800, 850, 1000)).toBeNull();
  });

  it('fires exceeded only when usage newly crosses 100 percent', () => {
    expect(getCrossedBudgetThreshold(999.99, 1000, 1000)).toBe('exceeded');
    expect(getCrossedBudgetThreshold(1000, 1100, 1000)).toBeNull();
  });

  it('gives exceeded precedence when one transaction crosses both thresholds', () => {
    expect(getCrossedBudgetThreshold(700, 1100, 1000)).toBe('exceeded');
  });

  it('ignores decreases and invalid limits', () => {
    expect(getCrossedBudgetThreshold(900, 700, 1000)).toBeNull();
    expect(getCrossedBudgetThreshold(0, 100, 0)).toBeNull();
  });
});

describe('budget threshold already reached when a limit is saved', () => {
  it('reports the highest threshold the current spending has reached', () => {
    expect(getReachedBudgetThreshold(387.1, 300)).toBe('exceeded');
    expect(getReachedBudgetThreshold(600, 600)).toBe('exceeded');
    expect(getReachedBudgetThreshold(480, 600)).toBe('warning');
    expect(getReachedBudgetThreshold(479.99, 600)).toBeNull();
    expect(getReachedBudgetThreshold(100, 0)).toBeNull();
  });
});

describe('in-app budget alert summary', () => {
  it('shows a single alert as-is and merges several into one dialog', () => {
    expect(summarizeBudgetAlerts([])).toBeNull();
    const overall = { type: 'budget_exceeded', title: 'Monthly budget exceeded', message: 'You have used 110% of this limit. Review your spending.' };
    const food = { type: 'budget_warning', title: 'Food limit is almost reached', message: 'You have used 85% of this limit. RM 15.00 remains.' };
    expect(summarizeBudgetAlerts([overall])).toEqual({ title: overall.title, message: overall.message });
    expect(summarizeBudgetAlerts([overall, food])).toEqual({
      title: 'Budget limits exceeded',
      message: `${overall.title}. ${overall.message}\n\n${food.title}. ${food.message}`,
    });
    expect(summarizeBudgetAlerts([food, food])?.title).toBe('Budget limits almost reached');
  });
});

describe('savings milestone crossings', () => {
  it('returns every newly crossed milestone in ascending order', () => {
    expect(getCrossedSavingsMilestones(200, 800, 1000)).toEqual([25, 50, 75]);
  });

  it('includes completion once and ignores repeated/decreasing progress', () => {
    expect(getCrossedSavingsMilestones(750, 1000, 1000)).toEqual([100]);
    expect(getCrossedSavingsMilestones(1000, 1000, 1000)).toEqual([]);
    expect(getCrossedSavingsMilestones(800, 700, 1000)).toEqual([]);
  });

  it('rejects a non-positive target', () => {
    expect(getCrossedSavingsMilestones(0, 100, 0)).toEqual([]);
  });
});

describe('stable alert dedupe keys', () => {
  it('separates overall and category budget periods', () => {
    expect(
      buildBudgetDedupeKey({
        scope: 'overall',
        sourceId: 'budget-1',
        month: '2026-07-01',
        threshold: 'warning',
        limit: 1000,
      }),
    ).toBe('budget:overall:budget-1:2026-07-01:warning:100000');
    expect(
      buildBudgetDedupeKey({
        scope: 'category',
        sourceId: 12,
        month: '2026-07-01',
        threshold: 'exceeded',
        limit: 250.5,
      }),
    ).toBe('budget:category:12:2026-07-01:exceeded:25050');
  });

  it('gives a changed limit a new budget alert identity', () => {
    const key = (limit: number) =>
      buildBudgetDedupeKey({ scope: 'overall', sourceId: 'b1', month: '2026-10-01', threshold: 'exceeded', limit });
    expect(key(800)).not.toBe(key(8000));
    expect(key(800)).toBe(key(800.001));
  });

  it('builds savings, spending, and bill occurrence identities', () => {
    expect(buildSavingsDedupeKey('goal-1', 'milestone', 50)).toBe(
      'savings:goal-1:milestone:50',
    );
    expect(buildSavingsDedupeKey('goal-1', 'deadline', '2026-08-01')).toBe(
      'savings:goal-1:deadline:2026-08-01',
    );
    expect(buildSpendingPeriodKey('weekly', '2026-07-13')).toBe(
      'spending:weekly:2026-07-13',
    );
    expect(buildBillDedupeKey('reminder-1', '2026-07-20T01:00:00.000Z')).toBe(
      'bill:reminder-1:2026-07-20T01:00:00.000Z',
    );
  });
});

describe('recurrence and trigger calculations', () => {
  it('advances weekly reminders by exactly seven calendar days', () => {
    expect(advanceRecurringDate('2026-07-15T01:30:00.000Z', 'weekly')).toBe(
      '2026-07-22T01:30:00.000Z',
    );
  });

  it('preserves the original month-day anchor across short months', () => {
    const february = advanceRecurringDate('2026-01-31T01:00:00.000Z', 'monthly', 31);
    expect(february).toBe('2026-02-28T01:00:00.000Z');
    expect(advanceRecurringDate(february!, 'monthly', 31)).toBe(
      '2026-03-31T01:00:00.000Z',
    );
  });

  it('clamps yearly leap-day recurrence when needed', () => {
    expect(advanceRecurringDate('2024-02-29T01:00:00.000Z', 'yearly', 29)).toBe(
      '2025-02-28T01:00:00.000Z',
    );
  });

  it('returns null for a non-recurring reminder', () => {
    expect(advanceRecurringDate('2026-07-15T01:00:00.000Z', 'none')).toBeNull();
  });

  it('subtracts lead days from the selected bill due time', () => {
    expect(calculateNextBillTrigger('2026-07-20T01:00:00.000Z', 3)).toBe(
      '2026-07-17T01:00:00.000Z',
    );
  });

  it('converts a Malaysia deadline reminder time to UTC', () => {
    expect(
      calculateSavingsReminderAt('2026-08-01', 7, '09:30', 'Asia/Kuala_Lumpur'),
    ).toBe('2026-07-25T01:30:00.000Z');
  });
});

describe('bill reminder validation', () => {
  const now = '2026-07-15T02:00:00.000Z';

  it('reports all required and malformed values', () => {
    expect(
      validateBillReminderInput(
        {
          title: ' ',
          amount: 'RM 20',
          dueAt: 'not-a-date',
          leadDays: -1,
          recurrence: 'monthly',
        },
        now,
      ),
    ).toEqual({
      title: 'Enter a reminder title.',
      amount: 'Enter a valid amount greater than RM 0.',
      dueAt: 'Choose a valid future due date and time.',
      leadDays: 'Lead time must be between 0 and 365 days.',
    });
  });

  it('rejects past dates and overlong titles', () => {
    const result = validateBillReminderInput(
      {
        title: 'a'.repeat(101),
        amount: '',
        dueAt: '2026-07-15T01:59:59.000Z',
        leadDays: 3,
        recurrence: 'none',
      },
      now,
    );
    expect(result.title).toBe('Reminder title must be 100 characters or fewer.');
    expect(result.dueAt).toBe('Choose a future due date and time.');
    expect(result.amount).toBeUndefined();
  });

  it('accepts a valid optional-amount reminder', () => {
    expect(
      validateBillReminderInput(
        {
          title: 'Internet bill',
          amount: '129.90',
          dueAt: '2026-07-20T01:00:00.000Z',
          leadDays: 3,
          recurrence: 'monthly',
        },
        now,
      ),
    ).toEqual({});
  });
});

describe('reminder list presentation', () => {
  const now = '2026-07-15T02:00:00.000Z';

  it('uses the notification timezone for a concise, unambiguous due label', () => {
    expect(formatReminderDue('2026-07-16T13:00:00.000Z', now, 'Asia/Kuala_Lumpur')).toBe(
      'Tomorrow · 9:00 PM',
    );
  });

  it('groups the chronological list into Next up, This week, and Later', () => {
    const groups = groupUpcomingReminders([
      reminder({ id: 'tomorrow', due_at: '2026-07-16T13:00:00.000Z' }),
      reminder({ id: 'this-week', due_at: '2026-07-20T13:00:00.000Z' }),
      reminder({ id: 'later', due_at: '2026-08-01T13:00:00.000Z' }),
    ], now, 'Asia/Kuala_Lumpur');

    expect(groups.nextUp.map((item) => item.id)).toEqual(['tomorrow']);
    expect(groups.thisWeek.map((item) => item.id)).toEqual(['this-week']);
    expect(groups.later.map((item) => item.id)).toEqual(['later']);
  });
});

describe('alert inbox grouping, filters, and navigation', () => {
  const records = [
    alert({ id: 'today', created_at: '2026-07-15T02:00:00.000Z', kind: 'insight' }),
    alert({
      id: 'yesterday',
      created_at: '2026-07-14T02:00:00.000Z',
      kind: 'alert',
      type: 'budget_warning',
    }),
    alert({ id: 'earlier', created_at: '2026-07-01T02:00:00.000Z', kind: 'alert' }),
  ];

  it('groups using the user timezone rather than the server date', () => {
    const groups = groupAlertsByDate(
      records,
      '2026-07-15T12:00:00.000Z',
      'Asia/Kuala_Lumpur',
    );
    expect(groups.today.map((item) => item.id)).toEqual(['today']);
    expect(groups.yesterday.map((item) => item.id)).toEqual(['yesterday']);
    expect(groups.earlier.map((item) => item.id)).toEqual(['earlier']);
  });

  it('filters All, Insights, and Alerts independently', () => {
    expect(filterAlerts(records, 'all')).toHaveLength(3);
    expect(filterAlerts(records, 'insights').map((item) => item.id)).toEqual(['today']);
    expect(filterAlerts(records, 'alerts').map((item) => item.id)).toEqual([
      'yesterday',
      'earlier',
    ]);
  });

  it('maps source alerts to safe Expo Router destinations', () => {
    expect(
      routeForAlert(
        alert({
          type: 'budget_warning',
          budget_id: 'budget-1',
          source_data: { month: '2026-07-01' },
        }),
      ),
    ).toBe('/budget?month=2026-07-01');
    expect(
      routeForAlert(alert({ type: 'savings_milestone', savings_goal_id: 'goal-1' })),
    ).toBe('/savings/goal-1');
    expect(
      routeForAlert(alert({ type: 'bill_reminder', reminder_id: 'reminder-1' })),
    ).toBe('/alerts/reminders/manage?id=reminder-1');
    expect(routeForAlert(alert({ type: 'spending_reminder' }))).toBe('/transactions/manage');
    expect(routeForAlert(alert({ type: 'savings_deadline', savings_goal_id: null }))).toBe(
      '/alerts',
    );
  });
});
