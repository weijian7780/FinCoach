import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('Financial Data Export and Backup UI', () => {
  test('routes App Settings to the implemented module', () => {
    const settings = read('src', 'app', 'profile', 'settings.tsx');
    expect(settings).toContain("router.push('/export-backup'");
    expect(settings).not.toContain('Export & Backup will be available in a later update.');
  });

  test('registers the export, success, and restore routes', () => {
    const layout = read('src', 'app', '_layout.tsx');
    expect(layout).toContain('name="export-backup/index"');
    expect(layout).toContain('name="export-backup/success"');
    expect(layout).toContain('name="export-backup/restore"');
  });

  test('runs eligible automatic backup after sign-in and foreground activation', () => {
    const auth = read('src', 'lib', 'auth-context.tsx');
    expect(auth).toContain('runEligibleAutomaticBackup');
    expect(auth).toContain("state === 'active'");
  });

  test('provides real export and cloud-backup actions', () => {
    const screen = read('src', 'app', 'export-backup', 'index.tsx');
    const sheet = read('src', 'components', 'export-backup', 'export-sheet.tsx');
    expect(screen).toContain('Export as CSV');
    expect(screen).toContain('Export as PDF');
    expect(screen).toContain('Create PDF or CSV files from your financial records.');
    expect(screen).toContain('Auto-backup to cloud');
    expect(screen).toContain('Back up now');
    expect(screen).toContain('Restore from backup');
    expect(screen).toContain('createDataExport');
    expect(screen).toContain('performCloudBackup');
    expect(sheet).toContain('CSV spreadsheet');
    expect(sheet).toContain('PDF document');
    expect(sheet).toContain('Transactions');
    expect(sheet).toContain('Budgets');
    expect(sheet).toContain('Savings');
    expect(sheet).not.toContain("label: 'Reports'");
  });

  test('warns before replacing current data and uses fetched backup metadata', () => {
    const restore = read('src', 'app', 'export-backup', 'restore.tsx');
    expect(restore).toContain('Restoring will replace your current data');
    expect(restore).toContain('fetchBackups');
    expect(restore).toContain('downloadBackupObject');
    expect(restore).toContain('restoreFinancialBackup');
    expect(restore).not.toMatch(/July \d{1,2}, 2026/);
    expect(restore).not.toMatch(/\b\d+(?:\.\d+)? MB\b/);
  });
});
