import { describe, expect, test, vi } from 'vitest';

import {
  createReportRecord,
  fetchRecentReports,
  fetchReportSourceData,
  type ReportDataClient,
} from './reports';
import type { ReportSelection } from './types';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));

type Result = { data: unknown; error: unknown };

function createBuilder(result: Partial<Result> = {}) {
  const response: Result = { data: result.data ?? null, error: result.error ?? null };
  const builder: Record<string, ReturnType<typeof vi.fn>> & {
    then?: (resolve: (value: Result) => unknown, reject?: (reason: unknown) => unknown) => Promise<unknown>;
  } = {
    select: vi.fn(),
    eq: vi.fn(),
    gte: vi.fn(),
    lte: vi.fn(),
    order: vi.fn(),
    limit: vi.fn(),
    insert: vi.fn(),
    single: vi.fn(),
  };
  for (const method of ['select', 'eq', 'gte', 'lte', 'order', 'limit', 'insert'] as const) {
    builder[method].mockReturnValue(builder);
  }
  builder.single.mockResolvedValue(response);
  builder.then = (resolve, reject) => Promise.resolve(response).then(resolve, reject);
  return builder;
}

function createClient(results: Record<string, Partial<Result>> = {}) {
  const builders = new Map<string, ReturnType<typeof createBuilder>>();
  const from = vi.fn((table: string) => {
    const builder = createBuilder(results[table]);
    builders.set(table, builder);
    return builder;
  });
  return { client: { from } as unknown as ReportDataClient, from, builders };
}

const selection: ReportSelection = {
  preset: 'last_3_months',
  startDate: '2026-05-01',
  endDate: '2026-07-31',
  categoryId: null,
  reportType: 'multi_month',
};

describe('report source persistence', () => {
  test('loads all financial sources with owner and bounded date filters', async () => {
    const transactions = [{ id: 't1' }];
    const monthlyBudgets = [{ id: 'm1' }];
    const categoryLimits = [{ id: 1 }];
    const savingsGoals = [{ id: 'g1' }];
    const { client, builders } = createClient({
      transactions: { data: transactions },
      monthly_budgets: { data: monthlyBudgets },
      budgets: { data: categoryLimits },
      savings_goals: { data: savingsGoals },
    });

    await expect(fetchReportSourceData('user-1', selection, client)).resolves.toEqual({
      transactions,
      monthlyBudgets,
      categoryLimits,
      savingsGoals,
    });

    const transactionsQuery = builders.get('transactions');
    expect(transactionsQuery?.select).toHaveBeenCalledWith('*, category:categories(*)');
    expect(transactionsQuery?.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(transactionsQuery?.gte).toHaveBeenCalledWith('transaction_date', '2026-05-01');
    expect(transactionsQuery?.lte).toHaveBeenCalledWith('transaction_date', '2026-07-31');
    expect(transactionsQuery?.order).toHaveBeenCalledWith('transaction_date', { ascending: true });

    for (const table of ['monthly_budgets', 'budgets'] as const) {
      expect(builders.get(table)?.eq).toHaveBeenCalledWith('user_id', 'user-1');
      expect(builders.get(table)?.gte).toHaveBeenCalledWith('month', '2026-05-01');
      expect(builders.get(table)?.lte).toHaveBeenCalledWith('month', '2026-07-01');
    }
    expect(builders.get('savings_goals')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });

  test('rejects the complete source request when any source fails', async () => {
    const error = new Error('Budgets unavailable');
    const { client } = createClient({ budgets: { error } });
    await expect(fetchReportSourceData('user-1', selection, client)).rejects.toBe(error);
  });

  test('inserts immutable owner-scoped report metadata', async () => {
    const row = {
      id: 5,
      user_id: 'user-1',
      period: '2026-05..2026-07',
      type: 'multi_month',
      generated_at: '2026-07-16T08:00:00Z',
    };
    const { client, builders } = createClient({ reports: { data: row } });
    await expect(createReportRecord('user-1', selection, client)).resolves.toEqual(row);
    expect(builders.get('reports')?.insert).toHaveBeenCalledWith({
      user_id: 'user-1',
      period: '2026-05..2026-07',
      type: 'multi_month',
    });
    expect(builders.get('reports')?.select).toHaveBeenCalledWith('*');
  });

  test('retrieves recent history with owner, ordering, and a bounded limit', async () => {
    const reports = [{ id: 5 }];
    const { client, builders } = createClient({ reports: { data: reports } });
    await expect(fetchRecentReports('user-1', 10, client)).resolves.toEqual(reports);
    expect(builders.get('reports')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builders.get('reports')?.order).toHaveBeenCalledWith('generated_at', { ascending: false });
    expect(builders.get('reports')?.limit).toHaveBeenCalledWith(10);
  });

  test('clamps history limits to prevent unbounded reads', async () => {
    const { client, builders } = createClient({ reports: { data: [] } });
    await fetchRecentReports('user-1', 500, client);
    expect(builders.get('reports')?.limit).toHaveBeenCalledWith(50);
  });
});
