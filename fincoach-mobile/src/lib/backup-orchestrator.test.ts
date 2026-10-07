import { describe, expect, test, vi } from 'vitest';

vi.mock('expo-constants', () => ({ default: { expoConfig: { version: '1.0.0' } } }));
vi.mock('expo-crypto', () => ({
  CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
  digestStringAsync: vi.fn().mockResolvedValue('checksum'),
}));
vi.mock('./export-backup', () => ({
  createBackupRecord: vi.fn(),
  deleteBackup: vi.fn(),
  downloadBackupObject: vi.fn(),
  fetchAutoBackupEnabled: vi.fn(),
  fetchBackups: vi.fn(),
  fetchBackupSourceData: vi.fn(),
  updateBackupRecord: vi.fn(),
  uploadBackupObject: vi.fn(),
}));

import {
  downloadAndValidateBackup,
  performCloudBackup,
  runEligibleAutomaticBackup,
  type BackupOrchestratorDependencies,
} from './backup-orchestrator';

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
        schema_version: 1,
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
