import { fetchAllRows as allRows } from '@/lib/pagination';
import { monthKeysForRange } from '@/lib/report-domain';
import { supabase } from '@/lib/supabase';
import type {
  BackupRecord,
  BackupSourceData,
  BackupType,
  DataExportRecord,
  ExportContentType,
  ExportSelection,
  ExportSourceData,
  FinancialBackupDocument,
  FinancialBackupDocumentV2,
  MonthlyBudget,
  Profile,
  Report,
  RestoreFinancialBackupResult,
  SavingsGoal,
  TransactionWithCategory,
} from '@/lib/types';

type QueryResult = { data: unknown; error: unknown; count?: number | null };

type ExportBackupQuery = PromiseLike<QueryResult> & {
  delete: () => ExportBackupQuery;
  eq: (column: string, value: unknown) => ExportBackupQuery;
  gte: (column: string, value: unknown) => ExportBackupQuery;
  in: (column: string, values: unknown[]) => ExportBackupQuery;
  insert: (value: Record<string, unknown> | Record<string, unknown>[]) => ExportBackupQuery;
  is: (column: string, value: unknown) => ExportBackupQuery;
  limit: (value: number) => ExportBackupQuery;
  lte: (column: string, value: unknown) => ExportBackupQuery;
  maybeSingle: () => Promise<QueryResult>;
  order: (column: string, options: Record<string, unknown>) => ExportBackupQuery;
  range: (from: number, to: number) => ExportBackupQuery;
  select: (...args: unknown[]) => ExportBackupQuery;
  single: () => Promise<QueryResult>;
  update: (value: Record<string, unknown>) => ExportBackupQuery;
};

type StorageBucket = {
  upload: (
    path: string,
    body: ArrayBuffer,
    options: { contentType: string; upsert: boolean },
  ) => Promise<QueryResult>;
  download: (path: string) => Promise<QueryResult>;
  remove: (paths: string[]) => Promise<QueryResult>;
  list: (prefix: string, options: { limit: number; offset: number }) => Promise<QueryResult>;
};

export type ExportBackupDataClient = {
  from: (table: string) => ExportBackupQuery;
  storage: { from: (bucket: string) => StorageBucket };
  rpc: (name: string, params: Record<string, unknown>) => Promise<QueryResult>;
};

const defaultClient = supabase as unknown as ExportBackupDataClient;
export { defaultClient as defaultExportBackupClient };
const backupBucket = 'financial-backups';

function throwIfError(error: unknown) {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string) {
  if (!data) throw new Error(message);
  return data as T;
}

export async function createDataExport(
  userId: string,
  selection: ExportSelection,
  fileName: string,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('data_exports')
    .insert({
      user_id: userId,
      format: selection.format,
      status: 'pending',
      file_name: fileName,
      date_from: selection.startDate,
      date_to: selection.endDate,
    })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<DataExportRecord>(data, 'The export record was not returned.');
}

export async function saveExportContents(
  exportId: string,
  contents: ExportContentType[],
  client: ExportBackupDataClient = defaultClient,
) {
  const payload = contents.map((contentType) => ({
    export_id: exportId,
    content_type: contentType,
  }));
  const { error } = await client.from('export_contents').insert(payload);
  throwIfError(error);
}

export async function updateDataExport(
  exportId: string,
  userId: string,
  updates: Partial<Pick<DataExportRecord, 'status' | 'file_size_bytes' | 'completed_at'>>,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('data_exports')
    .update(updates)
    .eq('id', exportId)
    .eq('user_id', userId)
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<DataExportRecord>(data, 'The export record could not be updated.');
}

export async function fetchExportSourceData(
  userId: string,
  selection: ExportSelection,
  client: ExportBackupDataClient = defaultClient,
): Promise<ExportSourceData> {
  const months = monthKeysForRange(selection.startDate, selection.endDate);
  if (!months.length) throw new Error('The export period is invalid.');
  const firstMonth = months[0];
  const lastMonth = months[months.length - 1];
  const endOfSelectedDay = `${selection.endDate}T23:59:59.999+08:00`;

  const [transactions, monthlyBudgets, categoryLimits, savingsGoals, reports] =
    await Promise.all([
      allRows<TransactionWithCategory>(() =>
        client
          .from('transactions')
          .select('*, category:categories(*)', { count: 'exact' })
          .eq('user_id', userId)
          .gte('transaction_date', selection.startDate)
          .lte('transaction_date', selection.endDate)
          .order('transaction_date', { ascending: true }).order('id', { ascending: true }),
      ),
      allRows<MonthlyBudget>(() =>
        client
          .from('monthly_budgets')
          .select('*', { count: 'exact' })
          .eq('user_id', userId)
          .gte('month', firstMonth)
          .lte('month', lastMonth)
          .order('month', { ascending: true }).order('id', { ascending: true }),
      ),
      allRows<ExportSourceData['categoryLimits'][number]>(() =>
        client
          .from('budgets')
          .select('*, category:categories(name)', { count: 'exact' })
          .eq('user_id', userId)
          .gte('month', firstMonth)
          .lte('month', lastMonth)
          .order('month', { ascending: true }).order('id', { ascending: true }),
      ),
      allRows<SavingsGoal>(() =>
        client
          .from('savings_goals')
          .select('*', { count: 'exact' })
          .eq('user_id', userId)
          .order('created_at', { ascending: true }).order('id', { ascending: true }),
      ),
      allRows<Report>(() =>
        client
          .from('reports')
          .select('*', { count: 'exact' })
          .eq('user_id', userId)
          .gte('generated_at', `${selection.startDate}T00:00:00+08:00`)
          .lte('generated_at', endOfSelectedDay)
          .order('generated_at', { ascending: true }).order('id', { ascending: true }),
      ),
    ]);
  return { transactions, monthlyBudgets, categoryLimits, savingsGoals, reports };
}

export async function fetchBackupSourceData(
  userId: string,
  client: ExportBackupDataClient = defaultClient,
  backupId?: string,
): Promise<BackupSourceData> {
  const { data, error } = await client.rpc('financial_backup_snapshot_v2', {
    backup_record_id: backupId ?? null,
  });
  throwIfError(error);
  const source = requireRow<BackupSourceData>(data, 'The complete backup snapshot was not returned.');
  if (source.profile && source.profile.id !== userId) throw new Error('Backup snapshot owner mismatch.');
  return source;
}

export async function completeFinancialBackup(
  backupId: string, document: FinancialBackupDocumentV2, path: string,
  size: number, checksum: string, client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client.rpc('complete_financial_backup_v2', {
    backup_record_id: backupId, document, object_path: path, object_size: size, checksum,
  });
  throwIfError(error);
  return requireRow<BackupRecord>(data, 'The completed backup record was not returned.');
}

export async function createBackupRecord(
  userId: string,
  type: BackupType,
  fileName: string,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('backups')
    .insert({
      user_id: userId,
      backup_type: type,
      status: 'pending',
      file_name: fileName,
      schema_version: 1,
    })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<BackupRecord>(data, 'The backup record was not returned.');
}

export async function updateBackupRecord(
  backupId: string,
  userId: string,
  updates: Partial<BackupRecord>,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('backups')
    .update(updates)
    .eq('id', backupId)
    .eq('user_id', userId)
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<BackupRecord>(data, 'The backup record could not be updated.');
}

export async function fetchBackups(
  userId: string,
  _limit = 50,
  client: ExportBackupDataClient = defaultClient,
) {
  return allRows<BackupRecord>(() =>
    client
      .from('backups')
      .select('*', { count: 'exact' })
      .eq('user_id', userId)
      .order('created_at', { ascending: false }).order('id', { ascending: false }),
  );
}

export async function uploadBackupObject(
  path: string,
  bytes: ArrayBuffer,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client.storage.from(backupBucket).upload(path, bytes, {
    contentType: 'application/json',
    upsert: false,
  });
  throwIfError(error);
  return requireRow<{ path: string }>(data, 'The backup object was not returned.');
}

export async function downloadBackupObject(
  path: string,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client.storage.from(backupBucket).download(path);
  throwIfError(error);
  return requireRow<Blob>(data, 'The backup object could not be downloaded.');
}

export async function removeBackupObject(path: string, client: ExportBackupDataClient = defaultClient) {
  const { error } = await client.storage.from(backupBucket).remove([path]);
  throwIfError(error);
}

export async function deleteBackup(
  record: BackupRecord,
  client: ExportBackupDataClient = defaultClient,
) {
  // A durable tombstone prevents restore from offering partially removed files.
  const begun = await client.rpc('begin_financial_backup_delete_v2', { backup_record_id: record.id });
  throwIfError(begun.error);
  // Keep lifecycle code out of module initialization to avoid a circular import.
  const { removeBackupAttachmentCopies } = await import('./backup-attachments');
  await removeBackupAttachmentCopies(record.user_id, record.id, client);
  if (record.storage_path) {
    const { error: storageError } = await client.storage
      .from(backupBucket)
      .remove([record.storage_path]);
    throwIfError(storageError);
  }
  const { error } = await client
    .from('backups')
    .delete()
    .eq('id', record.id)
    .eq('user_id', record.user_id);
  throwIfError(error);
}

export async function fetchAutoBackupEnabled(
  userId: string,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('profiles')
    .select('auto_backup_enabled')
    .eq('id', userId)
    .maybeSingle();
  throwIfError(error);
  return (data as Pick<Profile, 'auto_backup_enabled'> | null)?.auto_backup_enabled ?? true;
}

export async function updateAutoBackupEnabled(
  userId: string,
  enabled: boolean,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('profiles')
    .update({ auto_backup_enabled: enabled, updated_at: new Date().toISOString() })
    .eq('id', userId)
    .select('auto_backup_enabled')
    .single();
  throwIfError(error);
  return requireRow<Pick<Profile, 'auto_backup_enabled'>>(
    data,
    'The backup preference could not be updated.',
  ).auto_backup_enabled;
}

export class RestoreOutcomeUnknownError extends Error {
  constructor() {
    super('The server response was lost. Refresh backup history to check the restore status before retrying.');
    this.name = 'RestoreOutcomeUnknownError';
  }
}

export async function restoreFinancialBackup(
  backupId: string,
  document: FinancialBackupDocument,
  client: ExportBackupDataClient = defaultClient,
) {
  const { validateBackupDocument } = await import('./export-backup-domain');
  validateBackupDocument(document, document.userId);
  // Compare authoritative server history if a reply is lost after commit.
  const before = await client.from('backups').select('last_restored_at').eq('id', backupId).eq('user_id', document.userId).maybeSingle();
  throwIfError(before.error);
  const prepared = document.schemaVersion === 2
    ? await (await import('./backup-attachments')).prepareRestoreAttachments(backupId, document, client)
    : null;
  try {
  const { data, error } = await client.rpc(document.schemaVersion === 2 ? 'restore_financial_backup_v2' : 'restore_financial_backup_v1', {
    payload: document,
    backup_record_id: backupId,
    ...(prepared ? { restored_paths: prepared.paths } : {}),
  });
  throwIfError(error);
  return requireRow<RestoreFinancialBackupResult>(data, 'The restore result was not returned.');
  } catch (error) {
    // A network timeout has an unknown commit outcome. Do not delete files that
    // may now be referenced by a committed restore; database errors roll back.
    const definitive = error && typeof error === 'object' && 'code' in error &&
      /^\d{5}$|^P\d{4}$/.test(String((error as { code: unknown }).code));
    if (definitive) {
      if (prepared) await prepared.cleanup();
      throw error;
    }
    try {
      const after = await client.from('backups').select('last_restore_status,last_restored_at')
        .eq('id', backupId).eq('user_id', document.userId).maybeSingle();
      const current = after.data as Pick<BackupRecord, 'last_restore_status' | 'last_restored_at'> | null;
      const previous = before.data as Pick<BackupRecord, 'last_restored_at'> | null;
      if (!after.error && current?.last_restore_status === 'completed' && current.last_restored_at &&
        current.last_restored_at !== previous?.last_restored_at) {
        return (await import('./backup-v2-domain')).backupCounts(document.data);
      }
    } catch { /* An unreachable server cannot establish a commit outcome. */ }
    throw new RestoreOutcomeUnknownError();
  }
}

export async function reconcileStaleRecords(
  userId: string,
  cutoffIso: string,
  client: ExportBackupDataClient = defaultClient,
) {
  const exportResult = await client
    .from('data_exports')
    .update({ status: 'failed' })
    .eq('user_id', userId)
    .in('status', ['pending', 'processing'])
    .lte('created_at', cutoffIso);
  throwIfError(exportResult.error);
  const backupResult = await client
    .from('backups')
    .update({ status: 'failed' })
    .eq('user_id', userId)
    .in('status', ['pending', 'processing'])
    .lte('created_at', cutoffIso);
  throwIfError(backupResult.error);
}
