import { describe, expect, test, vi } from 'vitest';

vi.mock('expo-file-system', () => ({ Directory: class {}, File: class {}, Paths: {} }));
vi.mock('expo-print', () => ({ printToFileAsync: vi.fn() }));
vi.mock('expo-sharing', () => ({ isAvailableAsync: vi.fn(), shareAsync: vi.fn() }));

import {
  clearCurrentExport,
  getCurrentExport,
  readExportFileBytes,
  setCurrentExport,
  shareExportFile,
  writeCsvExport,
  writeNamedPdfExport,
  writePdfExport,
  type ExportFilePlatform,
} from './export-files';

function platform(): ExportFilePlatform {
  return {
    writeText: vi.fn().mockReturnValue({ uri: 'file:///cache/exports/report.csv', size: 18 }),
    readBytes: vi.fn().mockResolvedValue(new ArrayBuffer(12)),
    printHtml: vi.fn().mockResolvedValue({ uri: 'file:///cache/report.pdf', numberOfPages: 2 }),
    moveToExports: vi.fn(),
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

  test('reads a generated PDF into uploadable bytes', async () => {
    const adapter = platform();
    await expect(
      readExportFileBytes('file:///cache/report.pdf', adapter),
    ).resolves.toHaveProperty('byteLength', 12);
    expect(adapter.readBytes).toHaveBeenCalledWith('file:///cache/report.pdf');
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

describe('export file lifecycle', () => {
  test('moves a printed PDF to the export name and reports its size', async () => {
    const adapter = platform();
    vi.mocked(adapter.moveToExports).mockResolvedValue({ uri: 'file:///cache/fincoach-exports/FinCoach.pdf', size: 2048 });
    await expect(writeNamedPdfExport('FinCoach.pdf', '<html/>', adapter)).resolves.toEqual({
      uri: 'file:///cache/fincoach-exports/FinCoach.pdf', size: 2048, mimeType: 'application/pdf',
    });
    expect(adapter.moveToExports).toHaveBeenCalledWith('file:///cache/report.pdf', 'FinCoach.pdf');
  });

  test('removes the printed PDF when it cannot be renamed', async () => {
    const adapter = platform();
    vi.mocked(adapter.moveToExports).mockRejectedValue(new Error('disk full'));
    await expect(writeNamedPdfExport('FinCoach.pdf', '<html/>', adapter)).rejects.toThrow('disk full');
    expect(adapter.remove).toHaveBeenCalledWith('file:///cache/report.pdf');
  });

  test('deletes the previous export file when replaced or finished', () => {
    const adapter = platform();
    clearCurrentExport(adapter);
    const file = (uri: string) => ({ fileName: 'x', format: 'csv' as const, uri, size: 1, mimeType: 'text/csv' as const });
    setCurrentExport(file('file:///a.csv'), adapter);
    setCurrentExport(file('file:///a.csv'), adapter);
    expect(adapter.remove).not.toHaveBeenCalled();
    setCurrentExport(file('file:///b.csv'), adapter);
    expect(adapter.remove).toHaveBeenCalledWith('file:///a.csv');
    clearCurrentExport(adapter);
    expect(adapter.remove).toHaveBeenCalledWith('file:///b.csv');
    expect(getCurrentExport()).toBeNull();
  });
});
