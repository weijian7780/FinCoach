import { describe, expect, it } from 'vitest';

import {
  aggregateDeliveryStatus,
  buildExpoPushMessage,
  chunkExpoMessages,
  classifyExpoError,
  mapExpoTicketsToDevices,
  nextRetryDelayMilliseconds,
} from './push-domain';

describe('Expo message creation and batching', () => {
  it('creates a minimal channel-aware financial notification', () => {
    expect(
      buildExpoPushMessage(
        {
          id: 'alert-1',
          type: 'budget_warning',
          title: 'Budget almost reached',
          message: 'You have used 80% of your July budget.',
          route: '/budget?month=2026-07-01',
        },
        'ExponentPushToken[token]',
      ),
    ).toEqual({
      to: 'ExponentPushToken[token]',
      title: 'Budget almost reached',
      body: 'You have used 80% of your July budget.',
      data: {
        alertId: 'alert-1',
        type: 'budget_warning',
        url: '/budget?month=2026-07-01',
      },
      channelId: 'budget',
      sound: 'default',
      priority: 'high',
    });
  });

  it('chunks messages at Expo Push Service limits', () => {
    const messages = Array.from({ length: 205 }, (_, index) => ({ to: `token-${index}` }));
    expect(chunkExpoMessages(messages).map((chunk) => chunk.length)).toEqual([100, 100, 5]);
  });
});

describe('Expo ticket and retry handling', () => {
  it.each([
    ['DeviceNotRegistered', 'permanent'],
    ['MismatchSenderId', 'permanent'],
    ['InvalidCredentials', 'permanent'],
    ['MessageTooBig', 'permanent'],
    ['MessageRateExceeded', 'retryable'],
    ['InternalServerError', 'retryable'],
    [undefined, 'retryable'],
  ] as const)('classifies %s as %s', (error, classification) => {
    expect(classifyExpoError(error)).toBe(classification);
  });

  it('maps each ticket to its device without storing push tokens', () => {
    expect(
      mapExpoTicketsToDevices(
        ['device-1', 'device-2', 'device-3'],
        [
          { status: 'ok', id: 'ticket-1' },
          { status: 'error', message: 'Unregistered', details: { error: 'DeviceNotRegistered' } },
          { status: 'error', message: 'Busy', details: { error: 'MessageRateExceeded' } },
        ],
      ),
    ).toEqual({
      'device-1': { status: 'sent', ticketId: 'ticket-1' },
      'device-2': {
        status: 'failed',
        error: 'DeviceNotRegistered',
        retryable: false,
      },
      'device-3': {
        status: 'retryable',
        error: 'MessageRateExceeded',
        retryable: true,
      },
    });
  });

  it('uses bounded exponential retry delays', () => {
    expect(nextRetryDelayMilliseconds(1)).toBe(30_000);
    expect(nextRetryDelayMilliseconds(2)).toBe(60_000);
    expect(nextRetryDelayMilliseconds(20)).toBe(21_600_000);
  });
});

describe('aggregate delivery state', () => {
  it('handles no devices and all-device states', () => {
    expect(aggregateDeliveryStatus([])).toBe('no_active_device');
    expect(aggregateDeliveryStatus(['sent', 'sent'])).toBe('sent');
    expect(aggregateDeliveryStatus(['delivered', 'delivered'])).toBe('delivered');
    expect(aggregateDeliveryStatus(['failed', 'failed'])).toBe('failed');
  });

  it('keeps retryable work retryable and mixed final results partial', () => {
    expect(aggregateDeliveryStatus(['delivered', 'retryable'])).toBe('retryable');
    expect(aggregateDeliveryStatus(['delivered', 'failed'])).toBe('partially_delivered');
  });
});
