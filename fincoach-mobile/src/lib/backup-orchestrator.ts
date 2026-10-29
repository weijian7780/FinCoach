import Constants from 'expo-constants';
import * as Crypto from 'expo-crypto';

import {
  createBackupObjectPath,
  isDefinitiveDatabaseError,
  selectAutomaticBackupsForDeletion,
  serializeBackupDocument,
  validateBackupDocument,
} from '@/lib/export-backup-domain';
import {
  createBackupRecord,
  completeFinancialBackup,
  deleteBackup,
  downloadBackupObject,
  fetchAutoBackupEnabled,
  fetchBackups,
  fetchBackupSourceData,
  updateBackupRecord,
  uploadBackupObject,
  removeBackupObject,
  reconcileStaleRecords,
} from '@/lib/export-backup';
import type {
  BackupRecord,
  BackupSourceData,
  BackupType,
  FinancialBackupDocumentV1,
  FinancialBackupDocument,
  FinancialBackupDocumentV2,
  BackupAttachment,
} from '@/lib/types';
import { backupCounts } from './backup-v2-domain';
import { captureBackupAttachments, removeBackupAttachmentCopies } from './backup-attachments';

type BackupUpdates = Partial<BackupRecord>;

export type BackupOrchestratorDependencies = {
  now: () => Date;
  appVersion: string;
  createBackupRecord: (userId: string, type: BackupType, fileName: string) => Promise<BackupRecord>;
  updateBackupRecord: (backupId: string, userId: string, updates: BackupUpdates) => Promise<BackupRecord>;
  fetchBackupSourceData: (userId: string, backupId?: string) => Promise<BackupSourceData>;
  uploadBackupObject: (path: string, bytes: ArrayBuffer) => Promise<{ path: string }>;
  fetchBackups: (userId: string, limit?: number) => Promise<BackupRecord[]>;
  deleteBackup: (record: BackupRecord) => Promise<void>;
  fetchAutoBackupEnabled: (userId: string) => Promise<boolean>;
  digest: (content: string) => Promise<string>;
  captureAttachments?: (userId: string, backupId: string, source: BackupSourceData) => Promise<BackupAttachment[]>;
  completeBackup?: (backupId: string, document: FinancialBackupDocumentV2, path: string, size: number, checksum: string) => Promise<BackupRecord>;
  cleanupAttachments?: (userId: string, backupId: string) => Promise<void>;
  removeUploadedObject?: (path: string) => Promise<void>;
  reconcileStale?: (userId: string, cutoffIso: string) => Promise<void>;
};

const defaultDependencies: BackupOrchestratorDependencies = {
  now: () => new Date(),
  appVersion: Constants.expoConfig?.version ?? '1.0.0',
  createBackupRecord,
  updateBackupRecord,
  fetchBackupSourceData: (userId, backupId) => fetchBackupSourceData(userId, undefined, backupId),
  uploadBackupObject,
  fetchBackups,
  deleteBackup,
  fetchAutoBackupEnabled,
  digest: (content) =>
    Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, content),
  captureAttachments: captureBackupAttachments,
  completeBackup: completeFinancialBackup,
  cleanupAttachments: removeBackupAttachmentCopies,
  removeUploadedObject: removeBackupObject,
  reconcileStale: reconcileStaleRecords,
};

function backupFileName(type: BackupType, date: Date) {
  const stamp = date.toISOString().replace(/[:.]/g, '-');
  return `FinCoach_${type}_backup_${stamp}.json`;
}

function exactArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

export async function performCloudBackup(
  userId: string,
  type: BackupType,
  dependencies: BackupOrchestratorDependencies = defaultDependencies,
) {
  const createdAt = dependencies.now();
  const record = await dependencies.createBackupRecord(
    userId,
    type,
    backupFileName(type, createdAt),
  );
  let completionAttempted = false;
  let uploadedPath: string | null = null;

  try {
    await dependencies.updateBackupRecord(record.id, userId, { status: 'processing' });
    const source = await dependencies.fetchBackupSourceData(userId, record.id);
    const canonical = JSON.parse(serializeBackupDocument(
      userId,
      dependencies.appVersion,
      { ...source, userCategories: source.userCategories ?? [] },
      createdAt.toISOString(),
    )) as FinancialBackupDocumentV1;
    const attachments = await (dependencies.captureAttachments ?? captureBackupAttachments)(userId, record.id, canonical.data);
    const document: FinancialBackupDocumentV2 = { ...canonical, schemaVersion: 2, counts: backupCounts(canonical.data), attachments };
    validateBackupDocument(document, userId);
    const json = JSON.stringify(document);
    const bytes = new TextEncoder().encode(json);
    const checksum = await dependencies.digest(json);
    const path = createBackupObjectPath(userId, type, record.id, createdAt);
    // Persist the planned object path so failed uploads can be cleaned later.
    await dependencies.updateBackupRecord(record.id, userId, { storage_path: path });
    uploadedPath = path;
    await dependencies.uploadBackupObject(path, exactArrayBuffer(bytes));
    completionAttempted = true;
    const completed = dependencies.completeBackup
      ? await dependencies.completeBackup(record.id, document, path, bytes.byteLength, checksum)
      : await dependencies.updateBackupRecord(record.id, userId, {
      status: 'completed',
      storage_path: path,
      file_size_bytes: bytes.byteLength,
      checksum_sha256: checksum,
      schema_version: 2,
      data_counts: document.counts,
      attachment_count: attachments.length,
      completed_at: dependencies.now().toISOString(),
    });

    if (type === 'automatic') {
      try {
      const history = await dependencies.fetchBackups(userId, 100);
      const retainedHistory = history.some((item) => item.id === completed.id)
        ? history
        : [completed, ...history];
      for (const stale of selectAutomaticBackupsForDeletion(retainedHistory)) {
        await dependencies.deleteBackup(stale);
      }
      } catch (error) {
        // Retention is maintenance; the new verified backup remains completed.
        const cleanup_warning = 'Backup completed. Older backup cleanup will retry later.';
        await dependencies.updateBackupRecord(record.id, userId, { cleanup_warning }).catch(() => undefined);
        completed.cleanup_warning = cleanup_warning;
        console.warn(cleanup_warning, error);
      }
    }
    return completed;
  } catch (error) {
    if (completionAttempted) {
      // A lost response is not proof that the transaction rolled back. Preserve
      // a committed backup and leave an unknown outcome available for retry.
      const current = await dependencies.fetchBackups(userId, 100).then(records => records.find(b => b.id === record.id)).catch(() => undefined);
      if (current?.status === 'completed') return current;
      if (!isDefinitiveDatabaseError(error)) throw new Error('Backup completion could not be confirmed. Refresh backup history before retrying.');
    }
    // Deleting the record also drops its full server snapshot copy. If that
    // fails (often offline), mark it failed; stale cleanup deletes it later.
    const deleted = await dependencies.deleteBackup({ ...record, storage_path: uploadedPath })
      .then(() => true, () => false);
    if (!deleted) {
      if (uploadedPath) await dependencies.removeUploadedObject?.(uploadedPath).catch(() => undefined);
      await dependencies.cleanupAttachments?.(userId, record.id).catch(() => undefined);
      await dependencies
        .updateBackupRecord(record.id, userId, { status: 'failed' })
        .catch(() => undefined);
    }
    throw error;
  }
}

function readBackupText(blob: Blob): Promise<string> {
  // Browser Blobs support text(), but React Native's downloaded Blobs do not.
  // Read native data as UTF-8 without changing the JSON used for verification.
  if (typeof blob.text === 'function') return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result);
      else reject(new Error('The backup file could not be read as text.'));
    };
    reader.onerror = () => reject(reader.error ?? new Error('The backup file could not be read.'));
    reader.onabort = () => reject(new Error('Reading the backup file was cancelled.'));
    reader.readAsText(blob, 'UTF-8');
  });
}

export async function downloadAndValidateBackup(
  record: BackupRecord,
  expectedUserId: string,
  dependencies: Pick<BackupOrchestratorDependencies, 'digest'> = defaultDependencies,
  downloadedBlob?: Blob,
): Promise<FinancialBackupDocument> {
  if (record.user_id !== expectedUserId || record.status !== 'completed' || !record.storage_path) {
    throw new Error('This backup is not available for restore.');
  }
  const blob = downloadedBlob ?? await downloadBackupObject(record.storage_path);
  const json = await readBackupText(blob);
  const size = new TextEncoder().encode(json).byteLength;
  if (record.file_size_bytes !== null && record.file_size_bytes !== size) {
    throw new Error('Backup verification failed. The stored file size does not match.');
  }
  const checksum = await dependencies.digest(json);
  if (record.checksum_sha256 && checksum !== record.checksum_sha256) {
    throw new Error('Backup verification failed. The checksum does not match.');
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new Error('Invalid backup file.');
  }
  const document = validateBackupDocument(parsed, expectedUserId);
  if (document.schemaVersion === 2 && document.attachments.some(asset => !asset.backupPath.startsWith(`${expectedUserId}/assets/${record.id}/`))) {
    throw new Error('Backup attachment belongs to another snapshot.');
  }
  return document;
}

const automaticBackupInFlight = new Map<string, Promise<BackupRecord | null>>();
// Failed records are deleted, so the last failure time is kept per app session.
// Without it every foreground would re-copy all attachments and fail again.
const automaticBackupFailedAt = new Map<string, number>();
const automaticRetryDelayMs = 6 * 60 * 60 * 1000;
const staleBackupAgeMs = 15 * 60 * 1000;

export function runEligibleAutomaticBackup(
  userId: string,
  dependencies: BackupOrchestratorDependencies = defaultDependencies,
) {
  const existing = automaticBackupInFlight.get(userId);
  if (existing) return existing;

  const operation = (async () => {
    if (!(await dependencies.fetchAutoBackupEnabled(userId))) return null;
    const now = dependencies.now().getTime();
    await dependencies.reconcileStale?.(userId, new Date(now - staleBackupAgeMs).toISOString())
      .catch((error) => console.warn('Unfinished backup cleanup will retry later.', error));
    const failedAt = automaticBackupFailedAt.get(userId);
    if (failedAt !== undefined && now - failedAt < automaticRetryDelayMs) return null;
    const history = await dependencies.fetchBackups(userId, 20);
    const cutoff = dependencies.now().getTime() - 24 * 60 * 60 * 1000;
    const recent = history.some(
      (record) =>
        record.backup_type === 'automatic' &&
        record.status === 'completed' &&
        new Date(record.completed_at ?? record.created_at).getTime() >= cutoff,
    );
    if (recent) {
      const latest = history.find(record => record.backup_type === 'automatic' && record.status === 'completed');
      try {
        for (const stale of selectAutomaticBackupsForDeletion(history)) await dependencies.deleteBackup(stale);
        if (latest?.cleanup_warning) await dependencies.updateBackupRecord(latest.id, userId, { cleanup_warning: null });
      } catch (error) {
        console.warn('Older backup cleanup will retry on the next foreground check.', error);
      }
      return null;
    }
    try {
      const completed = await performCloudBackup(userId, 'automatic', dependencies);
      automaticBackupFailedAt.delete(userId);
      return completed;
    } catch (error) {
      automaticBackupFailedAt.set(userId, now);
      throw error;
    }
  })();

  automaticBackupInFlight.set(userId, operation);
  const clear = () => {
    if (automaticBackupInFlight.get(userId) === operation) {
      automaticBackupInFlight.delete(userId);
    }
  };
  void operation.then(clear, clear);
  return operation;
}
