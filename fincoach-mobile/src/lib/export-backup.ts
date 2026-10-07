import { monthKeysForRange } from '@/lib/report-domain';
import { supabase } from '@/lib/supabase';
import type {
  AlertRecord,
  BackupRecord,
  BackupSourceData,
  BackupType,
  BillReminder,
  Category,
  CategoryLimit,
  DataExportRecord,
  ExportContentType,
  ExportSelection,
  ExportSourceData,
  FinancialBackupDocumentV1,
  MonthlyBudget,
  NotificationPreferences,
  Profile,
  Report,
  RestoreFinancialBackupResult,
  SavingsContribution,
  SavingsGoal,
  Transaction,
  TransactionWithCategory,
} from '@/lib/types';

type QueryResult = { data: unknown; error: unknown };

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
};

export type ExportBackupDataClient = {
  from: (table: string) => ExportBackupQuery;
  storage: { from: (bucket: string) => StorageBucket };
  rpc: (name: string, params: Record<string, unknown>) => Promise<QueryResult>;
};

const defaultClient = supabase as unknown as ExportBackupDataClient;
const backupBucket = 'financial-backups';

function throwIfError(error: unknown) {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string) {
  if (!data) throw new Error(message);
  return data as T;
}

async function rows<T>(query: ExportBackupQuery) {
  const { data, error } = await query;
  throwIfError(error);
  return (data ?? []) as T[];
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
  const endOfSelectedDay = `${selection.endDate}T23:59:59.999`;

  const [transactions, monthlyBudgets, categoryLimits, savingsGoals, reports] =
    await Promise.all([
      rows<TransactionWithCategory>(
        client
          .from('transactions')
          .select('*, category:categories(*)')
          .eq('user_id', userId)
          .gte('transaction_date', selection.startDate)
          .lte('transaction_date', selection.endDate)
          .order('transaction_date', { ascending: true }),
      ),
      rows<MonthlyBudget>(
        client
          .from('monthly_budgets')
          .select('*')
          .eq('user_id', userId)
          .gte('month', firstMonth)
          .lte('month', lastMonth)
          .order('month', { ascending: true }),
      ),
      rows<CategoryLimit>(
        client
          .from('budgets')
          .select('*')
          .eq('user_id', userId)
          .gte('month', firstMonth)
          .lte('month', lastMonth)
          .order('month', { ascending: true }),
      ),
      rows<SavingsGoal>(
        client
          .from('savings_goals')
          .select('*')
          .eq('user_id', userId)
          .order('created_at', { ascending: true }),
      ),
      rows<Report>(
        client
          .from('reports')
          .select('*')
          .eq('user_id', userId)
          .gte('generated_at', `${selection.startDate}T00:00:00`)
          .lte('generated_at', endOfSelectedDay)
          .order('generated_at', { ascending: true }),
      ),
    ]);
  return { transactions, monthlyBudgets, categoryLimits, savingsGoals, reports };
}

export async function fetchBackupSourceData(
  userId: string,
  client: ExportBackupDataClient = defaultClient,
): Promise<BackupSourceData> {
  const goals = await rows<SavingsGoal>(
    client.from('savings_goals').select('*').eq('user_id', userId).order('created_at', { ascending: true }),
  );
  const goalIds = goals.map((goal) => goal.id);

  const [
    profileResult,
    customCategories,
    transactions,
    monthlyBudgets,
    categoryLimits,
    savingsContributions,
    reports,
    preferencesResult,
    reminders,
    alerts,
  ] = await Promise.all([
    client.from('profiles').select('*').eq('id', userId).maybeSingle(),
    rows<Category>(client.from('categories').select('*').eq('user_id', userId).order('id', { ascending: true })),
    rows<Transaction>(
      client.from('transactions').select('*').eq('user_id', userId).order('created_at', { ascending: true }),
    ),
    rows<MonthlyBudget>(
      client.from('monthly_budgets').select('*').eq('user_id', userId).order('month', { ascending: true }),
    ),
    rows<CategoryLimit>(
      client.from('budgets').select('*').eq('user_id', userId).order('created_at', { ascending: true }),
    ),
    goalIds.length
      ? rows<SavingsContribution>(
          client
            .from('savings_contributions')
            .select('*')
            .in('goal_id', goalIds)
            .order('created_at', { ascending: true }),
        )
      : Promise.resolve([]),
    rows<Report>(
      client.from('reports').select('*').eq('user_id', userId).order('generated_at', { ascending: true }),
    ),
    client
      .from('notification_preferences')
      .select('*')
      .eq('user_id', userId)
      .maybeSingle(),
    rows<BillReminder>(
      client.from('reminders').select('*').eq('user_id', userId).order('created_at', { ascending: true }),
    ),
    rows<AlertRecord>(
      client.from('alerts').select('*').eq('user_id', userId).order('created_at', { ascending: true }),
    ),
  ]);

  throwIfError(profileResult.error);
  throwIfError(preferencesResult.error);
  return {
    profile: profileResult.data as Profile | null,
    customCategories,
    transactions,
    monthlyBudgets,
    categoryLimits,
    savingsGoals: goals,
    savingsContributions,
    reports,
    notificationPreferences: preferencesResult.data as NotificationPreferences | null,
    reminders,
    alerts,
  };
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
  limit = 50,
  client: ExportBackupDataClient = defaultClient,
) {
  return rows<BackupRecord>(
    client
      .from('backups')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(Math.max(1, Math.min(100, Math.trunc(limit) || 50))),
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

export async function deleteBackup(
  record: BackupRecord,
  client: ExportBackupDataClient = defaultClient,
) {
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

export async function restoreFinancialBackup(
  backupId: string,
  document: FinancialBackupDocumentV1,
  client: ExportBackupDataClient = defaultClient,
) {
  const { data, error } = await client.rpc('restore_financial_backup_v1', {
    payload: document,
    backup_record_id: backupId,
  });
  throwIfError(error);
  return requireRow<RestoreFinancialBackupResult>(data, 'The restore result was not returned.');
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
