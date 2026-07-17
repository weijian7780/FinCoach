import { describe, expect, test, vi } from 'vitest';

vi.mock('./alerts', () => ({
  createIdempotentAlert: vi.fn(),
  ensureNotificationPreferences: vi.fn(),
}));
vi.mock('./budget', () => ({ fetchBudgetMonth: vi.fn() }));
vi.mock('./transactions', () => ({ fetchTransactions: vi.fn() }));

import { emitBudgetAlertsAfterTransactionChange, emitSavingsMilestonesAfterContribution } from './alert-events';

const expenseCategory = { id: 4, name: 'Food', type: 'expense', color: '#f00', icon: 'restaurant', user_id: null, created_at: '' } as const;
const incomeCategory = { ...expenseCategory, id: 8, name: 'Income', type: 'income' } as const;
const tx = (amount: number, category: typeof expenseCategory | typeof incomeCategory = expenseCategory) => ({ id: crypto.randomUUID(), user_id: 'u1', category_id: category.id, amount, transaction_date: '2026-07-15', description: null, source: 'Test', receipt_image_path: null, created_at: '', updated_at: '', category });
const preferences: any = { budget_enabled: true, savings_enabled: true, savings_milestones_enabled: true };

describe('automatic alert events', () => {
  test('budget evaluation ignores disabled preferences and income transactions', async () => {
    const createAlert = vi.fn();
    const base = { fetchPreferences: vi.fn().mockResolvedValue({ ...preferences, budget_enabled: false }), fetchTransactions: vi.fn().mockResolvedValue([]), fetchBudgetMonth: vi.fn(), createAlert };
    await emitBudgetAlertsAfterTransactionChange('u1', null, tx(90), base);
    expect(createAlert).not.toHaveBeenCalled();

    await emitBudgetAlertsAfterTransactionChange('u1', null, tx(90, incomeCategory), { ...base, fetchPreferences: vi.fn().mockResolvedValue(preferences) });
    expect(createAlert).not.toHaveBeenCalled();
  });

  test('creates distinct overall and category 80 percent warnings', async () => {
    const current = tx(85);
    const createAlert = vi.fn().mockResolvedValue({});
    await emitBudgetAlertsAfterTransactionChange('u1', null, current, {
      fetchPreferences: vi.fn().mockResolvedValue(preferences),
      fetchTransactions: vi.fn().mockResolvedValue([current]),
      fetchBudgetMonth: vi.fn().mockResolvedValue({ monthlyBudget: { id: 'mb1', limit_amount: 100, month: '2026-07-01' }, categoryLimits: [{ id: 10, category_id: 4, amount: 100, month: '2026-07-01' }], categories: [expenseCategory] }),
      createAlert,
    });
    expect(createAlert).toHaveBeenCalledTimes(2);
    expect(createAlert.mock.calls.map((call) => call[1].dedupe_key)).toEqual(expect.arrayContaining(['budget:overall:mb1:2026-07-01:warning', 'budget:category:10:2026-07-01:warning']));
  });

  test('a direct jump past 100 percent creates exceeded rather than warning', async () => {
    const current = tx(120);
    const createAlert = vi.fn().mockResolvedValue({});
    await emitBudgetAlertsAfterTransactionChange('u1', null, current, {
      fetchPreferences: vi.fn().mockResolvedValue(preferences), fetchTransactions: vi.fn().mockResolvedValue([current]),
      fetchBudgetMonth: vi.fn().mockResolvedValue({ monthlyBudget: { id: 'mb1', limit_amount: 100, month: '2026-07-01' }, categoryLimits: [], categories: [expenseCategory] }), createAlert,
    });
    expect(createAlert).toHaveBeenCalledTimes(1);
    expect(createAlert.mock.calls[0][1].type).toBe('budget_exceeded');
  });

  test('transaction edits evaluate the previous and new category/month buckets', async () => {
    const previous = tx(30);
    const current = { ...tx(90), id: previous.id };
    const createAlert = vi.fn().mockResolvedValue({});
    await emitBudgetAlertsAfterTransactionChange('u1', previous, current, {
      fetchPreferences: vi.fn().mockResolvedValue(preferences), fetchTransactions: vi.fn().mockResolvedValue([current]),
      fetchBudgetMonth: vi.fn().mockResolvedValue({ monthlyBudget: { id: 'mb1', limit_amount: 100, month: '2026-07-01' }, categoryLimits: [], categories: [expenseCategory] }), createAlert,
    });
    expect(createAlert).toHaveBeenCalledTimes(1);
  });

  test('savings creates every newly crossed milestone and respects settings', async () => {
    const createAlert = vi.fn().mockResolvedValue({});
    const goal = { id: 'g1', user_id: 'u1', name: 'Laptop', target_amount: 1000, current_amount: 800, deadline: null, created_at: '', updated_at: '' };
    await emitSavingsMilestonesAfterContribution('u1', goal, 200, 800, { fetchPreferences: vi.fn().mockResolvedValue(preferences), createAlert });
    expect(createAlert.mock.calls.map((call) => call[1].dedupe_key)).toEqual(['savings:g1:milestone:25', 'savings:g1:milestone:50', 'savings:g1:milestone:75']);

    createAlert.mockClear();
    await emitSavingsMilestonesAfterContribution('u1', goal, 800, 1000, { fetchPreferences: vi.fn().mockResolvedValue({ ...preferences, savings_milestones_enabled: false }), createAlert });
    expect(createAlert).not.toHaveBeenCalled();
  });
});
