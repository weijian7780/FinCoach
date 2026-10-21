import { createHash } from 'node:crypto';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { blobBytes, captureBackupAttachments, prepareRestoreAttachments, removeBackupAttachmentCopies } from './backup-attachments';
import { backupCounts } from './backup-v2-domain';
import type { BackupSourceData, FinancialBackupDocumentV2 } from './types';
import type { ExportBackupDataClient } from './export-backup';

vi.mock('expo-crypto', () => ({ CryptoDigestAlgorithm: { SHA256: 'SHA-256' }, randomUUID: () => 'test-attempt' }));
vi.mock('./supabase', () => ({ supabase: {} }));
const hash = async (bytes: ArrayBuffer) => createHash('sha256').update(new Uint8Array(bytes)).digest('hex');
const empty: BackupSourceData = { profile: null, customCategories: [], userCategories: [], transactions: [], monthlyBudgets: [],
  categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [], notificationPreferences: null, reminders: [], alerts: [] };

function storage() {
  const files = new Map<string, Blob>([['receipts/owner/source.png', new Blob(['original'], { type: 'image/png' })]]);
  const client = { storage: { from: (bucket: string) => ({
    download: async (path: string) => ({ data: files.get(`${bucket}/${path}`) ?? null, error: files.has(`${bucket}/${path}`) ? null : { message: 'not found' } }),
    upload: async (path: string, body: ArrayBuffer, options: { contentType: string; upsert: boolean }) => {
      const key = `${bucket}/${path}`;
      if (files.has(key) && !options.upsert) return { data: null, error: { message: 'already exists' } };
      files.set(key, new Blob([body], { type: options.contentType }));
      return { data: { path }, error: null };
    },
    remove: async (paths: string[]) => { paths.forEach(path => files.delete(`${bucket}/${path}`)); return { data: paths, error: null }; },
    list: async (prefix: string, options: { limit: number }) => ({ data: [...files.keys()].filter(k => k.startsWith(`${bucket}/${prefix}/`))
      .slice(0, options.limit).map(k => ({ name: k.split('/').at(-1)! })), error: null }),
  }) } } as unknown as ExportBackupDataClient;
  return { files, client };
}

function sourceWithPaths(paths = ['owner/source.png']) {
  return { ...empty, transactions: paths.map((path, i) => ({ id: `t-${i}`, user_id: 'owner', receipt_image_path: path })) } as BackupSourceData;
}

afterEach(() => vi.unstubAllGlobals());

describe('attachment recovery contract', () => {
  test('stores an independent verified copy and recovers deleted originals', async () => {
    const { files, client } = storage();
    const source = sourceWithPaths();
    const attachments = await captureBackupAttachments('owner', 'backup', source, client, hash);
    files.delete('receipts/owner/source.png');
    const document: FinancialBackupDocumentV2 = { schemaVersion: 2, userId: 'owner', appVersion: '1', createdAt: '2026-10-01', data: source, counts: backupCounts(source), attachments };
    const result = await prepareRestoreAttachments('backup', document, client, hash);
    expect(await files.get(`receipts/${result.paths[0].restoredPath}`)!.text()).toBe('original');
    expect(await files.get(`financial-backups/${attachments[0].backupPath}`)!.text()).toBe('original');
  });
  test('keeps distinct identical-content originals independently deletable', async () => {
    const { files, client } = storage();
    files.set('receipts/owner/second.png', files.get('receipts/owner/source.png')!);
    const source = sourceWithPaths(['owner/source.png', 'owner/second.png']);
    const attachments = await captureBackupAttachments('owner', 'backup', source, client, hash);
    const result = await prepareRestoreAttachments('backup', { schemaVersion: 2, userId: 'owner', appVersion: '1', createdAt: '2026-10-01', data: source, counts: backupCounts(source), attachments }, client, hash);
    expect(result.paths[0].restoredPath).not.toBe(result.paths[1].restoredPath);
    files.delete(`receipts/${result.paths[0].restoredPath}`);
    expect(await files.get(`receipts/${result.paths[1].restoredPath}`)!.text()).toBe('original');
  });
  test('does not overwrite a currently changed original file', async () => {
    const { files, client } = storage();
    const source = sourceWithPaths();
    const attachments = await captureBackupAttachments('owner', 'backup', source, client, hash);
    files.set('receipts/owner/source.png', new Blob(['newer'], { type: 'image/png' }));
    const result = await prepareRestoreAttachments('backup', { schemaVersion: 2, userId: 'owner', appVersion: '1', createdAt: '2026-10-01', data: source, counts: backupCounts(source), attachments }, client, hash);
    expect(await files.get('receipts/owner/source.png')!.text()).toBe('newer');
    expect(await files.get(`receipts/${result.paths[0].restoredPath}`)!.text()).toBe('original');
  });
  test('blocks missing required files and cleans earlier copies', async () => {
    const { files, client } = storage();
    await expect(captureBackupAttachments('owner', 'backup', sourceWithPaths(['owner/source.png', 'owner/missing.png']), client, hash)).rejects.toThrow('unavailable');
    expect([...files.keys()]).toEqual(['receipts/owner/source.png']);
  });
  test('blocks a corrupted saved attachment before restoring records', async () => {
    const { files, client } = storage();
    const source = sourceWithPaths();
    const attachments = await captureBackupAttachments('owner', 'backup', source, client, hash);
    files.set(`financial-backups/${attachments[0].backupPath}`, new Blob(['tampered'], { type: 'image/png' }));
    await expect(prepareRestoreAttachments('backup', { schemaVersion: 2, userId: 'owner', appVersion: '1', createdAt: '2026-10-01', data: source, counts: backupCounts(source), attachments }, client, hash)).rejects.toThrow('checksum');
    expect([...files.keys()].filter(k => k.includes('/restored/'))).toHaveLength(0);
  });
  test('deletes every copy above one Storage list page', async () => {
    const { files, client } = storage();
    for (let i = 0; i < 205; i++) files.set(`financial-backups/owner/assets/backup/file-${i}`, new Blob(['test']));
    await removeBackupAttachmentCopies('owner', 'backup', client);
    expect([...files.keys()]).toEqual(['receipts/owner/source.png']);
  });
  test('reads native binary Blobs without arrayBuffer()', async () => {
    vi.stubGlobal('FileReader', class {
      result = 'data:image/png;base64,b3JpZ2luYWw=';
      onload?: () => void;
      readAsDataURL() { queueMicrotask(() => this.onload?.()); }
    });
    expect(new TextDecoder().decode(await blobBytes({} as Blob))).toBe('original');
  });
});
