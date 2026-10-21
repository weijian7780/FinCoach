import { supabase } from '@/lib/supabase';
import type {
  BudgetMonthData,
  Category,
  CategoryLimit,
  CustomCategoryInput,
  MonthlyBudget,
} from '@/lib/types';

type QueryResult = { data: unknown; error: unknown };

type BudgetQuery = PromiseLike<QueryResult> & {
  delete: () => BudgetQuery;
  eq: (column: string, value: unknown) => BudgetQuery;
  insert: (value: Record<string, unknown>) => BudgetQuery;
  maybeSingle: () => Promise<QueryResult>;
  or: (filters: string) => BudgetQuery;
  order: (column: string, options: Record<string, unknown>) => BudgetQuery;
  select: (...args: unknown[]) => BudgetQuery;
  single: () => Promise<QueryResult>;
  update: (value: Record<string, unknown>) => BudgetQuery;
  upsert: (value: Record<string, unknown>, options: Record<string, unknown>) => BudgetQuery;
};

export type BudgetDataClient = {
  from: (table: string) => BudgetQuery;
};

const defaultClient = supabase as unknown as BudgetDataClient;

function throwIfError(error: unknown) {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string) {
  if (!data) throw new Error(message);
  return data as T;
}

export async function fetchMonthlyBudget(
  userId: string,
  month: string,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('monthly_budgets')
    .select('*')
    .eq('user_id', userId)
    .eq('month', month)
    .maybeSingle();
  throwIfError(error);
  return data as MonthlyBudget | null;
}

export async function fetchCategoryLimits(
  userId: string,
  month: string,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('budgets')
    .select('*')
    .eq('user_id', userId)
    .eq('month', month)
    .order('created_at', { ascending: true });
  throwIfError(error);
  return (data ?? []) as CategoryLimit[];
}

export async function fetchBudgetCategories(
  userId: string,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('categories')
    .select('*')
    .eq('type', 'expense')
    .or(`user_id.is.null,user_id.eq.${userId}`)
    .order('name', { ascending: true });
  throwIfError(error);
  return (data ?? []) as Category[];
}

export async function fetchBudgetMonth(
  userId: string,
  month: string,
  client: BudgetDataClient = defaultClient,
): Promise<BudgetMonthData> {
  const [monthlyBudget, categoryLimits, categories] = await Promise.all([
    fetchMonthlyBudget(userId, month, client),
    fetchCategoryLimits(userId, month, client),
    fetchBudgetCategories(userId, client),
  ]);
  return { monthlyBudget, categoryLimits, categories };
}

export async function upsertMonthlyBudget(
  userId: string,
  month: string,
  limitAmount: number,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('monthly_budgets')
    .upsert(
      { user_id: userId, month, limit_amount: limitAmount },
      { onConflict: 'user_id,month' },
    )
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<MonthlyBudget>(data, 'Monthly budget was saved but no row was returned.');
}

export async function deleteMonthlyBudget(
  budgetId: string,
  userId: string,
  client: BudgetDataClient = defaultClient,
) {
  const { error } = await client
    .from('monthly_budgets')
    .delete()
    .eq('id', budgetId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function upsertCategoryLimit(
  userId: string,
  month: string,
  categoryId: number,
  amount: number,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('budgets')
    .upsert(
      { user_id: userId, month, category_id: categoryId, amount },
      { onConflict: 'user_id,category_id,month' },
    )
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<CategoryLimit>(data, 'Category limit was saved but no row was returned.');
}

export async function deleteCategoryLimit(
  limitId: number,
  userId: string,
  client: BudgetDataClient = defaultClient,
) {
  const { error } = await client
    .from('budgets')
    .delete()
    .eq('id', limitId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function createCustomCategory(
  userId: string,
  input: CustomCategoryInput,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('categories')
    .insert({ ...input, type: 'expense', user_id: userId })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<Category>(data, 'Category was created but no row was returned.');
}

export async function updateCustomCategory(
  categoryId: number,
  userId: string,
  input: CustomCategoryInput,
  client: BudgetDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('categories')
    .update({ ...input, type: 'expense' })
    .eq('id', categoryId)
    .eq('user_id', userId)
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<Category>(data, 'Category was updated but no row was returned.');
}

export async function deleteCustomCategory(
  categoryId: number,
  userId: string,
  client: BudgetDataClient = defaultClient,
) {
  const { error } = await client
    .from('categories')
    .delete()
    .eq('id', categoryId)
    .eq('user_id', userId);
  throwIfError(error);
}

/** One RPC commits the parent and all category allocations together. */
export async function saveBudgetMonth(userId: string, month: string, overall: number, allocations: { category_id: number; amount: number }[]) {
  const { error } = await supabase.rpc('save_budget_month', { p_user_id: userId, p_month: month, p_overall: overall, p_allocations: allocations });
  if (error) throw error;
}
