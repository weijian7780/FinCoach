import {
  createCustomCategory,
  deleteCategoryLimit,
  deleteCustomCategory,
  deleteMonthlyBudget,
  fetchBudgetCategories,
  fetchBudgetMonth,
  updateCustomCategory,
  upsertCategoryLimit,
  upsertMonthlyBudget,
} from '@/lib/budget';
import type { BudgetDataClient } from '@/lib/budget';
import { describe, expect, test, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));

type Result = { data: unknown; error: unknown };

function createBuilder(result: Partial<Result> = {}) {
  const response: Result = { data: result.data ?? null, error: result.error ?? null };
  const builder: Record<string, ReturnType<typeof vi.fn>> & {
    then?: (resolve: (value: Result) => unknown, reject?: (reason: unknown) => unknown) => Promise<unknown>;
  } = {
    select: vi.fn(),
    eq: vi.fn(),
    or: vi.fn(),
    order: vi.fn(),
    insert: vi.fn(),
    update: vi.fn(),
    upsert: vi.fn(),
    delete: vi.fn(),
    single: vi.fn(),
    maybeSingle: vi.fn(),
  };
  for (const method of ['select', 'eq', 'or', 'order', 'insert', 'update', 'upsert', 'delete'] as const) {
    builder[method].mockReturnValue(builder);
  }
  builder.single.mockResolvedValue(response);
  builder.maybeSingle.mockResolvedValue(response);
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
  return { client: { from } as unknown as BudgetDataClient, from, builders };
}

const category = {
  id: 1,
  name: 'Food',
  type: 'expense',
  icon: 'restaurant',
  color: '#E45C3A',
  user_id: null,
};

describe('budget month persistence', () => {
  test('loads the parent, limits, and visible categories for one owner and month', async () => {
    const monthlyBudget = { id: 'budget-1', user_id: 'user-1', month: '2026-07-01', limit_amount: 1000 };
    const limit = { id: 2, user_id: 'user-1', category_id: 1, month: '2026-07-01', amount: 300 };
    const { client, builders } = createClient({
      monthly_budgets: { data: monthlyBudget },
      budgets: { data: [limit] },
      categories: { data: [category] },
    });

    await expect(fetchBudgetMonth('user-1', '2026-07-01', client)).resolves.toEqual({
      monthlyBudget,
      categoryLimits: [limit],
      categories: [category],
    });

    expect(builders.get('monthly_budgets')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builders.get('monthly_budgets')?.eq).toHaveBeenCalledWith('month', '2026-07-01');
    expect(builders.get('budgets')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builders.get('budgets')?.eq).toHaveBeenCalledWith('month', '2026-07-01');
    expect(builders.get('categories')?.or).toHaveBeenCalledWith('user_id.is.null,user_id.eq.user-1');
  });

  test('upserts the overall monthly budget by owner and month', async () => {
    const row = { id: 'budget-1' };
    const { client, builders } = createClient({ monthly_budgets: { data: row } });

    await expect(upsertMonthlyBudget('user-1', '2026-07-01', 1000, client)).resolves.toEqual(row);

    expect(builders.get('monthly_budgets')?.upsert).toHaveBeenCalledWith(
      { user_id: 'user-1', month: '2026-07-01', limit_amount: 1000 },
      { onConflict: 'user_id,month' },
    );
  });

  test('upserts one category limit by owner, category, and month', async () => {
    const { client, builders } = createClient({ budgets: { data: { id: 2 } } });
    await upsertCategoryLimit('user-1', '2026-07-01', 1, 300, client);
    expect(builders.get('budgets')?.upsert).toHaveBeenCalledWith(
      { user_id: 'user-1', month: '2026-07-01', category_id: 1, amount: 300 },
      { onConflict: 'user_id,category_id,month' },
    );
  });

  test('deletes parent and category limits only with owner filters', async () => {
    const first = createClient();
    await deleteMonthlyBudget('budget-1', 'user-1', first.client);
    expect(first.builders.get('monthly_budgets')?.eq).toHaveBeenCalledWith('id', 'budget-1');
    expect(first.builders.get('monthly_budgets')?.eq).toHaveBeenCalledWith('user_id', 'user-1');

    const second = createClient();
    await deleteCategoryLimit(2, 'user-1', second.client);
    expect(second.builders.get('budgets')?.eq).toHaveBeenCalledWith('id', 2);
    expect(second.builders.get('budgets')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });
});

describe('custom category persistence', () => {
  test('lists only visible expense categories in name order', async () => {
    const { client, builders } = createClient({ categories: { data: [category] } });
    await expect(fetchBudgetCategories('user-1', client)).resolves.toEqual([category]);
    expect(builders.get('categories')?.eq).toHaveBeenCalledWith('type', 'expense');
    expect(builders.get('categories')?.or).toHaveBeenCalledWith('user_id.is.null,user_id.eq.user-1');
    expect(builders.get('categories')?.order).toHaveBeenCalledWith('name', { ascending: true });
  });

  test('creates and updates only user-owned custom expense categories', async () => {
    const input = { name: 'Groceries', icon: 'shopping-cart', color: '#00897B' };
    const created = createClient({ categories: { data: { id: 7 } } });
    await createCustomCategory('user-1', input, created.client);
    expect(created.builders.get('categories')?.insert).toHaveBeenCalledWith({
      ...input,
      type: 'expense',
      user_id: 'user-1',
    });

    const updated = createClient({ categories: { data: { id: 7 } } });
    await updateCustomCategory(7, 'user-1', input, updated.client);
    expect(updated.builders.get('categories')?.eq).toHaveBeenCalledWith('id', 7);
    expect(updated.builders.get('categories')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });

  test('deletes only a user-owned custom category', async () => {
    const { client, builders } = createClient();
    await deleteCustomCategory(7, 'user-1', client);
    expect(builders.get('categories')?.eq).toHaveBeenCalledWith('id', 7);
    expect(builders.get('categories')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });

  test('propagates Supabase failures', async () => {
    const error = new Error('RLS denied');
    const { client } = createClient({ categories: { error } });
    await expect(fetchBudgetCategories('user-1', client)).rejects.toBe(error);
  });
});
