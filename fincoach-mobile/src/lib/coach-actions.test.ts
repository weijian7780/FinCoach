import { describe, expect, it, vi } from 'vitest';

import { generateCoachReport, type CoachReportDependencies } from './coach-actions';
import type { CoachReportAttempt } from './types';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('./export-files', () => ({
  readExportFileBytes: vi.fn(),
  removeCachedExport: vi.fn(),
  writePdfExport: vi.fn(),
}));
vi.mock('./transactions', () => ({ fetchTransactionCategories: vi.fn() }));
vi.mock('./coach-api', () => ({ getReportAttempt: vi.fn() }));
// The real duplicate classifier decides whether an upload failure is a
// reservation conflict or a real storage error.
vi.mock('./reports', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./reports')>();
  return { ...actual, fetchReportSourceData: vi.fn(), uploadReportPdf: vi.fn() };
});

function serverAttempt(overrides: Partial<CoachReportAttempt> = {}): CoachReportAttempt {
  return {
    attempt_id: 'attempt-1',
    message_id: 'message-1',
    action_id: 'action-1',
    status: 'active',
    storage_path: 'user-1/coach/attempt-1.pdf',
    period: 'current_month',
    report_type: 'monthly',
    start_date: '2026-07-01',
    end_date: '2026-07-31',
    category_id: null,
    category_name: null,
    report_id: null, lease_valid: true, server_time: '2030-01-01T00:00:00Z',
    lease_expires_at: '2030-01-01T00:05:00Z',
    ...overrides,
  };
}

function createDependencies(
  overrides: Partial<CoachReportDependencies> = {},
): CoachReportDependencies {
  return {
    fetchCategories: vi.fn(async () => []),
    fetchSource: vi.fn(async () => ({
      transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [],
    })),
    compile: vi.fn(() => ({}) as never),
    createArtifact: vi.fn(() => ({
      title: 'July report',
      fileName: 'FinCoach_July_2026.pdf',
      reportKey: 'key',
      storagePath: 'user-1/local-placeholder.pdf',
      generatedAt: '2026-07-24T00:00:00.000Z',
    })),
    buildHtml: vi.fn(() => '<html />'),
    writePdf: vi.fn(async () => ({
      uri: 'file://report.pdf', size: 10, mimeType: 'application/pdf' as const,
    })),
    readBytes: vi.fn(async () => new ArrayBuffer(4)),
    uploadPdf: vi.fn(async () => ({ path: 'uploaded' })),
    fetchAttempt: vi.fn(async () => serverAttempt()),
    removeCached: vi.fn(),
    ...overrides,
  };
}

describe('coach report action', () => {
  it('returns the uploaded report even if deleting the cached file fails', async () => {
    const dependencies = createDependencies({ removeCached: vi.fn(() => { throw new Error('filesystem failure'); }) });
    await expect(generateCoachReport('user-1', serverAttempt(), dependencies)).resolves.toMatchObject({ storagePath: 'user-1/coach/attempt-1.pdf' });
  });
  it('preserves the upload error when cache cleanup also fails', async () => {
    const original = new Error('upload failed');
    const dependencies = createDependencies({ uploadPdf: vi.fn(async () => { throw original; }), removeCached: vi.fn(() => { throw new Error('cache failure'); }) });
    await expect(generateCoachReport('user-1', serverAttempt(), dependencies)).rejects.toBe(original);
  });
  it('rejects excessive frozen periods before fetching any financial source', async () => {
    const dependencies = createDependencies();
    await expect(generateCoachReport('user-1', serverAttempt({ start_date: '1900-01-01' }), dependencies)).rejects.toThrow(/120/);
    expect(dependencies.fetchSource).not.toHaveBeenCalled();
  });
  it('uses the frozen category id and dates despite duplicate or renamed categories', async () => {
    const dependencies = createDependencies({ fetchCategories: vi.fn(async () => [
      { id: 1, name: 'Food' }, { id: 9, name: 'Renamed category' },
    ] as never) });
    const frozen = serverAttempt({ category_id: 9, category_name: 'Food', report_type: 'monthly_category' });
    await generateCoachReport('user-1', frozen, dependencies);
    expect(dependencies.fetchSource).toHaveBeenCalledWith('user-1', expect.objectContaining({
      categoryId: 9, startDate: '2026-07-01', endDate: '2026-07-31', reportType: 'monthly_category',
    }));
  });

  it('refuses upload if the renderer loses its lease while writing the PDF', async () => {
    let lost = false;
    const dependencies = createDependencies({ writePdf: vi.fn(async () => {
      lost = true;
      return { uri: 'file://report.pdf', size: 10, mimeType: 'application/pdf' as const };
    }) });
    await expect(generateCoachReport('user-1', serverAttempt(), dependencies, () => {
      if (lost) throw new Error('lease lost');
    })).rejects.toThrow('lease lost');
    expect(dependencies.uploadPdf).not.toHaveBeenCalled();
    expect(dependencies.removeCached).toHaveBeenCalled();
  });
  it('renders, uploads to the server-reserved path, and removes the temporary private PDF', async () => {
    const calls: string[] = [];
    const dependencies = createDependencies({
      fetchSource: vi.fn(async () => {
        calls.push('fetch');
        return { transactions: [], monthlyBudgets: [], categoryLimits: [], savingsGoals: [] };
      }),
      compile: vi.fn(() => {
        calls.push('compile');
        return {} as never;
      }),
      writePdf: vi.fn(async () => {
        calls.push('pdf');
        return { uri: 'file://report.pdf', size: 10, mimeType: 'application/pdf' as const };
      }),
      uploadPdf: vi.fn(async (path: string) => {
        calls.push(`upload:${path}`);
        return { path };
      }),
      removeCached: vi.fn(() => {
        calls.push('cleanup');
      }),
    });

    await expect(generateCoachReport('user-1', serverAttempt(), dependencies)).resolves.toEqual({
      title: 'July report',
      fileName: 'FinCoach_July_2026.pdf',
      generatedAt: '2026-07-24T00:00:00.000Z',
      storagePath: 'user-1/coach/attempt-1.pdf',
    });

    expect(calls).toEqual([
      'fetch', 'compile', 'pdf', 'upload:user-1/coach/attempt-1.pdf', 'cleanup',
    ]);
    expect(dependencies.fetchAttempt).not.toHaveBeenCalled();
  });

  it('accepts a duplicate upload only while the same attempt can still publish', async () => {
    const duplicate = Object.assign(new Error('The resource already exists'), { statusCode: 409 });
    const dependencies = createDependencies({
      uploadPdf: vi.fn(async () => {
        throw duplicate;
      }),
      fetchAttempt: vi.fn(async () => serverAttempt({ status: 'active' })),
    });

    await expect(generateCoachReport('user-1', serverAttempt(), dependencies))
      .resolves.toMatchObject({ storagePath: 'user-1/coach/attempt-1.pdf' });
    expect(dependencies.fetchAttempt).toHaveBeenCalledWith('message-1', 'attempt-1');
  });

  it('never accepts a duplicate once the server says the attempt cannot publish', async () => {
    const duplicate = Object.assign(new Error('Duplicate'), { statusCode: '409' });
    const dependencies = createDependencies({
      uploadPdf: vi.fn(async () => {
        throw duplicate;
      }),
      fetchAttempt: vi.fn(async () => serverAttempt({ status: 'superseded' })),
    });

    await expect(generateCoachReport('user-1', serverAttempt(), dependencies)).rejects.toBe(duplicate);
    expect(dependencies.removeCached).toHaveBeenCalledWith('file://report.pdf');
  });

  it('never accepts a duplicate when the attempt state cannot be verified', async () => {
    const duplicate = Object.assign(new Error('The resource already exists'), { statusCode: 409 });
    const dependencies = createDependencies({
      uploadPdf: vi.fn(async () => {
        throw duplicate;
      }),
      fetchAttempt: vi.fn(async () => {
        throw new Error('offline');
      }),
    });

    await expect(generateCoachReport('user-1', serverAttempt(), dependencies)).rejects.toBe(duplicate);
  });

  it('reports storage failures that are not a reservation conflict', async () => {
    const failure = new Error('bucket unavailable');
    const dependencies = createDependencies({
      uploadPdf: vi.fn(async () => {
        throw failure;
      }),
    });

    await expect(generateCoachReport('user-1', serverAttempt(), dependencies)).rejects.toBe(failure);
    expect(dependencies.fetchAttempt).not.toHaveBeenCalled();
  });
});
