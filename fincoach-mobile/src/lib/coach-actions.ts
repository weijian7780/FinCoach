import { getReportAttempt } from './coach-api';
import {
  readExportFileBytes,
  removeCachedExport,
  writePdfExport,
} from './export-files';
import { compileFinancialReport, requireValidReportSelection } from './report-domain';
import { parseReportAttempt } from './report-attempt';
import {
  buildFinancialReportHtml,
  createReportPdfArtifact,
} from './report-pdf';
import {
  fetchReportSourceData,
  isDuplicateReportUploadError,
  uploadReportPdf,
} from './reports';
import { fetchTransactionCategories } from './transactions';
import type {
  Category,
  CoachReportAttempt,
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

// The server reserves the storage path and writes the history row; the device
// only renders the PDF and reports its display metadata back.
export type GeneratedCoachReport = {
  title: string;
  fileName: string;
  generatedAt: string;
  storagePath: string;
};

export type CoachReportAttemptTarget = CoachReportAttempt;

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
  fetchAttempt: (messageId: string, attemptId: string) => Promise<unknown>;
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
  fetchAttempt: getReportAttempt,
  removeCached: removeCachedExport,
};

export async function generateCoachReport(
  userId: string,
  attempt: CoachReportAttemptTarget,
  dependencies: CoachReportDependencies = defaultDependencies,
  assertLease: () => void = () => {},
): Promise<GeneratedCoachReport> {
  assertLease();
  if (attempt.storage_path !== `${userId}/coach/${attempt.attempt_id}.pdf`) {
    throw new Error('The report storage reservation is invalid.');
  }
  // All filtering comes from the claim snapshot. Never resolve a name or
  // relative date again: a retry may occur after a rename or month boundary.
  const selection: ReportSelection = {
    preset: attempt.period === 'last_month' ? 'previous_month'
      : attempt.period === 'last_3_months' ? 'last_3_months'
      : attempt.period === 'current_month' ? 'current_month' : 'custom',
    startDate: attempt.start_date, endDate: attempt.end_date,
    categoryId: attempt.category_id, reportType: attempt.report_type,
  };
  requireValidReportSelection(selection);
  const categories = attempt.category_id !== null
    ? await dependencies.fetchCategories(userId)
    : [];
  if (attempt.category_id !== null && !categories.some((item) => item.id === attempt.category_id)) {
    throw new Error('The selected report category is no longer available.');
  }
  const source = await dependencies.fetchSource(userId, selection);
  const report = dependencies.compile(source, selection);
  const artifact = dependencies.createArtifact(
    userId,
    selection,
    attempt.category_name,
  );
  // The reserved path comes from the server-issued attempt, so a retry can
  // only ever write the single immutable file that attempt owns.
  artifact.storagePath = attempt.storage_path;
  const html = dependencies.buildHtml(report, source, artifact);
  let temporaryPdf: GeneratedPdf | null = null;
  try {
    temporaryPdf = await dependencies.writePdf(html);
    const bytes = await dependencies.readBytes(temporaryPdf.uri);
    assertLease();
    try {
      await dependencies.uploadPdf(artifact.storagePath, bytes);
    } catch (error) {
      if (!isDuplicateReportUploadError(error)) throw error;
      // The per-attempt path is immutable, so a duplicate can only be this
      // attempt's own earlier upload. It is never auto-accepted: the server
      // must still report the attempt as publishable.
      const status = await dependencies
        .fetchAttempt(attempt.message_id, attempt.attempt_id)
        .catch(() => null);
      const parsed = parseReportAttempt(status);
      if (!parsed || parsed.attempt_id !== attempt.attempt_id
        || (parsed.status !== 'completed' && (parsed.status !== 'active' || parsed.lease_valid !== true))) {
        throw error;
      }
    }
    assertLease();
    // The local PDF is removed below, so the storage path is the only way the
    // UI can reach the uploaded file afterwards.
    return {
      title: artifact.title,
      fileName: artifact.fileName,
      generatedAt: artifact.generatedAt,
      storagePath: artifact.storagePath,
    };
  } finally {
    if (temporaryPdf) {
      try {
        dependencies.removeCached(temporaryPdf.uri);
      } catch {
        // Cache maintenance must not replace upload success or the original error.
        console.warn('fincoach_report_cache_cleanup_failed');
      }
    }
  }
}
