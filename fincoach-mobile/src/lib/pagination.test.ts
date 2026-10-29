import { describe, expect, test, vi } from 'vitest';
import { createHash } from 'node:crypto';
import { fetchAllRows } from './pagination';
import { fetchTransactions } from './transactions';
import { fetchReportSourceData } from './reports';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('expo-crypto', () => ({ CryptoDigestAlgorithm: { SHA256: 'SHA-256' }, digestStringAsync: async (_algorithm: string, value: string) => createHash('sha256').update(value).digest('hex') }));

describe('complete financial reads', () => {
  const rows = Array.from({ length: 1251 }, (_, id) => ({ id: String(id), amount: id + 1 }));
  test('transaction history and report inputs survive a server cap below page size', async () => {
    const ranges: number[] = [];
    const client: any = { from(table: string) {
      const dataset = table === 'transactions' ? rows : [];
      const query: any = { range(from: number, to: number) {
        if (table === 'transactions') ranges.push(from);
        return Promise.resolve({ data: dataset.slice(from, Math.min(to + 1, from + 200)), count: dataset.length, error: null });
      } };
      for (const method of ['select', 'eq', 'gte', 'lte', 'order']) query[method] = () => query;
      return query;
    } };
    const transactions = await fetchTransactions('owner', client);
    const report = await fetchReportSourceData('owner', { preset: 'custom', startDate: '2026-01-01', endDate: '2026-12-31', categoryId: null, reportType: 'multi_month' } as any, client);
    expect(transactions).toEqual(rows);
    expect(report.transactions).toEqual(rows);
    expect(transactions.reduce((sum, row) => sum + row.amount, 0)).toBe(1251 * 1252 / 2);
    expect(ranges).toEqual(Array.from({ length: 3 }, () => Array.from({ length: 7 }, (_, i) => i * 200)).flat());
  });
  test.each([
    [{ data: [], count: 2, error: null }],
    [{ data: [{ id: 'a' }], count: 2, error: null }, { data: [{ id: 'a' }], count: 2, error: null }],
    [{ data: [{ id: 'a' }], count: 2, error: null }, { data: [], count: 1, error: null }],
    [{ data: [], error: null }],
    [{ data: [{ id: 'a' }], count: 2, error: null }, { data: null, error: new Error('offline') }],
  ])('rejects incomplete, overlapping, changing, or failed reads: %j', async (...pages) => {
    let index = 0;
    await expect(fetchAllRows(() => ({ range: async () => pages[index++] as any }))).rejects.toThrow();
  });
});
