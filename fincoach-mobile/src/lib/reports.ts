import { formatReportPeriod, monthKeysForRange } from '@/lib/report-domain';
import { supabase } from '@/lib/supabase';
import type {
  CategoryLimit,
  MonthlyBudget,
  Report,
  ReportSelection,
  ReportSourceData,
  SavingsGoal,
  TransactionWithCategory,
} from '@/lib/types';

type QueryResult = { data: unknown; error: unknown };

type ReportQuery = PromiseLike<QueryResult> & {
  eq: (column: string, value: unknown) => ReportQuery;
  gte: (column: string, value: unknown) => ReportQuery;
  insert: (value: Record<string, unknown>) => ReportQuery;
  limit: (value: number) => ReportQuery;
  lte: (column: string, value: unknown) => ReportQuery;
  order: (column: string, options: Record<string, unknown>) => ReportQuery;
  select: (...args: unknown[]) => ReportQuery;
  single: () => Promise<QueryResult>;
};

export type ReportDataClient = {
  from: (table: string) => ReportQuery;
};

const defaultClient = supabase as unknown as ReportDataClient;
const transactionSelection = '*, category:categories(*)';

function throwIfError(error: unknown) {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string) {
  if (!data) throw new Error(message);
  return data as T;
}

async function requireRows<T>(query: ReportQuery) {
  const { data, error } = await query;
  throwIfError(error);
  return (data ?? []) as T[];
}

export async function fetchReportSourceData(
  userId: string,
  selection: ReportSelection,
  client: ReportDataClient = defaultClient,
): Promise<ReportSourceData> {
  const months = monthKeysForRange(selection.startDate, selection.endDate);
  if (!months.length) throw new Error('The report period is invalid.');
  const firstMonth = months[0];
  const lastMonth = months[months.length - 1];

  const [transactions, monthlyBudgets, categoryLimits, savingsGoals] = await Promise.all([
    requireRows<TransactionWithCategory>(
      client
        .from('transactions')
        .select(transactionSelection)
        .eq('user_id', userId)
        .gte('transaction_date', selection.startDate)
        .lte('transaction_date', selection.endDate)
        .order('transaction_date', { ascending: true }),
    ),
    requireRows<MonthlyBudget>(
      client
        .from('monthly_budgets')
        .select('*')
        .eq('user_id', userId)
        .gte('month', firstMonth)
        .lte('month', lastMonth)
        .order('month', { ascending: true }),
    ),
    requireRows<CategoryLimit>(
      client
        .from('budgets')
        .select('*')
        .eq('user_id', userId)
        .gte('month', firstMonth)
        .lte('month', lastMonth)
        .order('month', { ascending: true }),
    ),
    requireRows<SavingsGoal>(
      client
        .from('savings_goals')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: true }),
    ),
  ]);

  return { transactions, monthlyBudgets, categoryLimits, savingsGoals };
}

export async function createReportRecord(
  userId: string,
  selection: ReportSelection,
  client: ReportDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('reports')
    .insert({
      user_id: userId,
      period: formatReportPeriod(selection),
      type: selection.reportType,
    })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<Report>(data, 'The report was generated but its history record was not returned.');
}

export async function fetchRecentReports(
  userId: string,
  limit = 10,
  client: ReportDataClient = defaultClient,
) {
  const safeLimit = Math.max(1, Math.min(50, Math.trunc(limit) || 10));
  const { data, error } = await client
    .from('reports')
    .select('*')
    .eq('user_id', userId)
    .order('generated_at', { ascending: false })
    .limit(safeLimit);
  throwIfError(error);
  return (data ?? []) as Report[];
}
