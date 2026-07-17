import { describe, expect, it } from 'vitest';

import {
  advanceRecurrence,
  PENDING_ALERT_RECOVERY_DELAY_MS,
  savingsDeadlineReminderAt,
  shouldAttemptAlertDelivery,
  spendingPeriod,
  spendingScheduleIsDue,
  summarizeReceipts,
} from './due-domain';

describe('spending reminder periods', () => {
  it('uses the user timezone for daily transaction dates', () => {
    expect(spendingPeriod('2026-07-15T16:30:00.000Z', 'Asia/Kuala_Lumpur', 'daily')).toEqual({
      startDate: '2026-07-16',
      endDate: '2026-07-17',
      periodKey: '2026-07-16',
    });
  });

  it('uses Monday-to-Monday weekly periods', () => {
    expect(spendingPeriod('2026-07-15T12:00:00.000Z', 'Asia/Kuala_Lumpur', 'weekly')).toEqual({
      startDate: '2026-07-13',
      endDate: '2026-07-20',
      periodKey: '2026-07-13',
    });
  });

  it('fires only after the configured local time and weekday', () => {
    expect(
      spendingScheduleIsDue(
        '2026-07-15T12:05:00.000Z',
        'Asia/Kuala_Lumpur',
        'daily',
        null,
        '20:00',
      ),
    ).toBe(true);
    expect(
      spendingScheduleIsDue(
        '2026-07-15T11:55:00.000Z',
        'Asia/Kuala_Lumpur',
        'daily',
        null,
        '20:00',
      ),
    ).toBe(false);
    expect(
      spendingScheduleIsDue(
        '2026-07-15T12:05:00.000Z',
        'Asia/Kuala_Lumpur',
        'weekly',
        3,
        '20:00',
      ),
    ).toBe(true);
    expect(
      spendingScheduleIsDue(
        '2026-07-15T12:05:00.000Z',
        'Asia/Kuala_Lumpur',
        'weekly',
        4,
        '20:00',
      ),
    ).toBe(false);
  });
});

describe('savings and bill date calculations', () => {
  it('creates the configured Malaysia savings lead-time instant', () => {
    expect(
      savingsDeadlineReminderAt('2026-08-01', 7, '09:00', 'Asia/Kuala_Lumpur'),
    ).toBe('2026-07-25T01:00:00.000Z');
  });

  it('advances weekly, monthly, and yearly recurrence without month-end drift', () => {
    expect(advanceRecurrence('2026-07-15T01:00:00.000Z', 'weekly', 15)).toBe(
      '2026-07-22T01:00:00.000Z',
    );
    const february = advanceRecurrence('2026-01-31T01:00:00.000Z', 'monthly', 31);
    expect(february).toBe('2026-02-28T01:00:00.000Z');
    expect(advanceRecurrence(february!, 'monthly', 31)).toBe(
      '2026-03-31T01:00:00.000Z',
    );
    expect(advanceRecurrence('2024-02-29T01:00:00.000Z', 'yearly', 29)).toBe(
      '2025-02-28T01:00:00.000Z',
    );
    expect(advanceRecurrence('2026-07-15T01:00:00.000Z', 'none', 15)).toBeNull();
  });
});

describe('delivery retry and receipts', () => {
  it('waits two minutes before recovering a pending alert', () => {
    expect(PENDING_ALERT_RECOVERY_DELAY_MS).toBe(120_000);
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: 'pending',
          createdAt: '2026-07-15T11:58:01.000Z',
          nextDeliveryAttemptAt: null,
        },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(false);
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: 'pending',
          createdAt: '2026-07-15T11:58:00.000Z',
          nextDeliveryAttemptAt: null,
        },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(true);
  });

  it('attempts only due retryable alerts', () => {
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: 'retryable',
          createdAt: '2026-07-15T11:00:00.000Z',
          nextDeliveryAttemptAt: '2026-07-15T12:00:00.000Z',
        },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(true);
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: 'retryable',
          createdAt: '2026-07-15T11:00:00.000Z',
          nextDeliveryAttemptAt: '2026-07-15T12:01:00.000Z',
        },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(false);
  });

  it.each(['sent', 'delivered', 'failed'])('does not attempt terminal status %s', (status) => {
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: status,
          createdAt: '2026-07-15T11:00:00.000Z',
          nextDeliveryAttemptAt: '2026-07-15T11:00:00.000Z',
        },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(false);
  });

  it('rejects invalid or missing delivery timestamps', () => {
    expect(
      shouldAttemptAlertDelivery(
        { deliveryStatus: 'pending', createdAt: 'invalid', nextDeliveryAttemptAt: null },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(false);
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: 'retryable',
          createdAt: '2026-07-15T11:00:00.000Z',
          nextDeliveryAttemptAt: null,
        },
        '2026-07-15T12:00:00.000Z',
      ),
    ).toBe(false);
    expect(
      shouldAttemptAlertDelivery(
        {
          deliveryStatus: 'pending',
          createdAt: '2026-07-15T11:00:00.000Z',
          nextDeliveryAttemptAt: null,
        },
        'invalid',
      ),
    ).toBe(false);
  });

  it('summarizes delivered, permanent, retryable, and pending device receipts', () => {
    expect(
      summarizeReceipts({
        'device-1': { status: 'delivered' },
        'device-2': { status: 'failed', error: 'DeviceNotRegistered' },
        'device-3': { status: 'retryable', error: 'MessageRateExceeded' },
      }),
    ).toEqual({
      deliveryStatus: 'retryable',
      invalidDeviceIds: ['device-2'],
      retryableDeviceIds: ['device-3'],
    });

    expect(
      summarizeReceipts({
        'device-1': { status: 'delivered' },
        'device-2': { status: 'failed', error: 'InvalidCredentials' },
      }).deliveryStatus,
    ).toBe('partially_delivered');
  });
});
