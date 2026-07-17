import { describe, expect, test } from 'vitest';

import {
  compileFinancialReport,
  createPresetSelection,
  formatReportMoney,
  formatReportPeriod,
  monthKeysForRange,
  validateReportSelection,
} from './report-domain';
import type { ReportSelection, ReportSourceData, TransactionWithCategory } from './types';

function transaction(
  id: string,
  date: string,
  amount: number,
  categoryId: number,
  categoryName: string,
  type: 'income' | 'expense',
): TransactionWithCategory {
  return {
    id,
    user_id: 'user-1',
    category_id: categoryId,
    amount,
    transaction_date: date,
    description: null,
    source: categoryName,
    receipt_image_path: null,
    created_at: `${date}T08:00:00Z`,
    updated_at: `${date}T08:00:00Z`,
    category: {
      id: categoryId,
      user_id: null,
      name: categoryName,
      type,
      icon: null,
      color: categoryId === 1 ? '#E45C3A' : '#4255D4',
    },
  };
}

const selection: ReportSelection = {
  preset: 'last_3_months',
  startDate: '2026-06-01',
  endDate: '2026-07-31',
  categoryId: null,
  reportType: 'multi_month',
};

const source: ReportSourceData = {
  transactions: [
    transaction('income-1', '2026-07-02', 1500, 9, 'Income', 'income'),
    transaction('food-1', '2026-07-03', 250, 1, 'Food', 'expense'),
    transaction('transport-1', '2026-06-20', 100, 2, 'Transport', 'expense'),
  ],
  monthlyBudgets: [
    { id: 'b1', user_id: 'user-1', month: '2026-06-01', limit_amount: 800, created_at: '', updated_at: '' },
    { id: 'b2', user_id: 'user-1', month: '2026-07-01', limit_amount: 1200, created_at: '', updated_at: '' },
  ],
  categoryLimits: [
    { id: 1, user_id: 'user-1', month: '2026-07-01', category_id: 1, amount: 400, created_at: '', updated_at: '' },
  ],
  savingsGoals: [
    { id: 'g1', user_id: 'user-1', name: 'Laptop', target_amount: 1000, current_amount: 500, deadline: null, created_at: '', updated_at: '' },
  ],
};

describe('report selections', () => {
  test('uses local calendar dates for the current month', () => {
    const now = new Date(2026, 6, 16, 0, 30);
    expect(createPresetSelection('current_month', now)).toEqual({
      preset: 'current_month',
      startDate: '2026-07-01',
      endDate: '2026-07-31',
      categoryId: null,
      reportType: 'monthly',
    });
  });

  test('resolves previous and recent months across year boundaries', () => {
    const now = new Date(2026, 0, 4, 12);
    expect(createPresetSelection('previous_month', now)).toMatchObject({
      startDate: '2025-12-01',
      endDate: '2025-12-31',
    });
    expect(createPresetSelection('last_3_months', now)).toMatchObject({
      startDate: '2025-11-01',
      endDate: '2026-01-31',
      reportType: 'multi_month',
    });
    expect(monthKeysForRange('2025-11-10', '2026-01-04')).toEqual([
      '2025-11-01',
      '2025-12-01',
      '2026-01-01',
    ]);
  });

  test('validates strict and ordered custom ranges', () => {
    expect(validateReportSelection({
      preset: 'custom',
      startDate: '2026-07-31',
      endDate: '2026-07-01',
      categoryId: null,
      reportType: 'custom',
    })).toBe('Start date must be on or before end date.');
    expect(validateReportSelection({
      preset: 'custom',
      startDate: '2026-02-30',
      endDate: '2026-03-01',
      categoryId: null,
      reportType: 'custom',
    })).toBe('Enter valid start and end dates.');
    expect(validateReportSelection(selection)).toBeNull();
  });

  test('formats canonical report periods and category-aware types', () => {
    expect(formatReportPeriod(selection)).toBe('2026-06..2026-07');
    expect(formatReportPeriod({ ...selection, preset: 'custom', startDate: '2026-06-02', reportType: 'custom' })).toBe(
      '2026-06-02..2026-07-31',
    );
  });
});

describe('financial report compiler', () => {
  test('calculates real summaries, categories, trends, budget, and savings', () => {
    const report = compileFinancialReport(source, selection);
    expect(report).toMatchObject({
      totalIncome: 1500,
      totalExpenses: 350,
      netBalance: 1150,
      transactionCount: 3,
      budget: {
        limit: 2000,
        spent: 350,
        remaining: 1650,
        exceeded: 0,
        percentage: 17.5,
        progressPercentage: 17.5,
      },
      savings: {
        current: 500,
        target: 1000,
        remaining: 500,
        percentage: 50,
        progressPercentage: 50,
      },
    });
    expect(report.categoryTotals.map((item) => [item.name, item.amount, item.percentage])).toEqual([
      ['Food', 250, 71.43],
      ['Transport', 100, 28.57],
    ]);
    expect(report.trend).toEqual([
      { month: '2026-06-01', income: 0, expenses: 100, net: -100 },
      { month: '2026-07-01', income: 1500, expenses: 250, net: 1250 },
    ]);
  });

  test('keeps overall budget spending unfiltered when a category report is selected', () => {
    const report = compileFinancialReport(source, {
      ...selection,
      categoryId: 1,
      reportType: 'multi_month_category',
    });
    expect(report.totalIncome).toBe(0);
    expect(report.totalExpenses).toBe(250);
    expect(report.transactionCount).toBe(1);
    expect(report.categoryTotals.map((item) => item.name)).toEqual(['Food']);
    expect(report.budget.spent).toBe(350);
  });

  test('shows true over-budget percentages while capping visual progress only', () => {
    const report = compileFinancialReport({
      ...source,
      monthlyBudgets: [{ ...source.monthlyBudgets[0], limit_amount: 100 }],
    }, selection);
    expect(report.budget).toMatchObject({
      limit: 100,
      spent: 350,
      remaining: 0,
      exceeded: 250,
      percentage: 350,
      progressPercentage: 100,
    });
  });

  test('fills missing trend months and handles empty data safely', () => {
    const empty = compileFinancialReport({
      transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [],
    }, {
      preset: 'last_3_months', startDate: '2026-05-01', endDate: '2026-07-31',
      categoryId: null, reportType: 'multi_month',
    });
    expect(empty.trend).toEqual([
      { month: '2026-05-01', income: 0, expenses: 0, net: 0 },
      { month: '2026-06-01', income: 0, expenses: 0, net: 0 },
      { month: '2026-07-01', income: 0, expenses: 0, net: 0 },
    ]);
    expect(empty.categoryTotals).toEqual([]);
    expect(empty.budget.percentage).toBe(0);
    expect(empty.savings.percentage).toBe(0);
  });

  test('rounds currency consistently for Malaysian display', () => {
    expect(formatReportMoney(1234.505)).toBe('RM 1,234.51');
  });
});
