import { formatReportPeriod, monthKeysForRange } from '@/lib/report-domain';
import type { ReportPdfArtifact } from '@/lib/report-pdf';
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
  upsert: (
    value: Record<string, unknown>,
    options: { onConflict: string },
  ) => ReportQuery;
};

type ReportStorageBucket = {
  upload: (
    path: string,
    body: ArrayBuffer,
    options: { contentType: string; upsert: boolean },
  ) => Promise<QueryResult>;
  createSignedUrl: (
    path: string,
    expiresIn: number,
  ) => Promise<QueryResult>;
};

export type ReportDataClient = {
  from: (table: string) => ReportQuery;
  storage: { from: (bucket: string) => ReportStorageBucket };
};

const defaultClient = supabase as unknown as ReportDataClient;
const transactionSelection = '*, category:categories(*)';
const reportBucket = 'financial-reports';

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

export async function saveReportRecord(
  userId: string,
  selection: ReportSelection,
  artifact: ReportPdfArtifact,
  client: ReportDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('reports')
    .upsert({
      user_id: userId,
      period: formatReportPeriod(selection),
      type: selection.reportType,
      title: artifact.title,
      file_name: artifact.fileName,
      storage_path: artifact.storagePath,
      report_key: artifact.reportKey,
      start_date: selection.startDate,
      end_date: selection.endDate,
      category_id: selection.categoryId,
      generated_at: artifact.generatedAt,
    }, {
      onConflict: 'user_id,report_key',
    })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<Report>(
    data,
    'The PDF was generated but its history record was not returned.',
  );
}

export async function uploadReportPdf(
  path: string,
  bytes: ArrayBuffer,
  client: ReportDataClient = defaultClient,
) {
  const { data, error } = await client.storage
    .from(reportBucket)
    .upload(path, bytes, {
      contentType: 'application/pdf',
      upsert: true,
    });
  throwIfError(error);
  return requireRow<{ path: string }>(
    data,
    'The uploaded report PDF was not returned.',
  );
}

export async function createReportSignedUrl(
  path: string,
  expiresIn = 600,
  client: ReportDataClient = defaultClient,
) {
  const safeExpiry = Math.max(60, Math.min(3600, Math.trunc(expiresIn) || 600));
  const { data, error } = await client.storage
    .from(reportBucket)
    .createSignedUrl(path, safeExpiry);
  throwIfError(error);
  const result = requireRow<{ signedUrl?: string }>(
    data,
    'The report PDF link was not returned.',
  );
  if (!result.signedUrl) throw new Error('The report PDF link was not returned.');
  return result.signedUrl;
}

// Reports generated before the coach card carried `storage_path` only recorded a
// report id, so the path is looked up from the owner-scoped history row instead.
export async function fetchReportStoragePath(
  reportId: number,
  client: ReportDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('reports')
    .select('storage_path')
    .eq('id', reportId)
    .single();
  throwIfError(error);
  const row = requireRow<{ storage_path: string | null }>(
    data,
    'That report is no longer in your history.',
  );
  if (!row.storage_path) throw new Error('That report has no stored PDF file.');
  return row.storage_path;
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
