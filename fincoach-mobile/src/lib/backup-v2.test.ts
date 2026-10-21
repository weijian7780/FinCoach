import { describe, expect, test, vi } from 'vitest';
import { buildExportCsv, buildExportHtml, escapeCsv, validateBackupDocument } from './export-backup-domain';
import { fetchBackupSourceData, fetchExportSourceData, type ExportBackupDataClient } from './export-backup';
import type { BackupSourceData, ExportSourceData } from './types';

vi.mock('./supabase', () => ({ supabase: {} }));

const empty: BackupSourceData = { profile: null, customCategories: [], userCategories: [], transactions: [],
  monthlyBudgets: [], categoryLimits: [], savingsGoals: [], savingsContributions: [], reports: [],
  notificationPreferences: null, reminders: [], alerts: [] };

describe('complete backup snapshot', () => {
  test('loads more than 1000 records from one server snapshot', async () => {
    const transactions = Array.from({ length: 1105 }, (_, i) => ({ id: `t-${i}`, user_id: 'owner' }));
    const client = { rpc: async (name: string) => name === 'financial_backup_snapshot_v2'
      ? { data: { ...empty, transactions }, error: null } : { data: null, error: new Error('Wrong RPC') },
      from: () => { throw new Error('Backup must not issue separate table queries'); } } as unknown as ExportBackupDataClient;
    expect((await fetchBackupSourceData('owner', client)).transactions).toHaveLength(1105);
  });
});

describe('export completeness', () => {
  test('retrieves every row when server returns fewer rows than requested', async () => {
    const values = Array.from({ length: 1105 }, (_, i) => ({ id: `t-${i}`, transaction_date: '2026-10-01' }));
    const client = { from: (table: string) => {
      const items = table === 'transactions' ? values : [];
      let offset = 0;
      const query = { select: () => query, eq: () => query, gte: () => query, lte: () => query,
        order: () => query, range: (start: number) => { offset = start; return query; },
        then: (done: (r: unknown) => unknown) => Promise.resolve({ data: items.slice(offset, offset + 137), count: items.length, error: null }).then(done) };
      return query;
    } } as unknown as ExportBackupDataClient;
    const result = await fetchExportSourceData('owner', { startDate: '2026-10-01', endDate: '2026-10-07', contents: ['transaction'], format: 'csv' }, client);
    expect(result.transactions).toHaveLength(1105);
    expect(new Set(result.transactions.map(t => t.id)).size).toBe(1105);
  });
});

describe('safe export fields', () => {
  test.each(['=1+1', '+CMD', '-CMD', '@SUM(A1)', '\t=1+1', '  =1+1'])('forces formula-like text to a text cell: %s', value => {
    expect(escapeCsv(value)).toContain("'");
  });
  test('uses the same source field and readable budget category in PDF and CSV', () => {
    const source = { transactions: [{ transaction_date: '2026-10-01', description: 'Food', amount: 3,
      source: 'receipt', category: { name: 'Food', type: 'expense' } }], monthlyBudgets: [],
      categoryLimits: [{ month: '2026-10-01', amount: 100, category_id: 7, category: { name: 'Food' } }], savingsGoals: [], reports: [] } as unknown as ExportSourceData;
    const selection = { startDate: '2026-10-01', endDate: '2026-10-07', format: 'csv' as const, contents: ['transaction', 'budget'] as const };
    const csv = buildExportCsv(source, { ...selection, contents: [...selection.contents] });
    const html = buildExportHtml(source, { ...selection, contents: [...selection.contents] });
    expect(html).toContain('<th>Source</th>');
    expect(html).toContain('<td>receipt</td>');
    expect(html).not.toContain('Category 7');
    expect(csv).toContain('Category,Food');
  });
  test('uses Malaysia calendar dates for report filtering', () => {
    const source = { transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [], reports: [
      { period: 'included', type: 'monthly', generated_at: '2026-09-30T16:30:00Z' },
      { period: 'excluded', type: 'monthly', generated_at: '2026-10-31T16:30:00Z' },
    ] } as unknown as ExportSourceData;
    const selection = { startDate: '2026-10-01', endDate: '2026-10-31', format: 'csv' as const, contents: ['report' as const] };
    expect(buildExportCsv(source, selection)).toContain('included');
    expect(buildExportCsv(source, selection)).not.toContain('excluded');
  });
});

describe('v2 preflight', () => {
  test('rejects a v2 document whose counts claim missing records', () => {
    const counts = Object.fromEntries(Object.keys(empty).map(key => [key, key === 'transactions' ? 10 : 0]));
    expect(() => validateBackupDocument({ schemaVersion: 2, userId: 'owner', appVersion: '1',
      createdAt: '2026-10-01T00:00:00Z', data: empty, counts, attachments: [] }, 'owner')).toThrow(/count|complete/i);
  });
  test('accepts a complete empty v2 backup', () => {
    const counts = Object.fromEntries(Object.keys(empty).map(key => [key, 0]));
    expect(validateBackupDocument({ schemaVersion: 2, userId: 'owner', appVersion: '1',
      createdAt: '2026-10-01T00:00:00Z', data: empty, counts, attachments: [] }, 'owner').schemaVersion).toBe(2);
  });
});
