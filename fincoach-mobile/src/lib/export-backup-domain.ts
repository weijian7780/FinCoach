import type {
  BackupRecord,
  BackupSourceData,
  BackupType,
  ExportContentType,
  ExportSelection,
  ExportSourceData,
  FinancialBackupDocumentV1,
} from './types';

type ExportPreset = 'current_month' | 'previous_month';

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function localDate(value: Date) {
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

function parseDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return localDate(date) === value ? date : null;
}

function lastDay(year: number, month: number) {
  return new Date(year, month + 1, 0);
}

export function createExportPreset(preset: ExportPreset, now = new Date()) {
  const offset = preset === 'previous_month' ? -1 : 0;
  const first = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  return {
    startDate: localDate(first),
    endDate: localDate(lastDay(first.getFullYear(), first.getMonth())),
  };
}

export function validateExportSelection(selection: ExportSelection) {
  const start = parseDate(selection.startDate);
  const end = parseDate(selection.endDate);
  if (!start || !end) return 'Enter valid start and end dates.';
  if (start.getTime() > end.getTime()) return 'Start date must be on or before end date.';
  if (!selection.contents.length) return 'Select at least one data section.';
  return null;
}

export function escapeCsv(value: unknown) {
  const text = String(value ?? '');
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function money(value: number) {
  return Number(value).toFixed(2);
}

function heading(name: string, columns: string[]) {
  return `${name}\r\n${columns.join(',')}\r\n`;
}

function inRange(value: string, selection: ExportSelection) {
  return value >= selection.startDate && value <= selection.endDate;
}

function csvTransactions(source: ExportSourceData, selection: ExportSelection) {
  let output = heading('Transactions', [
    'Date',
    'Description',
    'Category',
    'Type',
    'Amount (RM)',
    'Source',
  ]);
  for (const transaction of source.transactions.filter((item) =>
    inRange(item.transaction_date, selection),
  )) {
    output +=
      [
        transaction.transaction_date,
        escapeCsv(transaction.description),
        escapeCsv(transaction.category.name),
        transaction.category.type,
        money(transaction.amount),
        transaction.source,
      ].join(',') + '\r\n';
  }
  return output;
}

function csvBudgets(source: ExportSourceData) {
  let output = heading('Budgets', ['Month', 'Scope', 'Category ID', 'Limit (RM)']);
  for (const budget of source.monthlyBudgets) {
    output += [budget.month, 'Overall', '', money(budget.limit_amount)].join(',') + '\r\n';
  }
  for (const limit of source.categoryLimits) {
    output += [limit.month, 'Category', limit.category_id, money(limit.amount)].join(',') + '\r\n';
  }
  return output;
}

function csvSavings(source: ExportSourceData) {
  let output = heading('Savings Goals', [
    'Goal',
    'Current Amount (RM)',
    'Target Amount (RM)',
    'Deadline',
  ]);
  for (const goal of source.savingsGoals) {
    output +=
      [
        escapeCsv(goal.name),
        money(goal.current_amount),
        money(goal.target_amount),
        goal.deadline ?? '',
      ].join(',') + '\r\n';
  }
  return output;
}

function csvReports(source: ExportSourceData, selection: ExportSelection) {
  let output = heading('Generated Reports', ['Period', 'Type', 'Generated At']);
  for (const report of source.reports.filter((item) =>
    inRange(item.generated_at.slice(0, 10), selection),
  )) {
    output += [escapeCsv(report.period), report.type, report.generated_at].join(',') + '\r\n';
  }
  return output;
}

export function buildExportCsv(source: ExportSourceData, selection: ExportSelection) {
  const sections: Record<ExportContentType, () => string> = {
    transaction: () => csvTransactions(source, selection),
    budget: () => csvBudgets(source),
    savings: () => csvSavings(source),
    report: () => csvReports(source, selection),
  };
  return `\uFEFF${selection.contents.map((content) => sections[content]()).join('\r\n')}`;
}

function escapeHtml(value: unknown) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!,
  );
}

function table(headers: string[], rows: unknown[][]) {
  return `<table><thead><tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join('')}</tr></thead><tbody>${rows
    .map(
      (row) =>
        `<tr>${row.map((item) => `<td>${escapeHtml(item)}</td>`).join('')}</tr>`,
    )
    .join('')}</tbody></table>`;
}

export function buildExportHtml(source: ExportSourceData, selection: ExportSelection) {
  const sections: string[] = [];
  if (selection.contents.includes('transaction')) {
    sections.push(
      `<h2>Transactions</h2>${table(
        ['Date', 'Description', 'Category', 'Type', 'Amount (RM)'],
        source.transactions
          .filter((item) => inRange(item.transaction_date, selection))
          .map((item) => [
            item.transaction_date,
            item.description,
            item.category.name,
            item.category.type,
            money(item.amount),
          ]),
      )}`,
    );
  }
  if (selection.contents.includes('budget')) {
    sections.push(
      `<h2>Budgets</h2>${table(
        ['Month', 'Scope', 'Limit (RM)'],
        [
          ...source.monthlyBudgets.map((item) => [item.month, 'Overall', money(item.limit_amount)]),
          ...source.categoryLimits.map((item) => [
            item.month,
            `Category ${item.category_id}`,
            money(item.amount),
          ]),
        ],
      )}`,
    );
  }
  if (selection.contents.includes('savings')) {
    sections.push(
      `<h2>Savings Goals</h2>${table(
        ['Goal', 'Current (RM)', 'Target (RM)', 'Deadline'],
        source.savingsGoals.map((item) => [
          item.name,
          money(item.current_amount),
          money(item.target_amount),
          item.deadline ?? '',
        ]),
      )}`,
    );
  }
  if (selection.contents.includes('report')) {
    sections.push(
      `<h2>Generated Reports</h2>${table(
        ['Period', 'Type', 'Generated At'],
        source.reports
          .filter((item) => inRange(item.generated_at.slice(0, 10), selection))
          .map((item) => [item.period, item.type, item.generated_at]),
      )}`,
    );
  }

  return `<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:Arial,sans-serif;color:#1b1b23;padding:32px}h1{color:#4648d4}h2{margin-top:26px}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}
.meta{color:#666}.footer{margin-top:30px;font-size:10px;color:#777}
</style></head><body><h1>FinCoach Financial Export</h1><p class="meta">${escapeHtml(
    selection.startDate,
  )} to ${escapeHtml(selection.endDate)}</p>${sections.join(
    '',
  )}<p class="footer">User-generated personal financial data export.</p></body></html>`;
}

export function createExportFileName(selection: ExportSelection) {
  return `FinCoach_${selection.startDate}_to_${selection.endDate}.${selection.format}`;
}

function sortBy<T>(values: T[], key: (value: T) => string | number) {
  return [...values].sort((left, right) => String(key(left)).localeCompare(String(key(right))));
}

function canonicalBackupSource(source: BackupSourceData): BackupSourceData {
  return {
    profile: source.profile,
    customCategories: sortBy(source.customCategories, (item) => item.id),
    transactions: sortBy(source.transactions, (item) => item.id),
    monthlyBudgets: sortBy(source.monthlyBudgets, (item) => item.id),
    categoryLimits: sortBy(source.categoryLimits, (item) => item.id),
    savingsGoals: sortBy(source.savingsGoals, (item) => item.id),
    savingsContributions: sortBy(source.savingsContributions, (item) => item.id),
    reports: sortBy(source.reports, (item) => item.id),
    notificationPreferences: source.notificationPreferences,
    reminders: sortBy(source.reminders, (item) => item.id),
    alerts: sortBy(source.alerts, (item) => item.id),
  };
}

export function serializeBackupDocument(
  userId: string,
  appVersion: string,
  source: BackupSourceData,
  createdAt = new Date().toISOString(),
) {
  const document: FinancialBackupDocumentV1 = {
    schemaVersion: 1,
    createdAt,
    userId,
    appVersion,
    data: canonicalBackupSource(source),
  };
  return JSON.stringify(document);
}

export function validateBackupDocument(
  value: unknown,
  expectedUserId: string,
): FinancialBackupDocumentV1 {
  if (!value || typeof value !== 'object') throw new Error('Invalid backup file.');
  const document = value as Partial<FinancialBackupDocumentV1> & { schemaVersion?: number };
  if (document.schemaVersion !== 1) throw new Error('This backup version is not supported.');
  if (document.userId !== expectedUserId) throw new Error('This backup belongs to another account.');
  if (
    typeof document.createdAt !== 'string' ||
    typeof document.appVersion !== 'string' ||
    !document.data ||
    !Array.isArray(document.data.customCategories) ||
    !Array.isArray(document.data.transactions) ||
    !Array.isArray(document.data.monthlyBudgets) ||
    !Array.isArray(document.data.categoryLimits) ||
    !Array.isArray(document.data.savingsGoals) ||
    !Array.isArray(document.data.savingsContributions) ||
    !Array.isArray(document.data.reports) ||
    !Array.isArray(document.data.reminders) ||
    !Array.isArray(document.data.alerts)
  ) {
    throw new Error('Invalid backup file.');
  }
  return document as FinancialBackupDocumentV1;
}

export function createBackupObjectPath(
  userId: string,
  type: BackupType,
  backupId: string,
  createdAt = new Date(),
) {
  return `${userId}/${type}/${createdAt.toISOString().replace(/[:.]/g, '-')}-${backupId}.json`;
}

export function selectAutomaticBackupsForDeletion(records: BackupRecord[], keep = 5) {
  return records
    .filter((record) => record.backup_type === 'automatic' && record.status === 'completed')
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(Math.max(0, keep))
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
}
