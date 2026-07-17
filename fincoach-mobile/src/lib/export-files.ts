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

export function setCurrentExport(file: CurrentGeneratedExport) {
  currentExport = file;
}

export function getCurrentExport() {
  return currentExport;
}

export function clearCurrentExport() {
  currentExport = null;
}

export type ExportFilePlatform = {
  writeText: (fileName: string, content: string) => { uri: string; size: number | null };
  printHtml: (html: string) => Promise<{ uri: string; numberOfPages?: number }>;
  isSharingAvailable: () => Promise<boolean>;
  share: (
    uri: string,
    options: { mimeType: string; dialogTitle: string },
  ) => Promise<void>;
  remove: (uri: string) => void;
};

const defaultPlatform: ExportFilePlatform = {
  writeText(fileName, content) {
    const directory = new Directory(Paths.cache, 'fincoach-exports');
    directory.create({ idempotent: true, intermediates: true });
    const file = new File(directory, fileName);
    file.create({ overwrite: true, intermediates: true });
    file.write(content);
    return { uri: file.uri, size: file.size };
  },
  printHtml(html) {
    return Print.printToFileAsync({ html });
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
