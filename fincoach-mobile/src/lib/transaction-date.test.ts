import { describe, expect, test } from 'vitest';

import { isTransactionDate, malaysiaToday, transactionDateForPicker, transactionDateFromPicker } from './transaction-date';

describe('transaction calendar dates', () => {
  test('rolls today over at midnight in Malaysia rather than UTC', () => {
    expect(malaysiaToday(new Date('2026-09-21T15:59:59Z'))).toBe('2026-09-21');
    expect(malaysiaToday(new Date('2026-09-21T16:00:00Z'))).toBe('2026-09-22');
    expect(malaysiaToday(new Date('2026-12-31T16:00:00Z'))).toBe('2027-01-01');
  });

  test('rejects impossible extracted dates and accepts leap days', () => {
    expect(isTransactionDate('2026-02-29')).toBe(false);
    expect(isTransactionDate('2024-02-29')).toBe(true);
    expect(isTransactionDate('2026-13-01')).toBe(false);
    expect(isTransactionDate('')).toBe(false);
  });

  test('opens missing, invalid and future dates on today', () => {
    for (const value of ['', 'not a date', '2026-02-30', '2026-09-23']) {
      expect(transactionDateForPicker(value, '2026-09-22', true).toISOString()).toBe('2026-09-22T00:00:00.000Z');
    }
  });

  test('round-trips Android UTC calendar days without a timezone shift', () => {
    for (const day of ['2024-02-29', '2026-01-01', '2026-09-22']) {
      const nativeDate = transactionDateForPicker(day, '2026-09-22', true);
      expect(nativeDate.toISOString()).toBe(`${day}T00:00:00.000Z`);
      expect(transactionDateFromPicker(nativeDate, true)).toBe(day);
    }
  });

  test('round-trips local calendar components on other platforms', () => {
    const nativeDate = transactionDateForPicker('2026-09-22', '2026-09-22', false);
    expect(nativeDate.getDate()).toBe(22);
    expect(transactionDateFromPicker(nativeDate, false)).toBe('2026-09-22');
  });
});
