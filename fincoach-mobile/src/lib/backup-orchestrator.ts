import Constants from 'expo-constants';
import * as Crypto from 'expo-crypto';

import {
  createBackupObjectPath,
  selectAutomaticBackupsForDeletion,
  serializeBackupDocument,
  validateBackupDocument,
} from '@/lib/export-backup-domain';
import {
  createBackupRecord,
  deleteBackup,
  downloadBackupObject,
  fetchAutoBackupEnabled,
  fetchBackups,
  fetchBackupSourceData,
  updateBackupRecord,
  uploadBackupObject,
} from '@/lib/export-backup';
import type {
  BackupRecord,
  BackupSourceData,
  BackupType,
  FinancialBackupDocumentV1,
} from '@/lib/types';

type BackupUpdates = Partial<BackupRecord>;

export type BackupOrchestratorDependencies = {
  now: () => Date;
  appVersion: string;
  createBackupRecord: (userId: string, type: BackupType, fileName: string) => Promise<BackupRecord>;
  updateBackupRecord: (backupId: string, userId: string, updates: BackupUpdates) => Promise<BackupRecord>;
  fetchBackupSourceData: (userId: string) => Promise<BackupSourceData>;
  uploadBackupObject: (path: string, bytes: ArrayBuffer) => Promise<{ path: string }>;
  fetchBackups: (userId: string, limit?: number) => Promise<BackupRecord[]>;
  deleteBackup: (record: BackupRecord) => Promise<void>;
  fetchAutoBackupEnabled: (userId: string) => Promise<boolean>;
  digest: (content: string) => Promise<string>;
};

const defaultDependencies: BackupOrchestratorDependencies = {
  now: () => new Date(),
  appVersion: Constants.expoConfig?.version ?? '1.0.0',
  createBackupRecord,
  updateBackupRecord,
  fetchBackupSourceData,
  uploadBackupObject,
  fetchBackups,
  deleteBackup,
  fetchAutoBackupEnabled,
  digest: (content) =>
    Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, content),
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

  try {
    await dependencies.updateBackupRecord(record.id, userId, { status: 'processing' });
    const source = await dependencies.fetchBackupSourceData(userId);
    const json = serializeBackupDocument(
      userId,
      dependencies.appVersion,
      source,
      createdAt.toISOString(),
    );
    const bytes = new TextEncoder().encode(json);
    const checksum = await dependencies.digest(json);
    const path = createBackupObjectPath(userId, type, record.id, createdAt);
    await dependencies.uploadBackupObject(path, exactArrayBuffer(bytes));
    const completed = await dependencies.updateBackupRecord(record.id, userId, {
      status: 'completed',
      storage_path: path,
      file_size_bytes: bytes.byteLength,
      checksum_sha256: checksum,
      schema_version: 1,
      completed_at: dependencies.now().toISOString(),
    });

    if (type === 'automatic') {
      const history = await dependencies.fetchBackups(userId, 100);
      const retainedHistory = history.some((item) => item.id === completed.id)
        ? history
        : [completed, ...history];
      for (const stale of selectAutomaticBackupsForDeletion(retainedHistory)) {
        await dependencies.deleteBackup(stale);
      }
    }
    return completed;
  } catch (error) {
    await dependencies
      .updateBackupRecord(record.id, userId, { status: 'failed' })
      .catch(() => undefined);
    throw error;
  }
}

export async function downloadAndValidateBackup(
  record: BackupRecord,
  expectedUserId: string,
  dependencies: Pick<BackupOrchestratorDependencies, 'digest'> = defaultDependencies,
  downloadedBlob?: Blob,
): Promise<FinancialBackupDocumentV1> {
  if (record.user_id !== expectedUserId || record.status !== 'completed' || !record.storage_path) {
    throw new Error('This backup is not available for restore.');
  }
  const blob = downloadedBlob ?? await downloadBackupObject(record.storage_path);
  const json = await blob.text();
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
  return validateBackupDocument(parsed, expectedUserId);
}

const automaticBackupInFlight = new Map<string, Promise<BackupRecord | null>>();

export function runEligibleAutomaticBackup(
  userId: string,
  dependencies: BackupOrchestratorDependencies = defaultDependencies,
) {
  const existing = automaticBackupInFlight.get(userId);
  if (existing) return existing;

  const operation = (async () => {
    if (!(await dependencies.fetchAutoBackupEnabled(userId))) return null;
    const history = await dependencies.fetchBackups(userId, 20);
    const cutoff = dependencies.now().getTime() - 24 * 60 * 60 * 1000;
    const recent = history.some(
      (record) =>
        record.backup_type === 'automatic' &&
        record.status === 'completed' &&
        new Date(record.completed_at ?? record.created_at).getTime() >= cutoff,
    );
    return recent ? null : performCloudBackup(userId, 'automatic', dependencies);
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
