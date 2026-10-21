import { Directory, File, Paths } from 'expo-file-system';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

export type GeneratedExportFile = {
  uri: string;
  size: number | null;
  mimeType: 'text/csv' | 'application/pdf';
};

export type CurrentGeneratedExport = GeneratedExportFile & {
  fileName: string;
  format: 'csv' | 'pdf';
};

let currentExport: CurrentGeneratedExport | null = null;

// Exports hold personal financial data, so each one is deleted from the cache
// once it is replaced or the user finishes with it.
function discardExport(uri: string, platform: ExportFilePlatform) {
  try {
    platform.remove(uri);
  } catch (error) {
    console.warn('A previous export file could not be removed from the cache.', error);
  }
}

export function setCurrentExport(file: CurrentGeneratedExport, platform: ExportFilePlatform = defaultPlatform) {
  if (currentExport && currentExport.uri !== file.uri) discardExport(currentExport.uri, platform);
  currentExport = file;
}

export function getCurrentExport() {
  return currentExport;
}

export function clearCurrentExport(platform: ExportFilePlatform = defaultPlatform) {
  if (currentExport) discardExport(currentExport.uri, platform);
  currentExport = null;
}

export type ExportFilePlatform = {
  writeText: (fileName: string, content: string) => { uri: string; size: number | null };
  readBytes: (uri: string) => Promise<ArrayBuffer>;
  printHtml: (html: string) => Promise<{ uri: string; numberOfPages?: number }>;
  moveToExports: (uri: string, fileName: string) => Promise<{ uri: string; size: number | null }>;
  isSharingAvailable: () => Promise<boolean>;
  share: (
    uri: string,
    options: { mimeType: string; dialogTitle: string },
  ) => Promise<void>;
  remove: (uri: string) => void;
};

function exportDirectory() {
  const directory = new Directory(Paths.cache, 'fincoach-exports');
  directory.create({ idempotent: true, intermediates: true });
  return directory;
}

const defaultPlatform: ExportFilePlatform = {
  writeText(fileName, content) {
    const file = new File(exportDirectory(), fileName);
    file.create({ overwrite: true, intermediates: true });
    file.write(content);
    return { uri: file.uri, size: file.size };
  },
  readBytes(uri) {
    return new File(uri).arrayBuffer();
  },
  printHtml(html) {
    return Print.printToFileAsync({
      html,
      width: 595,
      height: 842,
    });
  },
  async moveToExports(uri, fileName) {
    const file = new File(uri);
    // move() updates file.uri to the new location.
    await file.move(new File(exportDirectory(), fileName), { overwrite: true });
    return { uri: file.uri, size: file.size };
  },
  isSharingAvailable() {
    return Sharing.isAvailableAsync();
  },
  async share(uri, options) {
    await Sharing.shareAsync(uri, options);
  },
  remove(uri) {
    const file = new File(uri);
    if (file.exists) file.delete();
  },
};

export function writeCsvExport(
  fileName: string,
  content: string,
  platform: ExportFilePlatform = defaultPlatform,
): GeneratedExportFile {
  const file = platform.writeText(fileName, content);
  return { ...file, mimeType: 'text/csv' };
}

export async function writePdfExport(
  html: string,
  platform: ExportFilePlatform = defaultPlatform,
): Promise<GeneratedExportFile> {
  const file = await platform.printHtml(html);
  return { uri: file.uri, size: null, mimeType: 'application/pdf' };
}

/** Printing names the PDF with a random UUID; move it so the shared file keeps
 * the export name shown to the user and its real size is known. */
export async function writeNamedPdfExport(
  fileName: string,
  html: string,
  platform: ExportFilePlatform = defaultPlatform,
): Promise<GeneratedExportFile> {
  const printed = await platform.printHtml(html);
  try {
    const file = await platform.moveToExports(printed.uri, fileName);
    return { ...file, mimeType: 'application/pdf' };
  } catch (error) {
    discardExport(printed.uri, platform);
    throw error;
  }
}

export function readExportFileBytes(
  uri: string,
  platform: ExportFilePlatform = defaultPlatform,
) {
  return platform.readBytes(uri);
}

export async function shareExportFile(
  file: GeneratedExportFile,
  platform: ExportFilePlatform = defaultPlatform,
) {
  if (!(await platform.isSharingAvailable())) {
    throw new Error('Sharing is not available on this device.');
  }
  await platform.share(file.uri, {
    mimeType: file.mimeType,
    dialogTitle: 'Share FinCoach export',
  });
}

export function removeCachedExport(
  uri: string,
  platform: ExportFilePlatform = defaultPlatform,
) {
  platform.remove(uri);
}
