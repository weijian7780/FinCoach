import { fetchAllRows } from '@/lib/pagination';
import { monthKeysForRange, requireValidReportSelection } from '@/lib/report-domain';
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

type QueryResult = { data: unknown; error: unknown; count?: number | null };

type ReportQuery = PromiseLike<QueryResult> & {
  range: (from: number, to: number) => ReportQuery;
  eq: (column: string, value: unknown) => ReportQuery;
  gte: (column: string, value: unknown) => ReportQuery;
  insert: (value: Record<string, unknown>) => ReportQuery;
  limit: (value: number) => ReportQuery;
  lte: (column: string, value: unknown) => ReportQuery;
  order: (column: string, options: Record<string, unknown>) => ReportQuery;
  select: (...args: unknown[]) => ReportQuery;
  single: () => Promise<QueryResult>;
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

export async function fetchReportSourceData(
  userId: string,
  selection: ReportSelection,
  client: ReportDataClient = defaultClient,
): Promise<ReportSourceData> {
  requireValidReportSelection(selection);
  let previous: string | undefined;
  // Agreement detects ordinary pagination/edit races, not a database snapshot.
  // Three full reads bound traffic when records continue changing.
  for (let pass = 0; pass < 3; pass++) {
    const source = await fetchReportSourceOnce(userId, selection, client);
    const fingerprint = await reportFingerprint(userId, selection, source);
    if (fingerprint === previous) return source;
    previous = fingerprint;
  }
  throw new ReportDataChangedError();
}

export class ReportDataChangedError extends Error {
  constructor() { super('Financial data changed while loading. Please retry.'); this.name = 'ReportDataChangedError'; }
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return Object.fromEntries(Object.keys(record).sort().map((key) => [key, canonical(record[key])]));
  }
  return value;
}

async function reportFingerprint(userId: string, selection: ReportSelection, source: ReportSourceData) {
  const normalized = Object.fromEntries(Object.entries(source).map(([key, rows]) => [key,
    [...rows].sort((a, b) => String(a.id).localeCompare(String(b.id))).map(canonical),
  ]));
  const Crypto = await import('expo-crypto');
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,
    JSON.stringify(canonical({ userId, selection, source: normalized })));
}

async function fetchReportSourceOnce(userId: string, selection: ReportSelection, client: ReportDataClient): Promise<ReportSourceData> {
  const months = monthKeysForRange(selection.startDate, selection.endDate);
  if (!months.length) throw new Error('The report period is invalid.');
  const firstMonth = months[0];
  const lastMonth = months[months.length - 1];

  const [transactions, monthlyBudgets, categoryLimits, savingsGoals] = await Promise.all([
    fetchAllRows<TransactionWithCategory>(() =>
      client
        .from('transactions')
        .select(transactionSelection, { count: 'exact' })
        .eq('user_id', userId)
        .gte('transaction_date', selection.startDate)
        .lte('transaction_date', selection.endDate)
        .order('transaction_date', { ascending: true }).order('id', { ascending: true }),
    ),
    fetchAllRows<MonthlyBudget>(() =>
      client
        .from('monthly_budgets')
        .select('*', { count: 'exact' })
        .eq('user_id', userId)
        .gte('month', firstMonth)
        .lte('month', lastMonth)
        .order('month', { ascending: true }).order('id', { ascending: true }),
    ),
    fetchAllRows<CategoryLimit>(() =>
      client
        .from('budgets')
        .select('*', { count: 'exact' })
        .eq('user_id', userId)
        .gte('month', firstMonth)
        .lte('month', lastMonth)
        .order('month', { ascending: true }).order('id', { ascending: true }),
    ),
    fetchAllRows<SavingsGoal>(() =>
      client
        .from('savings_goals')
        .select('*', { count: 'exact' })
        .eq('user_id', userId)
        .order('created_at', { ascending: true }).order('id', { ascending: true }),
    ),
  ]);

  return { transactions, monthlyBudgets, categoryLimits, savingsGoals };
}

export async function uploadReportPdf(
  path: string,
  bytes: ArrayBuffer,
  client: ReportDataClient = defaultClient,
) {
  // The path is reserved by one server-issued attempt, so an existing object is
  // that attempt's own earlier upload (or an old file). Never overwrite it.
  const { data, error } = await client.storage
    .from(reportBucket)
    .upload(path, bytes, {
      contentType: 'application/pdf',
      upsert: false,
    });
  throwIfError(error);
  return requireRow<{ path: string }>(
    data,
    'The uploaded report PDF was not returned.',
  );
}

/** Supabase reports a non-overwriting upload onto an existing object as a conflict. */
export function isDuplicateReportUploadError(error: unknown) {
  if (!error || typeof error !== 'object') return false;
  const statusCode = (error as { statusCode?: unknown }).statusCode;
  if (statusCode === 409 || statusCode === '409') return true;
  const message = (error as { message?: unknown }).message;
  return typeof message === 'string' && /already exists|duplicate/i.test(message);
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

// Resolve the current owner-scoped history path: restore may relocate its PDF
// while preserving the report id and the original embedded coach-card payload.
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
