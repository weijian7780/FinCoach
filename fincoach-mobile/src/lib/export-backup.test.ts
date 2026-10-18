import { describe, expect, test, vi } from 'vitest';

import {
  createDataExport,
  deleteBackup,
  RestoreOutcomeUnknownError,
  fetchBackupSourceData,
  restoreFinancialBackup,
  saveExportContents,
  updateAutoBackupEnabled,
  uploadBackupObject,
  type ExportBackupDataClient,
} from './export-backup';
import type { ExportSelection, FinancialBackupDocumentV1 } from './types';

vi.mock('expo-crypto', () => ({}));
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
    list: vi.fn().mockResolvedValue({ data: [], error: null }),
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
  test('loads approved data through the owner-scoped snapshot RPC', async () => {
    const { client, rpc } = createClient();
    const source = { profile: { id: 'user-1' }, customCategories: [], userCategories: [], transactions: [],
      monthlyBudgets: [], categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [],
      notificationPreferences: null, reminders: [], alerts: [] };
    rpc.mockResolvedValue({ data: source, error: null });
    await expect(fetchBackupSourceData('user-1', client)).resolves.toEqual(source);
    expect(rpc).toHaveBeenCalledWith('financial_backup_snapshot_v2', { backup_record_id: null });
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

  test('marks deletion unavailable before Storage and retains the tombstone on failure', async () => {
    const { client, rpc, storageBucket, from } = createClient();
    storageBucket.remove.mockRejectedValue(new Error('offline'));
    await expect(deleteBackup({ id: 'backup-1', user_id: 'user-1', storage_path: 'user-1/file.json' } as never, client)).rejects.toThrow('offline');
    expect(rpc).toHaveBeenCalledWith('begin_financial_backup_delete_v2', { backup_record_id: 'backup-1' });
    expect(rpc.mock.invocationCallOrder[0]).toBeLessThan(storageBucket.remove.mock.invocationCallOrder[0]);
    expect(from).not.toHaveBeenCalled();
  });

  test('keeps a deletion tombstone when asset removal stops after a batch', async () => {
    const { client, rpc, storageBucket, from } = createClient();
    storageBucket.list.mockResolvedValueOnce({ data: [{ name: 'one.png' }], error: null })
      .mockRejectedValueOnce(new Error('list disconnected'));
    await expect(deleteBackup({ id: 'backup-1', user_id: 'user-1' } as never, client)).rejects.toThrow('list disconnected');
    expect(rpc).toHaveBeenCalledWith('begin_financial_backup_delete_v2', { backup_record_id: 'backup-1' });
    expect(storageBucket.remove).toHaveBeenCalledWith(['user-1/assets/backup-1/one.png']);
    expect(from).not.toHaveBeenCalled();
  });

  test('retains the deletion marker when metadata deletion fails after files are removed', async () => {
    const { client, rpc, storageBucket, builders } = createClient({ backups: { error: new Error('database disconnected') } });
    await expect(deleteBackup({ id: 'backup-1', user_id: 'user-1', storage_path: 'user-1/file.json' } as never, client)).rejects.toThrow('database disconnected');
    expect(storageBucket.remove).toHaveBeenCalledWith(['user-1/file.json']);
    expect(builders.get('backups')?.delete).toHaveBeenCalled();
    expect(rpc).toHaveBeenCalledWith('begin_financial_backup_delete_v2', { backup_record_id: 'backup-1' });
  });

  test('preserves an unknown restore outcome after a lost server response', async () => {
    const { client, rpc } = createClient();
    rpc.mockRejectedValue(new Error('network timeout'));
    const document = { schemaVersion: 1, createdAt: '2026-07-16T00:00:00Z', userId: 'user-1', appVersion: '1',
      data: { profile: null, customCategories: [], userCategories: [], transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [], notificationPreferences: null, reminders: [], alerts: [] } } as FinancialBackupDocumentV1;
    await expect(restoreFinancialBackup('backup-1', document, client)).rejects.toBeInstanceOf(RestoreOutcomeUnknownError);
  });

  test('reconciles a lost restore reply against newly committed server history', async () => {
    const { client, rpc, from } = createClient();
    rpc.mockRejectedValue(new Error('lost reply'));
    const history = createBuilder();
    history.maybeSingle.mockResolvedValueOnce({ data: { last_restored_at: null }, error: null })
      .mockResolvedValueOnce({ data: { last_restore_status: 'completed', last_restored_at: '2026-10-10T16:00:00Z' }, error: null });
    from.mockReturnValue(history);
    const document = { schemaVersion: 1, createdAt: '2026-07-16T00:00:00Z', userId: 'user-1', appVersion: '1',
      data: { profile: null, customCategories: [], userCategories: [], transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [], notificationPreferences: null, reminders: [], alerts: [] } } as FinancialBackupDocumentV1;
    await expect(restoreFinancialBackup('backup-1', document, client)).resolves.toMatchObject({ transactions: 0 });
  });

  test('invokes the owner-validating restore RPC with the selected backup', async () => {
    const { client, rpc } = createClient();
    const document = {
      schemaVersion: 1,
      createdAt: '2026-07-16T00:00:00Z',
      userId: 'user-1',
      appVersion: '1.0.0',
      data: { profile: null, customCategories: [], userCategories: [], transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [], notificationPreferences: null, reminders: [], alerts: [] },
    } as unknown as FinancialBackupDocumentV1;
    await restoreFinancialBackup('backup-1', document, client);
    expect(rpc).toHaveBeenCalledWith('restore_financial_backup_v1', {
      payload: document,
      backup_record_id: 'backup-1',
    });
  });
});
