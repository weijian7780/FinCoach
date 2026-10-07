import { describe, expect, it } from 'vitest';

import { buildCoachInsightCards } from './coach-insights';
import type {
  MonthlyBudget,
  SavingsGoal,
  TransactionWithCategory,
} from './types';

const monthlyBudget = (limitAmount: number): MonthlyBudget => ({
  id: 'budget-1',
  user_id: 'user-1',
  month: '2026-07-01',
  limit_amount: limitAmount,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
});

const expense = (
  id: string,
  amount: number,
  categoryId: number,
  categoryName: string,
): TransactionWithCategory => ({
  id,
  user_id: 'user-1',
  category_id: categoryId,
  amount,
  transaction_date: '2026-07-12',
  description: null,
  source: 'manual',
  receipt_image_path: null,
  created_at: '2026-07-12T00:00:00Z',
  updated_at: '2026-07-12T00:00:00Z',
  category: {
    id: categoryId,
    user_id: null,
    name: categoryName,
    type: 'expense',
    icon: null,
    color: null,
  },
});

const savingsGoal = (): SavingsGoal => ({
  id: 'goal-1',
  user_id: 'user-1',
  name: 'Laptop',
  target_amount: 1000,
  current_amount: 250,
  deadline: '2026-12-31',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
});

describe('Coach contextual insights', () => {
  it('uses clear healthy, warning, and exceeded budget states with remaining MYR', () => {
    const now = new Date(2026, 6, 17);

    expect(buildCoachInsightCards({
      monthlyBudget: monthlyBudget(500),
      transactions: [expense('food-1', 200, 1, 'Food')],
      savingsGoals: [],
      now,
    })[0]).toMatchObject({
      id: 'budget',
      tone: 'healthy',
      title: 'RM300.00 remaining',
    });

    expect(buildCoachInsightCards({
      monthlyBudget: monthlyBudget(500),
      transactions: [expense('food-1', 450, 1, 'Food')],
      savingsGoals: [],
      now,
    })[0]).toMatchObject({
      id: 'budget',
      tone: 'warning',
      title: 'RM50.00 remaining',
    });

    expect(buildCoachInsightCards({
      monthlyBudget: monthlyBudget(500),
      transactions: [expense('food-1', 550, 1, 'Food')],
      savingsGoals: [],
      now,
    })[0]).toMatchObject({
      id: 'budget',
      tone: 'critical',
      title: 'RM50.00 over budget',
    });
  });

  it('summarizes the top recorded category and an active savings goal', () => {
    const cards = buildCoachInsightCards({
      monthlyBudget: null,
      transactions: [
        expense('food-1', 80, 1, 'Food'),
        expense('food-2', 70, 1, 'Food'),
        expense('travel-1', 40, 2, 'Transport'),
      ],
      savingsGoals: [savingsGoal()],
      now: new Date(2026, 6, 17),
    });

    expect(cards).toEqual([
      expect.objectContaining({
        id: 'spending',
        title: 'Food: RM150.00',
        prompt: 'How can I reduce Food spending?',
      }),
      expect.objectContaining({
        id: 'savings',
        title: 'RM750.00 to Laptop',
        detail: expect.stringContaining('25% saved'),
        prompt: 'Am I on track for my Laptop goal?',
      }),
    ]);
  });

  it('does not derive spending insights when transaction consent is absent', () => {
    const cards = buildCoachInsightCards({
      monthlyBudget: monthlyBudget(500),
      transactions: [expense('food-1', 200, 1, 'Food')],
      savingsGoals: [savingsGoal()],
      includeRecordedSpending: false,
      now: new Date(2026, 6, 17),
    });

    expect(cards.map((card) => card.id)).toEqual(['savings']);
  });
});
