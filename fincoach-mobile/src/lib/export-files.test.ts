import { describe, expect, test, vi } from 'vitest';

vi.mock('expo-file-system', () => ({ Directory: class {}, File: class {}, Paths: {} }));
vi.mock('expo-print', () => ({ printToFileAsync: vi.fn() }));
vi.mock('expo-sharing', () => ({ isAvailableAsync: vi.fn(), shareAsync: vi.fn() }));

import {
  clearCurrentExport,
  getCurrentExport,
  setCurrentExport,
  shareExportFile,
  writeCsvExport,
  writePdfExport,
  type ExportFilePlatform,
} from './export-files';

function platform(): ExportFilePlatform {
  return {
    writeText: vi.fn().mockReturnValue({ uri: 'file:///cache/exports/report.csv', size: 18 }),
    printHtml: vi.fn().mockResolvedValue({ uri: 'file:///cache/report.pdf', numberOfPages: 2 }),
    isSharingAvailable: vi.fn().mockResolvedValue(true),
    share: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn(),
  };
}

describe('export file platform', () => {
  test('writes CSV text to the export cache', () => {
    const adapter = platform();
    expect(writeCsvExport('report.csv', '\uFEFFTransactions', adapter)).toEqual({
      uri: 'file:///cache/exports/report.csv',
      size: 18,
      mimeType: 'text/csv',
    });
    expect(adapter.writeText).toHaveBeenCalledWith('report.csv', '\uFEFFTransactions');
  });

  test('creates a PDF from escaped HTML', async () => {
    const adapter = platform();
    await expect(writePdfExport('<html>Report</html>', adapter)).resolves.toEqual({
      uri: 'file:///cache/report.pdf',
      size: null,
      mimeType: 'application/pdf',
    });
    expect(adapter.printHtml).toHaveBeenCalledWith('<html>Report</html>');
  });

  test('shares files with their real MIME type', async () => {
    const adapter = platform();
    await shareExportFile(
      { uri: 'file:///cache/report.pdf', size: null, mimeType: 'application/pdf' },
      adapter,
    );
    expect(adapter.share).toHaveBeenCalledWith('file:///cache/report.pdf', {
      mimeType: 'application/pdf',
      dialogTitle: 'Share FinCoach export',
    });
  });

  test('fails clearly when native sharing is unavailable', async () => {
    const adapter = platform();
    vi.mocked(adapter.isSharingAvailable).mockResolvedValue(false);
    await expect(
      shareExportFile(
        { uri: 'file:///cache/report.csv', size: 10, mimeType: 'text/csv' },
        adapter,
      ),
    ).rejects.toThrow('Sharing is not available on this device.');
  });

  test('keeps generated file metadata only for the current app session', () => {
    clearCurrentExport();
    expect(getCurrentExport()).toBeNull();

    setCurrentExport({
      fileName: 'FinCoach_2026-07-01_to_2026-07-31.csv',
      format: 'csv',
      uri: 'file:///cache/report.csv',
      size: 10,
      mimeType: 'text/csv',
    });

    expect(getCurrentExport()?.fileName).toBe('FinCoach_2026-07-01_to_2026-07-31.csv');
    clearCurrentExport();
    expect(getCurrentExport()).toBeNull();
  });
});
