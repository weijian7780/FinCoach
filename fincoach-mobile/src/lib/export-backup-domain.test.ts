import { describe, expect, test } from 'vitest';

import {
  buildExportCsv,
  buildExportHtml,
  createBackupObjectPath,
  createExportFileName,
  createExportPreset,
  escapeCsv,
  selectAutomaticBackupsForDeletion,
  serializeBackupDocument,
  validateBackupDocument,
  validateExportSelection,
} from './export-backup-domain';
import type {
  BackupRecord,
  BackupSourceData,
  ExportSelection,
  ExportSourceData,
  FinancialBackupDocumentV1,
} from './types';

const selection: ExportSelection = {
  format: 'csv',
  startDate: '2026-07-01',
  endDate: '2026-07-31',
  contents: ['transaction', 'budget', 'savings', 'report'],
};

const exportSource: ExportSourceData = {
  transactions: [
    {
      id: 'transaction-1',
      user_id: 'user-1',
      category_id: 1,
      amount: 12.5,
      transaction_date: '2026-07-16',
      description: 'Cafe "A", KK',
      source: 'manual',
      receipt_image_path: null,
      created_at: '2026-07-16T01:00:00.000Z',
      updated_at: '2026-07-16T01:00:00.000Z',
      category: {
        id: 1,
        user_id: null,
        name: 'Food',
        type: 'expense',
        icon: 'restaurant',
        color: '#ff0000',
      },
    },
  ],
  monthlyBudgets: [
    {
      id: 'budget-1',
      user_id: 'user-1',
      month: '2026-07-01',
      limit_amount: 500,
      created_at: '2026-07-01T00:00:00.000Z',
      updated_at: '2026-07-01T00:00:00.000Z',
    },
  ],
  categoryLimits: [
    {
      id: 10,
      user_id: 'user-1',
      category_id: 1,
      month: '2026-07-01',
      amount: 200,
      created_at: '2026-07-01T00:00:00.000Z',
      updated_at: '2026-07-01T00:00:00.000Z',
    },
  ],
  savingsGoals: [
    {
      id: 'goal-1',
      user_id: 'user-1',
      name: '<script>alert(1)</script>',
      target_amount: 1000,
      current_amount: 250,
      deadline: '2026-12-31',
      created_at: '2026-07-01T00:00:00.000Z',
      updated_at: '2026-07-01T00:00:00.000Z',
    },
  ],
  reports: [
    {
      id: 1,
      user_id: 'user-1',
      period: '2026-07',
      type: 'monthly',
      generated_at: '2026-07-16T02:00:00.000Z',
    },
  ],
};

const backupSource: BackupSourceData = {
  profile: {
    id: 'user-1',
    email: 'student@example.com',
    full_name: 'Student',
    avatar_url: null,
    monthly_allowance: 1200,
    university: 'UMS Kota Kinabalu',
    year_of_study: 'Year 3',
    income_source: 'Allowance',
    financial_status: 'Stable',
    coaching_style: 'Supportive',
    onboarding_completed: true,
    spending_records_consent: 'granted',
    auto_backup_enabled: true,
    created_at: '2026-07-01T00:00:00.000Z',
    updated_at: '2026-07-01T00:00:00.000Z',
  },
  customCategories: [],
  transactions: exportSource.transactions.map(({ category: _category, ...transaction }) => transaction),
  monthlyBudgets: exportSource.monthlyBudgets,
  categoryLimits: exportSource.categoryLimits,
  savingsGoals: exportSource.savingsGoals,
  savingsContributions: [],
  reports: exportSource.reports,
  notificationPreferences: null,
  reminders: [],
  alerts: [],
};

function backupRecord(
  id: string,
  backupType: BackupRecord['backup_type'],
  status: BackupRecord['status'],
  createdAt: string,
): BackupRecord {
  return {
    id,
    user_id: 'user-1',
    backup_type: backupType,
    status,
    file_name: `${id}.json`,
    storage_path: `user-1/${backupType}/${id}.json`,
    file_size_bytes: 100,
    checksum_sha256: 'abc',
    schema_version: 1,
    last_restore_status: null,
    last_restored_at: null,
    completed_at: status === 'completed' ? createdAt : null,
    created_at: createdAt,
  };
}

describe('export selection', () => {
  test('requires at least one normalized export content row', () => {
    expect(validateExportSelection({ ...selection, contents: [] })).toBe(
      'Select at least one data section.',
    );
  });

  test('rejects reversed dates', () => {
    expect(
      validateExportSelection({
        ...selection,
        startDate: '2026-07-31',
        endDate: '2026-07-01',
      }),
    ).toBe('Start date must be on or before end date.');
  });

  test('creates Malaysia-local current-month dates', () => {
    expect(createExportPreset('current_month', new Date(2026, 6, 16, 23, 30))).toEqual({
      startDate: '2026-07-01',
      endDate: '2026-07-31',
    });
  });
});

describe('export generation', () => {
  test('escapes RFC 4180 values', () => {
    expect(escapeCsv('Cafe "A", KK')).toBe('"Cafe ""A"", KK"');
  });

  test('generates selected CSV sections with a UTF-8 byte-order mark', () => {
    const csv = buildExportCsv(exportSource, selection);
    expect(csv.startsWith('\uFEFFTransactions')).toBe(true);
    expect(csv).toContain('"Cafe ""A"", KK"');
    expect(csv).toContain('Budgets');
    expect(csv).toContain('Savings Goals');
    expect(csv).toContain('Generated Reports');
  });

  test('escapes user-controlled values in PDF HTML', () => {
    const html = buildExportHtml(exportSource, { ...selection, format: 'pdf' });
    expect(html).toContain('FinCoach Financial Export');
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
  });

  test('creates stable file names', () => {
    expect(createExportFileName(selection)).toBe('FinCoach_2026-07-01_to_2026-07-31.csv');
  });
});

describe('backup documents', () => {
  test('serializes the same source deterministically', () => {
    const first = serializeBackupDocument('user-1', '1.0.0', backupSource, '2026-07-16T03:00:00.000Z');
    const second = serializeBackupDocument('user-1', '1.0.0', backupSource, '2026-07-16T03:00:00.000Z');
    expect(first).toBe(second);
    expect(JSON.parse(first)).toMatchObject({ schemaVersion: 1, userId: 'user-1' });
  });

  test('rejects cross-user and unsupported backup documents', () => {
    const document = JSON.parse(
      serializeBackupDocument('user-1', '1.0.0', backupSource, '2026-07-16T03:00:00.000Z'),
    ) as FinancialBackupDocumentV1;

    expect(() => validateBackupDocument(document, 'user-2')).toThrow(
      'This backup belongs to another account.',
    );
    expect(() =>
      validateBackupDocument({ ...document, schemaVersion: 2 } as unknown, 'user-1'),
    ).toThrow('This backup version is not supported.');
  });

  test('creates owner-folder backup paths', () => {
    expect(
      createBackupObjectPath('user-1', 'manual', 'backup-1', new Date('2026-07-16T03:00:00.000Z')),
    ).toBe('user-1/manual/2026-07-16T03-00-00-000Z-backup-1.json');
  });

  test('retains the latest five completed automatic backups only', () => {
    const records = [
      backupRecord('manual', 'manual', 'completed', '2026-07-01T00:00:00.000Z'),
      backupRecord('failed', 'automatic', 'failed', '2026-07-02T00:00:00.000Z'),
      ...Array.from({ length: 7 }, (_, index) =>
        backupRecord(
          `auto-${index + 1}`,
          'automatic',
          'completed',
          `2026-07-${String(index + 3).padStart(2, '0')}T00:00:00.000Z`,
        ),
      ),
    ];

    expect(selectAutomaticBackupsForDeletion(records).map((record) => record.id)).toEqual([
      'auto-2',
      'auto-1',
    ]);
  });
});
