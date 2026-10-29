import type {
  FinancialReport,
  ReportCategoryBudget,
  ReportCategoryTotal,
  ReportPreset,
  ReportSelection,
  ReportSourceData,
  ReportType,
  ReportTrendPoint,
  TransactionWithCategory,
} from './types';

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const MAX_REPORT_CENTS = 2 ** 51 - 1;

export class ReportCalculationError extends Error {
  constructor(message: string) { super(message); this.name = 'ReportCalculationError'; }
}

// Stay below the precision boundary of the existing numeric display contract.
// Every addition uses integer cents, including grouped and summary totals.
function cents(value: number) {
  const result = Math.round(value * 100);
  if (!Number.isFinite(value) || !Number.isSafeInteger(result) || Math.abs(result) > MAX_REPORT_CENTS) {
    throw new ReportCalculationError('The report amount exceeds the supported range. Choose a smaller period.');
  }
  return result;
}

function addCents(left: number, right: number) {
  const result = left + right;
  if (!Number.isSafeInteger(result) || Math.abs(result) > MAX_REPORT_CENTS) {
    throw new ReportCalculationError('The report amount exceeds the supported range. Choose a smaller period.');
  }
  return result;
}

function sumMoney(values: number[]) {
  return values.reduce((sum, value) => addCents(sum, cents(value)), 0) / 100;
}

function subtractMoney(left: number, right: number) {
  return addCents(cents(left), -cents(right)) / 100;
}

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function localMonthKey(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-01`;
}

function endOfMonth(date: Date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function parseLocalDate(value: string) {
  const match = DATE_PATTERN.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year
    || date.getMonth() !== month - 1
    || date.getDate() !== day
  ) return null;
  return date;
}

function round(value: number, digits = 2) {
  const multiplier = 10 ** digits;
  return Math.round((value + Number.EPSILON) * multiplier) / multiplier;
}

function ratioMetrics(used: number, limit: number) {
  const percentage = limit > 0 ? round((used / limit) * 100) : 0;
  return {
    limit: round(limit),
    spent: round(used),
    remaining: Math.max(0, subtractMoney(limit, used)),
    exceeded: Math.max(0, subtractMoney(used, limit)),
    percentage,
    progressPercentage: Math.min(100, Math.max(0, percentage)),
  };
}

function reportTypeFor(preset: ReportPreset, categoryId: number | null): ReportType {
  const suffix = categoryId == null ? '' : '_category';
  if (preset === 'current_month' || preset === 'previous_month') {
    return `monthly${suffix}` as ReportType;
  }
  if (preset === 'last_3_months') return `multi_month${suffix}` as ReportType;
  return `custom${suffix}` as ReportType;
}

export function withReportCategory(selection: ReportSelection, categoryId: number | null) {
  return {
    ...selection,
    categoryId,
    reportType: reportTypeFor(selection.preset, categoryId),
  };
}

export function createPresetSelection(
  preset: ReportPreset,
  now = new Date(),
): ReportSelection {
  const currentMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  let start = currentMonth;
  let end = endOfMonth(currentMonth);

  if (preset === 'previous_month') {
    start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    end = endOfMonth(start);
  } else if (preset === 'last_3_months') {
    start = new Date(now.getFullYear(), now.getMonth() - 2, 1);
    end = endOfMonth(currentMonth);
  } else if (preset === 'custom') {
    end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  return {
    preset,
    startDate: localDateKey(start),
    endDate: localDateKey(end),
    categoryId: null,
    reportType: reportTypeFor(preset, null),
  };
}

export function validateReportSelection(selection: ReportSelection) {
  const start = parseLocalDate(selection.startDate);
  const end = parseLocalDate(selection.endDate);
  if (!start || !end) return 'Enter valid start and end dates.';
  if (start.getTime() > end.getTime()) return 'Start date must be on or before end date.';
  const months = (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth() + 1;
  if (months > 120) return 'Choose a report period covering no more than 120 calendar months.';
  return null;
}

export function requireValidReportSelection(selection: ReportSelection) {
  const error = validateReportSelection(selection);
  if (error) throw new ReportCalculationError(error);
}

export function monthKeysForRange(startDate: string, endDate: string) {
  const start = parseLocalDate(startDate);
  const end = parseLocalDate(endDate);
  if (!start || !end || start > end) return [];
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const last = new Date(end.getFullYear(), end.getMonth(), 1);
  const keys: string[] = [];
  while (cursor <= last) {
    keys.push(localMonthKey(cursor));
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return keys;
}

export function formatReportPeriod(selection: ReportSelection) {
  if (
    selection.reportType === 'monthly'
    || selection.reportType === 'monthly_category'
  ) return selection.startDate.slice(0, 7);
  if (
    selection.reportType === 'multi_month'
    || selection.reportType === 'multi_month_category'
  ) return `${selection.startDate.slice(0, 7)}..${selection.endDate.slice(0, 7)}`;
  return `${selection.startDate}..${selection.endDate}`;
}

export function formatReportPeriodLabel(selection: ReportSelection) {
  const start = parseLocalDate(selection.startDate);
  const end = parseLocalDate(selection.endDate);
  if (!start || !end) return 'Invalid period';
  const formatter = new Intl.DateTimeFormat('en-MY', { day: 'numeric', month: 'short', year: 'numeric' });
  if (selection.startDate.slice(0, 7) === selection.endDate.slice(0, 7)
    && selection.startDate.endsWith('-01')
    && end.getDate() === endOfMonth(end).getDate()) {
    return new Intl.DateTimeFormat('en-MY', { month: 'long', year: 'numeric' }).format(start);
  }
  return `${formatter.format(start)} – ${formatter.format(end)}`;
}

export function formatReportMoney(value: number) {
  return `RM ${round(value).toLocaleString('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function isInRange(transaction: TransactionWithCategory, selection: ReportSelection) {
  return transaction.transaction_date >= selection.startDate
    && transaction.transaction_date <= selection.endDate;
}

function compileCategoryTotals(expenses: TransactionWithCategory[]): ReportCategoryTotal[] {
  const grouped = new Map<number, ReportCategoryTotal>();
  for (const transaction of expenses) {
    const current = grouped.get(transaction.category_id) ?? {
      categoryId: transaction.category_id,
      name: transaction.category.name,
      color: transaction.category.color,
      amount: 0,
      percentage: 0,
      transactionCount: 0,
    };
    current.amount = addCents(current.amount, cents(transaction.amount));
    current.transactionCount += 1;
    grouped.set(transaction.category_id, current);
  }
  const total = [...grouped.values()].reduce((sum, item) => addCents(sum, item.amount), 0);
  return [...grouped.values()]
    .map((item) => ({
      ...item,
      amount: item.amount / 100,
      percentage: total > 0 ? round((item.amount / total) * 100) : 0,
    }))
    .sort((left, right) => right.amount - left.amount || left.name.localeCompare(right.name));
}

function compileTrend(
  transactions: TransactionWithCategory[],
  selection: ReportSelection,
): ReportTrendPoint[] {
  const byMonth = new Map(monthKeysForRange(selection.startDate, selection.endDate).map((month) => [
    month,
    { month, income: 0, expenses: 0, net: 0 },
  ]));
  for (const transaction of transactions) {
    const month = `${transaction.transaction_date.slice(0, 7)}-01`;
    const point = byMonth.get(month);
    if (!point) continue;
    if (transaction.category.type === 'income') point.income = addCents(point.income, cents(transaction.amount));
    else point.expenses = addCents(point.expenses, cents(transaction.amount));
    point.net = addCents(point.income, -point.expenses);
  }
  return [...byMonth.values()].map((point) => ({ ...point, income: point.income / 100, expenses: point.expenses / 100, net: point.net / 100 }));
}

function transactionMonth(transaction: TransactionWithCategory) {
  return `${transaction.transaction_date.slice(0, 7)}-01`;
}

// A limit only covers its own month: spending from months without a saved
// limit must not be compared against it.
function compileCategoryBudgets(
  source: ReportSourceData,
  overallExpenses: TransactionWithCategory[],
): ReportCategoryBudget[] {
  const limitByCategory = new Map<number, number>();
  const limitedMonths = new Set<string>();
  for (const limit of source.categoryLimits) {
    limitByCategory.set(limit.category_id, addCents(limitByCategory.get(limit.category_id) ?? 0, cents(limit.amount)));
    limitedMonths.add(`${limit.category_id}|${limit.month.slice(0, 7)}-01`);
  }
  const spentByCategory = new Map<number, number>();
  for (const transaction of overallExpenses) {
    if (!limitedMonths.has(`${transaction.category_id}|${transactionMonth(transaction)}`)) continue;
    spentByCategory.set(
      transaction.category_id,
      addCents(spentByCategory.get(transaction.category_id) ?? 0, cents(transaction.amount)),
    );
  }
  return [...limitByCategory.entries()]
    .map(([categoryId, limit]) => ({ categoryId, ...ratioMetrics((spentByCategory.get(categoryId) ?? 0) / 100, limit / 100) }))
    .sort((left, right) => right.percentage - left.percentage);
}

export function compileFinancialReport(
  source: ReportSourceData,
  selection: ReportSelection,
): FinancialReport {
  requireValidReportSelection(selection);
  const inRange = source.transactions.filter((item) => isInRange(item, selection));
  const selected = selection.categoryId == null
    ? inRange
    : inRange.filter((item) => item.category_id === selection.categoryId);
  const income = selected.filter((item) => item.category.type === 'income');
  const expenses = selected.filter((item) => item.category.type === 'expense');
  const overallExpenses = inRange.filter((item) => item.category.type === 'expense');
  const totalIncome = sumMoney(income.map((item) => item.amount));
  const totalExpenses = sumMoney(expenses.map((item) => item.amount));
  const budgetLimit = sumMoney(source.monthlyBudgets.map((item) => item.limit_amount));
  const budgetedMonths = new Set(source.monthlyBudgets.map((item) => `${item.month.slice(0, 7)}-01`));
  const budgetSpent = sumMoney(overallExpenses
    .filter((item) => budgetedMonths.has(transactionMonth(item)))
    .map((item) => item.amount));
  const savingsCurrent = sumMoney(source.savingsGoals.map((item) => item.current_amount));
  const savingsTarget = sumMoney(source.savingsGoals.map((item) => item.target_amount));
  const savingsPercentage = savingsTarget > 0 ? round((savingsCurrent / savingsTarget) * 100) : 0;

  return {
    selection,
    totalIncome,
    totalExpenses,
    netBalance: subtractMoney(totalIncome, totalExpenses),
    transactionCount: selected.length,
    categoryTotals: compileCategoryTotals(expenses),
    trend: compileTrend(selected, selection),
    budget: ratioMetrics(budgetSpent, budgetLimit),
    categoryBudgets: compileCategoryBudgets(source, overallExpenses),
    savings: {
      current: savingsCurrent,
      target: savingsTarget,
      remaining: Math.max(0, subtractMoney(savingsTarget, savingsCurrent)),
      percentage: savingsPercentage,
      progressPercentage: Math.min(100, Math.max(0, savingsPercentage)),
    },
  };
}
