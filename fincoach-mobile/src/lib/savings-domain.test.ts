import { describe, expect, test } from 'vitest';

import {
  formatMoney,
  formatGoalDate,
  getGoalStatus,
  getSavingsMetrics,
  getSavingsSuggestion,
  parseMoney,
  isoDateToLocalDate,
  todayIsoDate,
  validateContributionInput,
  validateGoalInput,
} from '@/lib/savings-domain';

const today = '2026-07-12';

describe('money helpers', () => {
  test('normalizes valid RM input to two decimals', () => {
    expect(parseMoney(' 12.345 ')).toBe(12.35);
    expect(parseMoney('0')).toBe(0);
    expect(formatMoney(1234.5)).toBe('RM 1,234.50');
  });

  test('rejects empty, negative, and malformed amounts', () => {
    expect(parseMoney('')).toBeNull();
    expect(parseMoney('-1')).toBeNull();
    expect(parseMoney('1.2.3')).toBeNull();
    expect(parseMoney('RM 12')).toBeNull();
  });

  test('formats dates using the local calendar day', () => {
    expect(todayIsoDate(new Date(2026, 6, 12, 23, 30))).toBe('2026-07-12');
  });

  test('round-trips stored date-only values without a timezone shift', () => {
    const date = isoDateToLocalDate('2026-08-09');
    expect(date?.getFullYear()).toBe(2026);
    expect(date?.getMonth()).toBe(7);
    expect(date?.getDate()).toBe(9);
    expect(todayIsoDate(date ?? undefined)).toBe('2026-08-09');
    expect(formatGoalDate('2026-08-09')).toBe('9 Aug 2026');
    expect(formatGoalDate(null)).toBe('No deadline');
  });
});

describe('goal validation', () => {
  test('requires purpose and a positive target while allowing no deadline', () => {
    expect(validateGoalInput({ name: '', targetAmount: '0', deadline: '' }, { today, currentAmount: 0 })).toEqual({
      name: 'Enter a goal purpose.',
      targetAmount: 'Enter a target amount greater than RM 0.',
    });
  });

  test('rejects past deadlines', () => {
    expect(
      validateGoalInput(
        { name: 'Laptop', targetAmount: '3000', deadline: '2026-07-11' },
        { today, currentAmount: 0 },
      ).deadline,
    ).toBe('Choose today or a future date.');
  });

  test('rejects target values below recorded contributions', () => {
    expect(
      validateGoalInput(
        { name: 'Laptop', targetAmount: '400', deadline: '2026-12-01' },
        { today, currentAmount: 500 },
      ).targetAmount,
    ).toBe('Target cannot be lower than the RM 500.00 already saved.');
  });

  test('limits goal names to 100 characters', () => {
    expect(
      validateGoalInput(
        { name: 'a'.repeat(101), targetAmount: '100', deadline: '2026-12-01' },
        { today, currentAmount: 0 },
      ).name,
    ).toBe('Goal purpose must be 100 characters or fewer.');
  });

  test('accepts a valid goal', () => {
    expect(
      validateGoalInput(
        { name: 'Emergency fund', targetAmount: '1200.50', deadline: '2026-12-01' },
        { today, currentAmount: 200 },
      ),
    ).toEqual({});
  });
});

describe('contribution validation', () => {
  test('rejects future dates and amounts above the remaining target', () => {
    expect(
      validateContributionInput(
        { amount: '501', contributedOn: '2026-07-13', note: '' },
        { today, remainingAmount: 500 },
      ),
    ).toEqual({
      amount: 'Contribution cannot exceed the RM 500.00 remaining.',
      contributedOn: 'Contribution date cannot be in the future.',
    });
  });

  test('requires a positive amount and contribution date', () => {
    expect(
      validateContributionInput(
        { amount: '0', contributedOn: '', note: '' },
        { today, remainingAmount: 500 },
      ),
    ).toEqual({
      amount: 'Enter a contribution greater than RM 0.',
      contributedOn: 'Choose a contribution date.',
    });
  });

  test('limits optional notes to 200 characters', () => {
    expect(
      validateContributionInput(
        { amount: '50', contributedOn: today, note: 'a'.repeat(201) },
        { today, remainingAmount: 500 },
      ).note,
    ).toBe('Note must be 200 characters or fewer.');
  });

  test('accepts a contribution equal to the remaining target', () => {
    expect(
      validateContributionInput(
        { amount: '500', contributedOn: today, note: 'Final contribution' },
        { today, remainingAmount: 500 },
      ),
    ).toEqual({});
  });
});

describe('progress and status', () => {
  test('caps display progress and never returns negative remaining amount', () => {
    expect(getSavingsMetrics(1200, 1000)).toEqual({
      currentAmount: 1200,
      targetAmount: 1000,
      remainingAmount: 0,
      ratio: 1,
      percentage: 100,
    });
  });

  test('marks a completed goal as reached', () => {
    expect(
      getGoalStatus(
        { currentAmount: 1000, targetAmount: 1000, createdAt: '2026-01-01T00:00:00Z', deadline: today },
        today,
      ).label,
    ).toBe('Goal reached!');
  });

  test('gives overdue incomplete goals precedence over percentage thresholds', () => {
    expect(
      getGoalStatus(
        { currentAmount: 900, targetAmount: 1000, createdAt: '2026-01-01T00:00:00Z', deadline: '2026-07-11' },
        today,
      ).label,
    ).toBe('Needs Attention');
  });

  test('marks non-overdue goals at 80 percent as almost there', () => {
    expect(
      getGoalStatus(
        { currentAmount: 800, targetAmount: 1000, createdAt: '2026-07-01T00:00:00Z', deadline: '2026-08-01' },
        today,
      ).label,
    ).toBe('Almost there!');
  });

  test('uses deadline pace to distinguish on-track from needs-attention goals', () => {
    const base = { targetAmount: 1000, createdAt: '2026-07-01T00:00:00Z', deadline: '2026-07-31' };
    expect(getGoalStatus({ ...base, currentAmount: 300 }, today).label).toBe('On Track');
    expect(getGoalStatus({ ...base, currentAmount: 100 }, today).label).toBe('Needs Attention');
  });

  test('uses the reference 40 percent threshold for legacy goals without a deadline', () => {
    const base = { targetAmount: 1000, createdAt: '2026-01-01T00:00:00Z', deadline: null };
    expect(getGoalStatus({ ...base, currentAmount: 400 }, today).label).toBe('On Track');
    expect(getGoalStatus({ ...base, currentAmount: 399 }, today).label).toBe('Needs Attention');
  });
});

describe('saving suggestions', () => {
  test('calculates a practical weekly amount before a future deadline', () => {
    expect(getSavingsSuggestion({ currentAmount: 500, targetAmount: 1000, deadline: '2026-08-09' }, today)).toBe(
      'Save about RM 125.00 per week to reach this goal by 9 Aug 2026.',
    );
  });

  test('handles reached, due-today, overdue, and legacy no-deadline goals', () => {
    expect(getSavingsSuggestion({ currentAmount: 1000, targetAmount: 1000, deadline: today }, today)).toBe(
      'Goal reached. Keep these savings set aside for their intended purpose.',
    );
    expect(getSavingsSuggestion({ currentAmount: 750, targetAmount: 1000, deadline: today }, today)).toBe(
      'RM 250.00 remains to reach this goal today.',
    );
    expect(getSavingsSuggestion({ currentAmount: 750, targetAmount: 1000, deadline: '2026-07-11' }, today)).toBe(
      'RM 250.00 remains and the deadline has passed. Choose a new deadline or revise your contribution plan.',
    );
    expect(getSavingsSuggestion({ currentAmount: 750, targetAmount: 1000, deadline: null }, today)).toBe(
      'RM 250.00 remains. Set a deadline to calculate a weekly saving amount.',
    );
  });
});
