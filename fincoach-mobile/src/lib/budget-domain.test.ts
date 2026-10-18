import { describe, expect, it } from 'vitest';

import {
  formatBudgetMonth,
  formatBudgetMoney,
  getLimitMetrics,
  getLimitStatus,
  getUnbudgetedCategorySpending,
  monthKey,
  parseBudgetMoney,
  shiftMonth,
  validateCategoryAllocation,
  validateCustomCategory,
  validateMonthlyBudget,
} from './budget-domain';

describe('budget month helpers', () => {
  it('normalizes a date to the first day of its local month', () => {
    expect(monthKey(new Date(2026, 6, 13, 12))).toBe('2026-07-01');
  });

  it('shifts across year boundaries', () => {
    expect(shiftMonth('2026-01-01', -1)).toBe('2025-12-01');
    expect(shiftMonth('2026-12-01', 1)).toBe('2027-01-01');
  });

  it('formats a month for Malaysian English', () => {
    expect(formatBudgetMonth('2026-07-01')).toBe('July 2026');
  });
});

describe('budget money helpers', () => {
  it('parses and rounds valid positive decimal input', () => {
    expect(parseBudgetMoney(' 1200.555 ')).toBe(1200.56);
    expect(parseBudgetMoney('0')).toBe(0);
  });

  it('rejects malformed money input', () => {
    expect(parseBudgetMoney('RM 20')).toBeNull();
    expect(parseBudgetMoney('-20')).toBeNull();
    expect(parseBudgetMoney('')).toBeNull();
  });

  it('formats RM with two decimal places', () => {
    expect(formatBudgetMoney(1234.5)).toBe('RM 1,234.50');
  });
});

describe('limit metrics and status', () => {
  it('keeps overspending visible while capping only visual progress', () => {
    expect(getLimitMetrics(120, 100)).toEqual({
      usedAmount: 120,
      limitAmount: 100,
      remainingAmount: 0,
      exceededAmount: 20,
      ratio: 1.2,
      progressRatio: 1,
      percentage: 120,
    });
  });

  it.each([
    [79.99, 'Within Limit'],
    [80, 'Approaching Limit'],
    [99.99, 'Approaching Limit'],
    [100, 'Limit Reached'],
    [100.01, 'Exceeded'],
  ] as const)('classifies %s%% usage as %s', (used, label) => {
    expect(getLimitStatus(used, 100).label).toBe(label);
  });

  it('finds spending categories that do not have a saved limit', () => {
    const spending = new Map([
      [1, 80],
      [2, 240.555],
      [3, 0],
    ]);

    expect(getUnbudgetedCategorySpending(spending, [1])).toEqual([
      { categoryId: 2, amount: 240.56 },
    ]);
  });
});

describe('budget validation', () => {
  it('requires the monthly budget to cover allocated category limits', () => {
    expect(validateMonthlyBudget('500', 600)).toBe(
      'Overall budget cannot be lower than the RM 600.00 already allocated.',
    );
    expect(validateMonthlyBudget('600', 600)).toBeNull();
  });

  it('prevents a category allocation from exceeding the remaining budget', () => {
    expect(
      validateCategoryAllocation('301', { overallLimit: 1000, otherAllocated: 700 }),
    ).toBe('Only RM 300.00 remains available for this category.');
    expect(
      validateCategoryAllocation('300', { overallLimit: 1000, otherAllocated: 700 }),
    ).toBeNull();
  });

  it('validates custom category ownership fields and duplicate names', () => {
    expect(
      validateCustomCategory(
        { name: ' food ', icon: '', color: '' },
        ['Food', 'Transport'],
      ),
    ).toEqual({
      name: 'A category named Food already exists.',
      icon: 'Choose an icon.',
      color: 'Choose a colour.',
    });
  });
});
