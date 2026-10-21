import { describe, expect, test } from 'vitest';
import { compileFinancialReport, formatReportMoney, monthKeysForRange, validateReportSelection } from './report-domain';
import { buildFinancialReportHtml, createReportPdfArtifact } from './report-pdf';
import type { ReportSelection, ReportSourceData, TransactionWithCategory } from './types';

const selection: ReportSelection = { preset: 'custom', reportType: 'custom', categoryId: null, startDate: '2026-10-01', endDate: '2026-10-31' };
function source(amount = 100, count = 1): ReportSourceData {
  return { transactions: Array.from({ length: count }, (_, id) => ({ id: String(id), user_id: 'owner', category_id: 1, amount,
    transaction_date: '2026-10-02', created_at: '2026-10-02T00:00:00Z', updated_at: '', description: null, source: 'Food', receipt_image_path: null,
    category: { id: 1, name: 'Food', type: 'expense', user_id: null, icon: null, color: null },
  } as TransactionWithCategory)), monthlyBudgets: [], categoryLimits: [], savingsGoals: [] };
}
describe('report repair boundaries', () => {
  test('accepts 120 touched months and rejects 121 before compilation', () => {
    expect(validateReportSelection({ ...selection, startDate: '2017-01-15', endDate: '2026-12-31' })).toBeNull();
    expect(validateReportSelection({ ...selection, startDate: '2017-01-15', endDate: '2027-01-01' })).toMatch(/120/);
    expect(() => compileFinancialReport(source(), { ...selection, startDate: '1900-01-01', endDate: '9999-12-31' })).toThrow(/120/);
    // Export callers retain the unrestricted shared calendar helper.
    expect(monthKeysForRange('2016-01-01', '2026-12-31')).toHaveLength(132);
  });
  test('keeps summary, budget, category and trend totals equal to exact cents', () => {
    const data = source(9999999999.99, 500);
    data.monthlyBudgets = [{ id: 'oct', user_id: 'owner', month: '2026-10-01', limit_amount: 1, created_at: '', updated_at: '' }];
    const report = compileFinancialReport(data, selection);
    expect(report.totalExpenses).toBe(4999999999995);
    expect(report.budget.spent).toBe(4999999999995);
    expect(report.netBalance).toBe(-4999999999995);
    expect(report.categoryTotals[0].amount).toBe(4999999999995);
    expect(report.trend[0].expenses).toBe(4999999999995);
  });
  test('rejects unsupported aggregates rather than silently losing cents', () => {
    expect(() => compileFinancialReport(source(9999999999.99, 2300), selection)).toThrow(/supported|large|amount/i);
    expect(() => compileFinancialReport(source(Number.NaN), selection)).toThrow();
    const maximum = (2 ** 51 - 1) / 100;
    expect(formatReportMoney(compileFinancialReport(source(maximum), selection).totalExpenses)).toBe('RM 22,517,998,136,852.47');
    expect(() => compileFinancialReport(source(maximum + 0.01), selection)).toThrow(/supported/);
  });
  test('agrees to the cent across income, category limits, contextual budgets, and savings', () => {
    const data = source(0.1, 2);
    data.transactions[1] = { ...data.transactions[1], amount: 0.2, transaction_date: '2026-11-02' };
    data.transactions.push(...data.transactions.map((row) => ({ ...row, id: `income-${row.id}`, category_id: 2,
      category: { ...row.category, id: 2, name: 'Income', type: 'income' as const } })));
    const timestamps = { created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', user_id: 'owner' };
    data.monthlyBudgets = [0.1, 0.2].map((amount, index) => ({ ...timestamps,
      id: String(index), month: `2026-${10 + index}-01`, limit_amount: amount }));
    data.categoryLimits = [0.1, 0.2].map((amount, index) => ({ ...timestamps,
      id: index, category_id: 1, month: `2026-${10 + index}-01`, amount }));
    data.savingsGoals = [0.1, 0.2].map((amount, index) => ({ ...timestamps,
      id: String(index), name: 'Savings', deadline: null, current_amount: amount, target_amount: index ? 0.6 : 0.3 }));
    const report = compileFinancialReport(data, { ...selection, endDate: '2026-11-30' });
    expect([report.totalIncome, report.totalExpenses, report.budget.spent, report.budget.limit, report.categoryTotals[0].amount]).toEqual([0.3, 0.3, 0.3, 0.3, 0.3]);
    expect(report.netBalance).toBe(0);
    expect(report.categoryBudgets[0]).toMatchObject({ spent: 0.3, limit: 0.3, remaining: 0, exceeded: 0 });
    expect(report.trend.map((point) => [point.income, point.expenses, point.net])).toEqual([[0.1, 0.1, 0], [0.2, 0.2, 0]]);
    expect(report.savings).toMatchObject({ current: 0.3, target: 0.9, remaining: 0.6 });
  });
  test.each(['', '2026-02-30', '10000-01-01', 'invalid'])('rejects malformed dates: %s', (startDate) => {
    expect(validateReportSelection({ ...selection, startDate })).toMatch(/valid.*date/i);
  });
  test('does not claim budget compliance or excess without a saved budget', () => {
    const data = source();
    const html = buildFinancialReportHtml(compileFinancialReport(data, selection), data, createReportPdfArtifact('owner', selection, null));
    expect(html).toContain('No budget');
    expect(html).toContain('<span class="">No budget</span>');
    expect(html).not.toMatch(/RM 100\.00 over budget|>Over budget<|>Within budget</);
  });
});
