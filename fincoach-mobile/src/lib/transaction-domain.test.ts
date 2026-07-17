import { describe, expect, test } from 'vitest';

import {
  filterTransactions,
  formatTransactionAmount,
  groupTransactionsByDate,
  validateTransactionInput,
} from '@/lib/transaction-domain';
import type { Category, TransactionWithCategory } from '@/lib/types';

const categories: Category[] = [
  { id: 1, name: 'Food', type: 'expense', icon: 'restaurant', color: '#E45C3A', user_id: null },
  { id: 2, name: 'Income', type: 'income', icon: 'payments', color: '#06a96b', user_id: null },
];

const makeTransaction = (overrides: Partial<TransactionWithCategory>): TransactionWithCategory => ({
  id: '00000000-0000-4000-8000-000000000001',
  user_id: 'user-1',
  category_id: 1,
  amount: 12.5,
  transaction_date: '2026-07-14',
  description: null,
  source: 'Campus Cafe',
  receipt_image_path: null,
  created_at: '2026-07-14T08:00:00Z',
  updated_at: '2026-07-14T08:00:00Z',
  category: categories[0],
  ...overrides,
});

describe('transaction form validation', () => {
  test('requires a positive RM amount, source, and category', () => {
    expect(validateTransactionInput({ type: 'expense', amount: '0', source: '', transactionDate: '2026-07-14', description: '', categoryId: null }, categories, '2026-07-14')).toEqual({
      amount: 'Enter an amount greater than RM 0.',
      source: 'Enter a merchant or income source.',
      categoryId: 'Choose a category.',
    });
  });

  test('rejects future dates and categories from the wrong transaction type', () => {
    expect(validateTransactionInput({ type: 'income', amount: '100', source: 'Allowance', transactionDate: '2026-07-15', description: '', categoryId: 1 }, categories, '2026-07-14')).toMatchObject({
      transactionDate: 'Transaction date cannot be in the future.',
      categoryId: 'Choose an income category.',
    });
  });

  test('limits source and optional description lengths', () => {
    expect(validateTransactionInput({ type: 'expense', amount: '12.50', source: 'x'.repeat(121), transactionDate: '2026-07-14', description: 'x'.repeat(301), categoryId: 1 }, categories, '2026-07-14')).toMatchObject({
      source: 'Source must be 120 characters or fewer.',
      description: 'Note must be 300 characters or fewer.',
    });
  });

  test('accepts a valid income transaction', () => {
    expect(validateTransactionInput({ type: 'income', amount: '1500.00', source: 'Allowance', transactionDate: '2026-07-14', description: 'Monthly support', categoryId: 2 }, categories, '2026-07-14')).toEqual({});
  });
});

describe('transaction history helpers', () => {
  const income = makeTransaction({ id: 'income', category_id: 2, amount: 1500, source: 'Allowance', category: categories[1] });
  const yesterday = makeTransaction({ id: 'yesterday', transaction_date: '2026-07-13' });
  const transactions = [income, makeTransaction({ id: 'expense' }), yesterday];

  test('groups ordered transactions by date', () => {
    expect(groupTransactionsByDate(transactions).map((group) => [group.date, group.items.map((item) => item.id)])).toEqual([
      ['2026-07-14', ['income', 'expense']],
      ['2026-07-13', ['yesterday']],
    ]);
  });

  test('filters by category while All preserves every row', () => {
    expect(filterTransactions(transactions, null)).toHaveLength(3);
    expect(filterTransactions(transactions, 2).map((item) => item.id)).toEqual(['income']);
  });

  test('formats income with a plus sign and expense with a minus sign', () => {
    expect(formatTransactionAmount(income)).toBe('+RM 1,500.00');
    expect(formatTransactionAmount(transactions[1])).toBe('-RM 12.50');
  });
});
