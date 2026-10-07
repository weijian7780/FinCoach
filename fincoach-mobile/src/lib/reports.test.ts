import { describe, expect, test, vi } from 'vitest';

import {
  createReportSignedUrl,
  fetchRecentReports,
  fetchReportSourceData,
  fetchReportStoragePath,
  saveReportRecord,
  uploadReportPdf,
  type ReportDataClient,
} from './reports';
import type { ReportPdfArtifact } from './report-pdf';
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
    upsert: vi.fn(),
    single: vi.fn(),
  };
  for (const method of ['select', 'eq', 'gte', 'lte', 'order', 'limit', 'insert', 'upsert'] as const) {
    builder[method].mockReturnValue(builder);
  }
  builder.single.mockResolvedValue(response);
  builder.then = (resolve, reject) => Promise.resolve(response).then(resolve, reject);
  return builder;
}

function createClient(results: Record<string, Partial<Result>> = {}) {
  const builders = new Map<string, ReturnType<typeof createBuilder>>();
  const upload = vi.fn().mockResolvedValue({
    data: { path: 'user-1/monthly-2026-07.pdf' },
    error: null,
  });
  const createSignedUrl = vi.fn().mockResolvedValue({
    data: { signedUrl: 'https://example.supabase.co/report.pdf?token=signed' },
    error: null,
  });
  const storageFrom = vi.fn().mockReturnValue({ upload, createSignedUrl });
  const from = vi.fn((table: string) => {
    const builder = createBuilder(results[table]);
    builders.set(table, builder);
    return builder;
  });
  return {
    client: {
      from,
      storage: { from: storageFrom },
    } as unknown as ReportDataClient,
    from,
    builders,
    storageFrom,
    upload,
    createSignedUrl,
  };
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

  test('upserts one owner-scoped PDF record for the same report selection', async () => {
    const row = {
      id: 5,
      user_id: 'user-1',
      period: '2026-05..2026-07',
      type: 'multi_month',
      title: 'May - July 2026 Financial Summary',
      file_name: 'FinCoach_May_July_2026_Financial_Summary.pdf',
      storage_path: 'user-1/multi-month-2026-05-01-2026-07-31-all.pdf',
      report_key: 'multi_month:2026-05-01:2026-07-31:all',
      start_date: '2026-05-01',
      end_date: '2026-07-31',
      category_id: null,
      generated_at: '2026-07-16T08:00:00Z',
    };
    const artifact: ReportPdfArtifact = {
      title: row.title,
      fileName: row.file_name,
      storagePath: row.storage_path,
      reportKey: row.report_key,
      generatedAt: row.generated_at,
    };
    const { client, builders } = createClient({ reports: { data: row } });
    await expect(saveReportRecord('user-1', selection, artifact, client)).resolves.toEqual(row);
    expect(builders.get('reports')?.upsert).toHaveBeenCalledWith({
      user_id: 'user-1',
      period: '2026-05..2026-07',
      type: 'multi_month',
      title: artifact.title,
      file_name: artifact.fileName,
      storage_path: artifact.storagePath,
      report_key: artifact.reportKey,
      start_date: '2026-05-01',
      end_date: '2026-07-31',
      category_id: null,
      generated_at: artifact.generatedAt,
    }, {
      onConflict: 'user_id,report_key',
    });
    expect(builders.get('reports')?.select).toHaveBeenCalledWith('*');
  });

  test('uploads the PDF to the private financial-reports bucket with overwrite enabled', async () => {
    const { client, storageFrom, upload } = createClient();
    const bytes = new ArrayBuffer(8);

    await expect(
      uploadReportPdf('user-1/monthly-2026-07.pdf', bytes, client),
    ).resolves.toEqual({ path: 'user-1/monthly-2026-07.pdf' });

    expect(storageFrom).toHaveBeenCalledWith('financial-reports');
    expect(upload).toHaveBeenCalledWith(
      'user-1/monthly-2026-07.pdf',
      bytes,
      { contentType: 'application/pdf', upsert: true },
    );
  });

  test('creates a short-lived URL for opening a private report PDF', async () => {
    const { client, storageFrom, createSignedUrl } = createClient();

    await expect(
      createReportSignedUrl('user-1/monthly-2026-07.pdf', 600, client),
    ).resolves.toBe('https://example.supabase.co/report.pdf?token=signed');

    expect(storageFrom).toHaveBeenCalledWith('financial-reports');
    expect(createSignedUrl).toHaveBeenCalledWith(
      'user-1/monthly-2026-07.pdf',
      600,
    );
  });

  test('recovers the storage path of an older report from its history row', async () => {
    const { client, builders } = createClient({
      reports: { data: { storage_path: 'user-1/monthly-2026-07.pdf' } },
    });

    await expect(fetchReportStoragePath(42, client)).resolves.toBe(
      'user-1/monthly-2026-07.pdf',
    );
    expect(builders.get('reports')?.eq).toHaveBeenCalledWith('id', 42);
  });

  test('reports a clear reason when a history row has no stored PDF', async () => {
    const { client } = createClient({ reports: { data: { storage_path: null } } });

    await expect(fetchReportStoragePath(42, client)).rejects.toThrow(
      'That report has no stored PDF file.',
    );
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
