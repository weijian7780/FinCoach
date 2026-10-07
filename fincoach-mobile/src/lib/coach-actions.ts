import { reportSelectionFromCoachAction } from './coach-agent';
import {
  readExportFileBytes,
  removeCachedExport,
  writePdfExport,
} from './export-files';
import { compileFinancialReport } from './report-domain';
import {
  buildFinancialReportHtml,
  createReportPdfArtifact,
} from './report-pdf';
import {
  fetchReportSourceData,
  saveReportRecord,
  uploadReportPdf,
} from './reports';
import { fetchTransactionCategories } from './transactions';
import type {
  Category,
  FinancialReport,
  ReportSelection,
  ReportSourceData,
} from './types';
import type { ReportPdfArtifact } from './report-pdf';

type GeneratedPdf = {
  uri: string;
  size: number | null;
  mimeType: 'text/csv' | 'application/pdf';
};

export type CoachReportDependencies = {
  fetchCategories: (userId: string) => Promise<Category[]>;
  fetchSource: (userId: string, selection: ReportSelection) => Promise<ReportSourceData>;
  compile: (source: ReportSourceData, selection: ReportSelection) => FinancialReport;
  createArtifact: (
    userId: string,
    selection: ReportSelection,
    categoryName: string | null,
  ) => ReportPdfArtifact;
  buildHtml: (
    report: FinancialReport,
    source: ReportSourceData,
    artifact: ReportPdfArtifact,
  ) => string;
  writePdf: (html: string) => Promise<GeneratedPdf>;
  readBytes: (uri: string) => Promise<ArrayBuffer>;
  uploadPdf: (path: string, bytes: ArrayBuffer) => Promise<unknown>;
  saveRecord: (
    userId: string,
    selection: ReportSelection,
    artifact: ReportPdfArtifact,
  ) => Promise<{ id: number }>;
  removeCached: (uri: string) => void;
};

const defaultDependencies: CoachReportDependencies = {
  fetchCategories: fetchTransactionCategories,
  fetchSource: fetchReportSourceData,
  compile: compileFinancialReport,
  createArtifact: createReportPdfArtifact,
  buildHtml: buildFinancialReportHtml,
  writePdf: writePdfExport,
  readBytes: readExportFileBytes,
  uploadPdf: uploadReportPdf,
  saveRecord: saveReportRecord,
  removeCached: removeCachedExport,
};

export async function generateCoachReport(
  userId: string,
  actionArguments: Record<string, unknown>,
  dependencies: CoachReportDependencies = defaultDependencies,
) {
  const requestedCategory = typeof actionArguments.category_name === 'string'
    ? actionArguments.category_name.trim()
    : '';
  const categories = requestedCategory
    ? await dependencies.fetchCategories(userId)
    : [];
  const category = requestedCategory
    ? categories.find((item) => item.name.toLocaleLowerCase() === requestedCategory.toLocaleLowerCase())
    : null;
  if (requestedCategory && !category) {
    throw new Error(`The category “${requestedCategory}” is no longer available.`);
  }
  const selection = reportSelectionFromCoachAction(
    actionArguments,
    category?.id ?? null,
  );
  const source = await dependencies.fetchSource(userId, selection);
  const report = dependencies.compile(source, selection);
  const artifact = dependencies.createArtifact(
    userId,
    selection,
    category?.name ?? null,
  );
  const html = dependencies.buildHtml(report, source, artifact);
  let temporaryPdf: GeneratedPdf | null = null;
  try {
    temporaryPdf = await dependencies.writePdf(html);
    const bytes = await dependencies.readBytes(temporaryPdf.uri);
    await dependencies.uploadPdf(artifact.storagePath, bytes);
    const record = await dependencies.saveRecord(userId, selection, artifact);
    // The local PDF is removed below, so the storage path is the only way the UI
    // can reach the uploaded file afterwards.
    return {
      reportId: record.id,
      title: artifact.title,
      storagePath: artifact.storagePath,
    };
  } finally {
    if (temporaryPdf) dependencies.removeCached(temporaryPdf.uri);
  }
}
