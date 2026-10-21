import { createHash } from 'node:crypto';
import { expect, test, vi } from 'vitest';
import { fetchReportSourceData, type ReportDataClient } from './reports';
import type { ReportSelection } from './types';
vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('expo-crypto', () => ({ CryptoDigestAlgorithm: { SHA256: 'SHA-256' }, digestStringAsync: async (_algorithm: string, value: string) => createHash('sha256').update(value).digest('hex') }));
const selection: ReportSelection = { preset: 'custom', reportType: 'custom', categoryId: null, startDate: '2026-10-01', endDate: '2026-10-31' };
function clientFor(passes: unknown[][], categoryPasses?: unknown[][]) {
  let pass = -1;
  const client = { from(table: string) {
    const query: Record<string, unknown> = { range(from: number, to: number) {
      if (table === 'transactions' && from === 0) pass++;
      const rows = table === 'transactions' ? passes[Math.min(pass, passes.length - 1)] : table === 'savings_goals' ? categoryPasses?.[pass] ?? [] : [];
      return Promise.resolve({ data: rows.slice(from, to + 1), count: rows.length, error: null });
    } };
    for (const name of ['select', 'eq', 'gte', 'lte', 'order']) query[name] = () => query;
    return query;
  } } as unknown as ReportDataClient;
  return { client, reads: () => pass + 1 };
}
test('only returns two consecutive agreeing complete reads', async () => {
  const { client, reads } = clientFor([[{ id: 'one', amount: 10 }], [{ id: 'one', amount: 20 }], [{ id: 'one', amount: 20 }]]);
  expect((await fetchReportSourceData('owner', selection, client)).transactions[0].amount).toBe(20);
  expect(reads()).toBe(3);
});
test('rejects continuing data changes after three complete reads', async () => {
  const { client, reads } = clientFor([[{ id: 'one', amount: 10 }], [{ id: 'one', amount: 20 }], [{ id: 'one', amount: 30 }]]);
  await expect(fetchReportSourceData('owner', selection, client)).rejects.toThrow(/changed.*loading/i);
  expect(reads()).toBe(3);
});
test('detects changed contextual datasets, not just transactions', async () => {
  const { client } = clientFor([[]], [[{ id: 'g', current_amount: 1 }], [{ id: 'g', current_amount: 2 }], [{ id: 'g', current_amount: 3 }]]);
  await expect(fetchReportSourceData('owner', selection, client)).rejects.toThrow(/changed.*loading/i);
});
test('canonical comparison ignores object key and row ordering', async () => {
  const { client, reads } = clientFor([[{ id: 'a', amount: 1 }, { id: 'b', amount: 2 }], [{ amount: 2, id: 'b' }, { amount: 1, id: 'a' }]]);
  expect((await fetchReportSourceData('owner', selection, client)).transactions).toHaveLength(2);
  expect(reads()).toBe(2);
});
test('rejects oversized dates before issuing a database request', async () => {
  const from = vi.fn();
  await expect(fetchReportSourceData('owner', { ...selection, startDate: '1900-01-01', endDate: '9999-12-31' }, { from } as unknown as ReportDataClient)).rejects.toThrow(/120/);
  expect(from).not.toHaveBeenCalled();
});

test('detects an embedded category rename with unchanged transaction ids and amounts', async () => {
  const row = { id: 'one', amount: 10, category: { id: 1, name: 'Food', type: 'expense' } };
  const renamed = { ...row, category: { ...row.category, name: 'Dining' } };
  const { client, reads } = clientFor([[row], [renamed], [renamed]]);
  expect((await fetchReportSourceData('owner', selection, client)).transactions[0].category.name).toBe('Dining');
  expect(reads()).toBe(3);
});

test('detects a count-preserving edit between transaction pages and returns agreeing later reads', async () => {
  let reads = 0;
  let changed = false;
  const rows = Array.from({ length: 1001 }, (_, id) => ({ id: String(id), amount: 1 }));
  const client = { from(table: string) {
    const query: Record<string, unknown> = { range(from: number, to: number) {
      if (table !== 'transactions') return Promise.resolve({ data: [], count: 0, error: null });
      if (from === 0) reads++;
      if (from > 0 && !changed) { rows[0] = { ...rows[0], amount: 99 }; changed = true; }
      return Promise.resolve({ data: structuredClone(rows.slice(from, to + 1)), count: rows.length, error: null });
    } };
    for (const name of ['select', 'eq', 'gte', 'lte', 'order']) query[name] = () => query;
    return query;
  } } as unknown as ReportDataClient;
  const source = await fetchReportSourceData('owner', selection, client);
  expect(source.transactions).toHaveLength(1001);
  expect(source.transactions[0].amount).toBe(99);
  expect(reads).toBe(3);
});
