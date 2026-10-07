import { describe, expect, it, vi } from 'vitest';
import { generateCoachReport } from './coach-actions';

vi.mock('./export-files', () => ({
  readExportFileBytes: vi.fn(),
  removeCachedExport: vi.fn(),
  writePdfExport: vi.fn(),
}));
vi.mock('./reports', () => ({
  fetchReportSourceData: vi.fn(),
  saveReportRecord: vi.fn(),
  uploadReportPdf: vi.fn(),
}));
vi.mock('./transactions', () => ({ fetchTransactionCategories: vi.fn() }));

describe('coach report action', () => {
  it('generates, uploads, records, and removes the temporary private PDF', async () => {
    const calls: string[] = [];
    const dependencies = {
      fetchCategories: vi.fn(async () => []),
      fetchSource: vi.fn(async () => {
        calls.push('fetch');
        return { transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [] };
      }),
      compile: vi.fn(() => {
        calls.push('compile');
        return { selection: {} } as never;
      }),
      createArtifact: vi.fn(() => ({
        title: 'July report',
        fileName: 'report.pdf',
        reportKey: 'key',
        storagePath: 'user-1/report.pdf',
        generatedAt: '2026-07-24T00:00:00.000Z',
      })),
      buildHtml: vi.fn(() => '<html />'),
      writePdf: vi.fn(async () => {
        calls.push('pdf');
        return { uri: 'file://report.pdf', size: 10, mimeType: 'application/pdf' as const };
      }),
      readBytes: vi.fn(async () => new ArrayBuffer(4)),
      uploadPdf: vi.fn(async () => {
        calls.push('upload');
        return { path: 'user-1/report.pdf' };
      }),
      saveRecord: vi.fn(async () => {
        calls.push('save');
        return { id: 42 };
      }),
      removeCached: vi.fn(() => calls.push('cleanup')),
    };

    await expect(generateCoachReport('user-1', {
      period: 'current_month',
      start_date: '2026-07-01',
      end_date: '2026-07-31',
      category_name: null,
    }, dependencies)).resolves.toEqual({
      reportId: 42,
      title: 'July report',
      storagePath: 'user-1/report.pdf',
    });

    expect(calls).toEqual(['fetch', 'compile', 'pdf', 'upload', 'save', 'cleanup']);
  });
});
