import { afterEach, describe, expect, test, vi } from 'vitest';

import { serializeBackupDocument } from './export-backup-domain';
import {
  downloadAndValidateBackup,
  performCloudBackup,
  runEligibleAutomaticBackup,
  type BackupOrchestratorDependencies,
} from './backup-orchestrator';

vi.mock('expo-constants', () => ({ default: { expoConfig: { version: '1.0.0' } } }));
vi.mock('expo-crypto', () => ({
  CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
  digestStringAsync: vi.fn().mockResolvedValue('checksum'),
}));
vi.mock('./export-backup', () => ({
  createBackupRecord: vi.fn(),
  completeFinancialBackup: vi.fn(),
  defaultExportBackupClient: {},
  removeBackupObject: vi.fn(),
  deleteBackup: vi.fn(),
  downloadBackupObject: vi.fn(),
  fetchAutoBackupEnabled: vi.fn(),
  fetchBackups: vi.fn(),
  fetchBackupSourceData: vi.fn(),
  updateBackupRecord: vi.fn(),
  uploadBackupObject: vi.fn(),
}));

afterEach(() => vi.unstubAllGlobals());

// React Native's downloaded Blob has no text() method. FileReader reads its
// native data instead; Node's Blob alone cannot reproduce this Android failure.
function nativeDownloadedBlob(content: string, failure?: Error) {
  const blob = { size: new TextEncoder().encode(content).byteLength, type: 'application/json' } as Blob;
  const readAsText = vi.fn();
  vi.stubGlobal('FileReader', class {
    result: string | null = null;
    error: Error | null = null;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    readAsText(value: Blob, encoding: string) {
      readAsText(value, encoding);
      queueMicrotask(() => {
        if (failure) {
          this.error = failure;
          this.onerror?.();
        } else {
          this.result = content;
          this.onload?.();
        }
      });
    }
  });
  return { blob, readAsText };
}

function dependencies(): BackupOrchestratorDependencies {
  const completed = {
    id: 'backup-1',
    user_id: 'user-1',
    backup_type: 'automatic' as const,
    status: 'completed' as const,
    file_name: 'backup.json',
    storage_path: 'user-1/automatic/backup-1.json',
    file_size_bytes: 20,
    checksum_sha256: 'checksum',
    schema_version: 1,
    last_restore_status: null,
    last_restored_at: null,
    completed_at: '2026-07-16T00:00:00.000Z',
    created_at: '2026-07-16T00:00:00.000Z',
  };
  return {
    now: () => new Date('2026-07-16T12:00:00.000Z'),
    appVersion: '1.0.0',
    createBackupRecord: vi.fn().mockResolvedValue({ ...completed, status: 'pending' }),
    updateBackupRecord: vi.fn().mockResolvedValue(completed),
    fetchBackupSourceData: vi.fn().mockResolvedValue({
      profile: null,
      customCategories: [],
      transactions: [],
      monthlyBudgets: [],
      categoryLimits: [],
      savingsGoals: [],
      savingsContributions: [],
      reports: [],
      notificationPreferences: null,
      reminders: [],
      alerts: [],
    }),
    uploadBackupObject: vi.fn().mockResolvedValue({ path: completed.storage_path }),
    fetchBackups: vi.fn().mockResolvedValue([]),
    deleteBackup: vi.fn().mockResolvedValue(undefined),
    fetchAutoBackupEnabled: vi.fn().mockResolvedValue(true),
    digest: vi.fn().mockResolvedValue('checksum'),
  };
}

describe('cloud backup orchestration', () => {
  test('preserves a completed backup when the completion response is lost', async () => {
    const deps = dependencies();
    const completed = { ...(await deps.createBackupRecord('user-1', 'manual', 'backup.json')), status: 'completed' as const, schema_version: 2 };
    deps.completeBackup = async () => { throw new Error('Response lost after server commit'); };
    vi.mocked(deps.fetchBackups).mockResolvedValue([completed]);
    await expect(performCloudBackup('user-1', 'manual', deps)).resolves.toMatchObject({ status: 'completed', schema_version: 2 });
    expect(deps.updateBackupRecord).not.toHaveBeenCalledWith('backup-1', 'user-1', { status: 'failed' });
  });
  test('validates a native downloaded Blob without Blob.text()', async () => {
    const deps = dependencies();
    const source = await deps.fetchBackupSourceData('user-1');
    const json = serializeBackupDocument('user-1', '1.0.0', source, deps.now().toISOString());
    const { blob, readAsText } = nativeDownloadedBlob(json);
    const record = await deps.updateBackupRecord('backup-1', 'user-1', {});
    await expect(downloadAndValidateBackup(
      { ...record, file_size_bytes: blob.size }, 'user-1', deps, blob,
    )).resolves.toEqual(JSON.parse(json));
    expect(readAsText).toHaveBeenCalledWith(blob, 'UTF-8');
    expect(deps.digest).toHaveBeenCalledWith(json);
  });

  test.each([
    ['checksum mismatch', '{}', null, 'different', 'checksum does not match'],
    ['size mismatch', '{}', 100, 'checksum', 'file size does not match'],
    ['invalid JSON', '{broken', null, 'checksum', 'Invalid backup file'],
  ])('still blocks a native Blob with %s', async (_name, json, size, checksum, message) => {
    const deps = dependencies();
    const record = await deps.updateBackupRecord('backup-1', 'user-1', {});
    const { blob } = nativeDownloadedBlob(json);
    await expect(downloadAndValidateBackup(
      { ...record, file_size_bytes: size, checksum_sha256: checksum }, 'user-1', deps, blob,
    )).rejects.toThrow(message);
  });

  test('rejects native file read failures before hashing the backup', async () => {
    const deps = dependencies();
    const record = await deps.updateBackupRecord('backup-1', 'user-1', {});
    const { blob } = nativeDownloadedBlob('{}', new Error('Native read failed'));
    await expect(downloadAndValidateBackup(
      { ...record, file_size_bytes: null }, 'user-1', deps, blob,
    )).rejects.toThrow('Native read failed');
    expect(deps.digest).not.toHaveBeenCalled();
  });

  test('creates and uploads an exact automatic backup document', async () => {
    const deps = dependencies();
    await performCloudBackup('user-1', 'automatic', deps);
    expect(deps.uploadBackupObject).toHaveBeenCalledOnce();
    expect(deps.updateBackupRecord).toHaveBeenCalledWith(
      'backup-1',
      'user-1',
      expect.objectContaining({
        status: 'completed',
        checksum_sha256: 'checksum',
        schema_version: 2,
      }),
    );
  });

  test('skips automatic backup when the preference is disabled', async () => {
    const deps = dependencies();
    vi.mocked(deps.fetchAutoBackupEnabled).mockResolvedValue(false);
    await expect(runEligibleAutomaticBackup('user-1', deps)).resolves.toBeNull();
    expect(deps.createBackupRecord).not.toHaveBeenCalled();
  });

  test('skips automatic backup when a completed one exists within 24 hours', async () => {
    const deps = dependencies();
    vi.mocked(deps.fetchBackups).mockResolvedValue([
      {
        ...(await vi.mocked(deps.createBackupRecord)('user-1', 'automatic', 'backup.json')),
        status: 'completed',
        created_at: '2026-07-16T00:00:00.000Z',
      },
    ]);
    vi.mocked(deps.createBackupRecord).mockClear();
    await expect(runEligibleAutomaticBackup('user-1', deps)).resolves.toBeNull();
    expect(deps.createBackupRecord).not.toHaveBeenCalled();
  });

  test('shares one in-flight automatic backup promise per user', async () => {
    const deps = dependencies();
    let release!: () => void;
    vi.mocked(deps.fetchBackupSourceData).mockImplementation(
      () => new Promise((resolve) => {
        release = () => resolve({
          profile: null,
          customCategories: [],
          transactions: [],
          monthlyBudgets: [],
          categoryLimits: [],
          savingsGoals: [],
          savingsContributions: [],
          reports: [],
          notificationPreferences: null,
          reminders: [],
          alerts: [],
        });
      }),
    );
    const first = runEligibleAutomaticBackup('user-1', deps);
    const second = runEligibleAutomaticBackup('user-1', deps);
    await vi.waitFor(() => expect(deps.createBackupRecord).toHaveBeenCalledOnce());
    release();
    await Promise.all([first, second]);
    expect(deps.createBackupRecord).toHaveBeenCalledOnce();
  });

  test('blocks a downloaded backup when its checksum differs', async () => {
    const deps = dependencies();
    vi.mocked(deps.digest).mockResolvedValue('tampered');
    const record = await vi.mocked(deps.updateBackupRecord)(
      'backup-1',
      'user-1',
      {},
    );
    await expect(
      downloadAndValidateBackup(
        { ...record, checksum_sha256: 'expected', file_size_bytes: null },
        'user-1',
        deps,
        new Blob(['{}']),
      ),
    ).rejects.toThrow('checksum does not match');
  });
});
