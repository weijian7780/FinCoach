import { describe, expect, test, vi } from 'vitest';

import {
  createDataExport,
  fetchBackupSourceData,
  restoreFinancialBackup,
  saveExportContents,
  updateAutoBackupEnabled,
  uploadBackupObject,
  type ExportBackupDataClient,
} from './export-backup';
import type { ExportSelection, FinancialBackupDocumentV1 } from './types';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));

type Result = { data: unknown; error: unknown };

function createBuilder(result: Partial<Result> = {}) {
  const response: Result = { data: result.data ?? null, error: result.error ?? null };
  const builder: Record<string, ReturnType<typeof vi.fn>> & {
    then?: (resolve: (value: Result) => unknown, reject?: (reason: unknown) => unknown) => Promise<unknown>;
  } = {
    select: vi.fn(),
    eq: vi.fn(),
    is: vi.fn(),
    in: vi.fn(),
    gte: vi.fn(),
    lte: vi.fn(),
    order: vi.fn(),
    limit: vi.fn(),
    insert: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    single: vi.fn(),
    maybeSingle: vi.fn(),
  };
  for (const method of [
    'select',
    'eq',
    'is',
    'in',
    'gte',
    'lte',
    'order',
    'limit',
    'insert',
    'update',
    'delete',
  ] as const) {
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
  const storageBucket = {
    upload: vi.fn().mockResolvedValue({ data: { path: 'user-1/manual/file.json' }, error: null }),
    download: vi.fn().mockResolvedValue({ data: new Blob(['{}']), error: null }),
    remove: vi.fn().mockResolvedValue({ data: {}, error: null }),
  };
  const rpc = vi.fn().mockResolvedValue({ data: { transactions: 1 }, error: null });
  return {
    client: {
      from,
      storage: { from: vi.fn().mockReturnValue(storageBucket) },
      rpc,
    } as unknown as ExportBackupDataClient,
    from,
    builders,
    storageBucket,
    rpc,
  };
}

const selection: ExportSelection = {
  format: 'csv',
  startDate: '2026-07-01',
  endDate: '2026-07-31',
  contents: ['transaction', 'report'],
};

describe('normalized export metadata', () => {
  test('creates an owner-scoped export row and separate content rows', async () => {
    const row = {
      id: 'export-1',
      user_id: 'user-1',
      format: 'csv',
      status: 'pending',
      file_name: 'FinCoach.csv',
      file_size_bytes: null,
      date_from: '2026-07-01',
      date_to: '2026-07-31',
      completed_at: null,
      created_at: '2026-07-16T00:00:00Z',
    };
    const { client, builders } = createClient({ data_exports: { data: row } });

    await expect(createDataExport('user-1', selection, 'FinCoach.csv', client)).resolves.toEqual(
      row,
    );
    await saveExportContents('export-1', selection.contents, client);

    expect(builders.get('data_exports')?.insert).toHaveBeenCalledWith({
      user_id: 'user-1',
      format: 'csv',
      status: 'pending',
      file_name: 'FinCoach.csv',
      date_from: '2026-07-01',
      date_to: '2026-07-31',
    });
    expect(builders.get('export_contents')?.insert).toHaveBeenCalledWith([
      { export_id: 'export-1', content_type: 'transaction' },
      { export_id: 'export-1', content_type: 'report' },
    ]);
  });
});

describe('full backup source', () => {
  test('loads every approved dataset with explicit owner filters', async () => {
    const { client, builders } = createClient({
      profiles: { data: { id: 'user-1' } },
      categories: { data: [] },
      transactions: { data: [] },
      monthly_budgets: { data: [] },
      budgets: { data: [] },
      savings_goals: { data: [] },
      savings_contributions: { data: [] },
      reports: { data: [] },
      notification_preferences: { data: null },
      reminders: { data: [] },
      alerts: { data: [] },
    });

    await expect(fetchBackupSourceData('user-1', client)).resolves.toMatchObject({
      profile: { id: 'user-1' },
      customCategories: [],
      transactions: [],
      alerts: [],
    });

    for (const table of [
      'profiles',
      'transactions',
      'monthly_budgets',
      'budgets',
      'savings_goals',
      'reports',
      'notification_preferences',
      'reminders',
      'alerts',
    ]) {
      expect(builders.get(table)?.eq).toHaveBeenCalledWith(
        table === 'profiles' ? 'id' : table === 'notification_preferences' ? 'user_id' : 'user_id',
        'user-1',
      );
    }
    expect(builders.get('categories')?.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });
});

describe('private backup operations', () => {
  test('uploads exact JSON bytes without upsert', async () => {
    const { client, storageBucket } = createClient();
    const bytes = new TextEncoder().encode('{"schemaVersion":1}').buffer;
    await uploadBackupObject('user-1/manual/file.json', bytes, client);
    expect(storageBucket.upload).toHaveBeenCalledWith('user-1/manual/file.json', bytes, {
      contentType: 'application/json',
      upsert: false,
    });
  });

  test('updates the preference through the owner-scoped profile row', async () => {
    const { client, builders } = createClient({ profiles: { data: { auto_backup_enabled: false } } });
    await updateAutoBackupEnabled('user-1', false, client);
    expect(builders.get('profiles')?.update).toHaveBeenCalledWith({
      auto_backup_enabled: false,
      updated_at: expect.any(String),
    });
    expect(builders.get('profiles')?.eq).toHaveBeenCalledWith('id', 'user-1');
  });

  test('invokes the owner-validating restore RPC with the selected backup', async () => {
    const { client, rpc } = createClient();
    const document = {
      schemaVersion: 1,
      createdAt: '2026-07-16T00:00:00Z',
      userId: 'user-1',
      appVersion: '1.0.0',
      data: {},
    } as unknown as FinancialBackupDocumentV1;
    await restoreFinancialBackup('backup-1', document, client);
    expect(rpc).toHaveBeenCalledWith('restore_financial_backup_v1', {
      payload: document,
      backup_record_id: 'backup-1',
    });
  });
});
