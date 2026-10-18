import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, vi } from 'vitest';
import { performCloudBackup, downloadAndValidateBackup, type BackupOrchestratorDependencies } from '../src/lib/backup-orchestrator';
import type { BackupRecord, BackupSourceData } from '../src/lib/types';

vi.mock('expo-constants', () => ({ default: { expoConfig: { version: '1.0.0' } } }));
vi.mock('expo-crypto', () => ({ CryptoDigestAlgorithm: { SHA256: 'SHA-256' } }));
vi.mock('../src/lib/supabase', () => ({ supabase: {} }));

test.skipIf(process.env.FINCOACH_DEEP_AUDIT !== '1')('audit cloud failures and backup validation without network', async () => {
  const checks: { name: string; passed: boolean; detail?: unknown }[] = [];
  const check = (name: string, passed: boolean, detail?: unknown) => checks.push({ name, passed, detail });
  function scenario() {
    let record: BackupRecord = { id: 'new', user_id: 'test-owner', backup_type: 'automatic', status: 'pending',
      file_name: 'test.json', storage_path: null, file_size_bytes: null, checksum_sha256: null, schema_version: 1,
      last_restore_status: null, last_restored_at: null, completed_at: null, created_at: '2026-10-10T00:00:00Z' };
    let json = '';
    const source: BackupSourceData = { profile: null, customCategories: [], userCategories: [], transactions: [],
      monthlyBudgets: [], categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [],
      notificationPreferences: null, reminders: [], alerts: [] };
    const deps: BackupOrchestratorDependencies = {
      now: () => new Date('2026-10-10T00:00:00Z'), appVersion: 'audit',
      createBackupRecord: async () => record,
      updateBackupRecord: async (_id, _owner, updates) => (record = { ...record, ...updates }),
      fetchBackupSourceData: async () => source,
      uploadBackupObject: async (path, bytes) => { json = new TextDecoder().decode(bytes); return { path }; },
      fetchBackups: async () => [], deleteBackup: async () => {}, fetchAutoBackupEnabled: async () => true,
      digest: async content => createHash('sha256').update(content).digest('hex'),
    };
    return { deps, record: () => record, json: () => json };
  }
  const readFailure = scenario();
  readFailure.deps.fetchBackupSourceData = async () => { throw new Error('simulated source read failed'); };
  await expect(performCloudBackup('test-owner', 'manual', readFailure.deps)).rejects.toThrow('source read failed');
  check('source query failure is not marked completed', readFailure.record().status === 'failed' && !readFailure.json());
  const uploadFailure = scenario();
  uploadFailure.deps.uploadBackupObject = async () => { throw new Error('simulated storage outage'); };
  await expect(performCloudBackup('test-owner', 'manual', uploadFailure.deps)).rejects.toThrow('storage outage');
  check('upload failure is not marked completed', uploadFailure.record().status === 'failed');
  const good = scenario();
  await performCloudBackup('test-owner', 'manual', good.deps);
  const blob = new Blob([good.json()]);
  await expect(downloadAndValidateBackup({ ...good.record(), file_size_bytes: 1 }, 'test-owner', good.deps, blob)).rejects.toThrow('file size does not match');
  check('wrong file size rejected', true);
  await expect(downloadAndValidateBackup(good.record(), 'different-owner', good.deps, blob)).rejects.toThrow('not available');
  check('wrong owner rejected', true);
  const invalidVersion = JSON.stringify({ ...JSON.parse(good.json()), schemaVersion: 999 });
  await expect(downloadAndValidateBackup({ ...good.record(), file_size_bytes: Buffer.byteLength(invalidVersion),
    checksum_sha256: await good.deps.digest(invalidVersion) }, 'test-owner', good.deps, new Blob([invalidVersion]))).rejects.toThrow('version is not supported');
  check('unsupported backup version rejected', true);
  const malformed = '{malformed';
  await expect(downloadAndValidateBackup({ ...good.record(), file_size_bytes: Buffer.byteLength(malformed),
    checksum_sha256: await good.deps.digest(malformed) }, 'test-owner', good.deps, new Blob([malformed]))).rejects.toThrow('Invalid backup file');
  check('invalid JSON rejected even with matching checksum', true);

  const cleanupFailure = scenario();
  cleanupFailure.deps.fetchBackups = async () => Array.from({ length: 6 }, (_, index) => ({
    ...cleanupFailure.record(), id: `old-${index}`, status: 'completed' as const, created_at: `2026-09-0${index + 1}T00:00:00Z`,
  }));
  cleanupFailure.deps.deleteBackup = async () => { throw new Error('simulated retention delete failed'); };
  await expect(performCloudBackup('test-owner', 'automatic', cleanupFailure.deps)).resolves.toMatchObject({ status: 'completed' });
  check('retention cleanup failure preserves successfully uploaded backup as completed', cleanupFailure.record().status === 'completed',
    { finalStatus: cleanupFailure.record().status, hasUploadedJson: !!cleanupFailure.json(), hasStoragePath: !!cleanupFailure.record().storage_path });
  const directory = resolve('../output/export-backup-v2-20261010');
  mkdirSync(directory, { recursive: true });
  writeFileSync(resolve(directory, 'failure-injection-results.json'), JSON.stringify({ environment: 'Production orchestrator with injected I/O failures; no network', checks }, null, 2));
  expect(checks.filter(c => !c.passed), 'Audit failures are saved in failure-injection-results.json').toEqual([]);
});
