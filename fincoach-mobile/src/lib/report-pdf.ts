import { formatReportMoney } from './report-domain';
import type {
  FinancialReport,
  ReportSelection,
  ReportSourceData,
  TransactionWithCategory,
} from './types';

function formatPdfMoney(value: number) {
  const formattedAbsoluteValue = formatReportMoney(Math.abs(value));
  return value < 0 ? `-${formattedAbsoluteValue}` : formattedAbsoluteValue;
}

export type ReportPdfArtifact = {
  title: string;
  fileName: string;
  reportKey: string;
  storagePath: string;
  generatedAt: string;
};

function parseDate(value: string) {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function monthYear(value: string) {
  return new Intl.DateTimeFormat('en-MY', {
    month: 'long',
    year: 'numeric',
  }).format(parseDate(value));
}

function reportPeriodTitle(selection: ReportSelection) {
  if (
    selection.reportType === 'monthly'
    || selection.reportType === 'monthly_category'
  ) {
    return monthYear(selection.startDate);
  }

  const start = parseDate(selection.startDate);
  const end = parseDate(selection.endDate);
  const sameYear = start.getFullYear() === end.getFullYear();
  const fullMonthRange = selection.reportType.startsWith('multi_month');
  if (fullMonthRange && sameYear) {
    const startMonth = new Intl.DateTimeFormat('en-MY', {
      month: 'long',
    }).format(start);
    return `${startMonth} - ${monthYear(selection.endDate)}`;
  }
  if (fullMonthRange) {
    return `${monthYear(selection.startDate)} - ${monthYear(selection.endDate)}`;
  }

  const dateFormatter = new Intl.DateTimeFormat('en-MY', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  return `${dateFormatter.format(start)} - ${dateFormatter.format(end)}`;
}

function fileSafe(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[^\w]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function pathSafe(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function createReportPdfArtifact(
  userId: string,
  selection: ReportSelection,
  categoryName: string | null,
  generatedAt = new Date(),
): ReportPdfArtifact {
  const period = reportPeriodTitle(selection);
  const title = selection.categoryId == null
    ? `${period} Financial Summary`
    : `${period} ${categoryName?.trim() || 'Category'} Spending Report`;
  const categoryKey = selection.categoryId == null
    ? 'all'
    : String(selection.categoryId);
  const reportKey = [
    selection.reportType,
    selection.startDate,
    selection.endDate,
    categoryKey,
  ].join(':');
  const storageName = pathSafe([
    selection.reportType,
    selection.startDate,
    selection.endDate,
    categoryKey,
  ].join('-'));

  return {
    title,
    fileName: `FinCoach_${fileSafe(title)}.pdf`,
    reportKey,
    storagePath: `${pathSafe(userId)}/${storageName}.pdf`,
    generatedAt: generatedAt.toISOString(),
  };
}

function escapeHtml(value: unknown) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (character) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[character]!,
  );
}

function safeColor(value: string | null) {
  return value && /^#[0-9a-f]{6}$/i.test(value) ? value : '#4648D4';
}

function formatGeneratedAt(value: string) {
  const date = new Date(value);
  return new Intl.DateTimeFormat('en-MY', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(date);
}

function documentTypeLabel(selection: ReportSelection) {
  if (selection.reportType.startsWith('multi_month')) return 'MULTI-MONTH PDF';
  if (selection.reportType.startsWith('custom')) return 'CUSTOM PDF';
  return 'MONTHLY PDF';
}

function selectedExpenses(
  source: ReportSourceData,
  selection: ReportSelection,
) {
  return source.transactions
    .filter(
      (transaction) =>
        transaction.category.type === 'expense'
        && transaction.transaction_date >= selection.startDate
        && transaction.transaction_date <= selection.endDate
        && (
          selection.categoryId == null
          || transaction.category_id === selection.categoryId
        ),
    )
    .sort(
      (left, right) =>
        right.transaction_date.localeCompare(left.transaction_date)
        || right.created_at.localeCompare(left.created_at),
    );
}

function expenseRows(expenses: TransactionWithCategory[]) {
  if (!expenses.length) {
    return '<div class="empty">No expense transactions were recorded for this period.</div>';
  }
  return expenses
    .slice(0, 5)
    .map(
      (item) => `<div class="transaction">
        <span class="transaction-date">${escapeHtml(
          new Intl.DateTimeFormat('en-MY', {
            day: 'numeric',
            month: 'short',
          }).format(parseDate(item.transaction_date)),
        )}</span>
        <span class="transaction-name">${escapeHtml(
          item.description?.trim() || item.category.name,
        )}</span>
        <span class="category-pill">${escapeHtml(item.category.name)}</span>
        <strong class="expense-amount">-${escapeHtml(
          formatReportMoney(item.amount),
        )}</strong>
      </div>`,
    )
    .join('');
}

function categoryRows(report: FinancialReport) {
  if (!report.categoryTotals.length) {
    return '<div class="empty">No expense categories to show.</div>';
  }
  return report.categoryTotals
    .slice(0, 4)
    .map(
      (item) => `<div class="category-row">
        <div class="category-heading">
          <span><i style="background:${safeColor(item.color)}"></i>${escapeHtml(
            item.name,
          )}</span>
          <strong>${escapeHtml(formatReportMoney(item.amount))}</strong>
        </div>
        <div class="track"><span style="width:${Math.min(
          100,
          Math.max(0, item.percentage),
        )}%;background:${safeColor(item.color)}"></span></div>
        <small>${escapeHtml(item.percentage)}% - ${escapeHtml(
          item.transactionCount,
        )} transaction${item.transactionCount === 1 ? '' : 's'}</small>
      </div>`,
    )
    .join('');
}

function insightRows(report: FinancialReport) {
  const insights: { headline: string; detail: string }[] = [];
  if (report.budget.limit <= 0) {
    insights.push({
      headline: 'No monthly budget was found.',
      detail: 'Add a budget to measure monthly performance.',
    });
  } else if (report.budget.exceeded > 0) {
    insights.push({
      headline: 'The monthly budget has been exceeded.',
      detail: `${formatReportMoney(report.budget.exceeded)} is over the saved limit.`,
    });
  } else {
    insights.push({
      headline: 'Budget is currently on track.',
      detail: `${formatReportMoney(report.budget.remaining)} remains for this period.`,
    });
  }

  const topCategory = report.categoryTotals[0];
  if (topCategory) {
    insights.push({
      headline: `${topCategory.name} is the largest spending category.`,
      detail: `${topCategory.percentage}% of recorded expenses came from this category.`,
    });
  } else {
    insights.push({
      headline: 'No expenses were recorded.',
      detail: 'Add transactions to receive a spending breakdown.',
    });
  }

  if (report.savings.target > 0) {
    insights.push({
      headline: `Savings progress is ${report.savings.percentage}%.`,
      detail: `${formatReportMoney(report.savings.remaining)} remains across active goals.`,
    });
  } else {
    insights.push({
      headline: 'No savings target was found.',
      detail: 'Create a goal to track savings progress.',
    });
  }

  return insights
    .map(
      (item) => `<div class="insight">
        <i></i><strong>${escapeHtml(item.headline)}</strong>
        <span>${escapeHtml(item.detail)}</span>
      </div>`,
    )
    .join('');
}

export function buildFinancialReportHtml(
  report: FinancialReport,
  source: ReportSourceData,
  artifact: ReportPdfArtifact,
) {
  const expenses = selectedExpenses(source, report.selection);
  const budgetPercentage = Math.min(
    100,
    Math.max(0, report.budget.progressPercentage),
  );
  const hasBudget = report.budget.limit > 0;
  const budgetStatus = !hasBudget ? 'No budget saved for this period' : report.budget.exceeded > 0
    ? `${formatReportMoney(report.budget.exceeded)} over budget`
    : `${formatReportMoney(report.budget.remaining)} remaining`;
  const budgetLabel = report.budget.limit > 0
    ? `${Math.round(report.budget.percentage)}% used`
    : 'No budget';
  const selectedPeriod = `${report.selection.startDate} to ${report.selection.endDate}`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(artifact.title)}</title>
<style>
@page{size:A4;margin:0}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#fcf8ff;color:#1b1b23;font-family:Arial,sans-serif}
body{width:210mm;min-height:297mm;font-size:10px}
.header{height:43mm;padding:12mm 13mm 8mm;background:#4648d4;color:#fff;position:relative;overflow:hidden}
.header:after{content:"";position:absolute;width:54mm;height:54mm;border-radius:50%;right:-12mm;top:-25mm;background:#6c6ff0;box-shadow:0 0 0 11mm #5a5de3}
.brand{display:flex;align-items:center;gap:4mm;position:relative;z-index:1}
.brand-mark{width:14mm;height:14mm;border-radius:4mm;background:#fff;color:#4648d4;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:17px}
.brand-name{font-size:15px;font-weight:800}.brand-subtitle{font-size:8px;opacity:.82;margin-top:1mm;letter-spacing:.5px}
.header h1{font-size:23px;line-height:1.1;margin:4mm 0 0;position:relative;z-index:1}
.header-meta{position:absolute;right:13mm;bottom:8mm;text-align:right;z-index:1;font-size:9px;line-height:1.6}
.content{padding:5mm 13mm 8mm}
.document-meta{display:flex;align-items:center;gap:4mm;margin-bottom:4mm;color:#666575}
.pill{padding:2mm 4mm;border-radius:99px;background:#e7e6ff;color:#4648d4;font-weight:700}
.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:3mm;margin-bottom:4mm}
.metric,.panel{background:#fff;border-radius:4mm;page-break-inside:avoid}
.metric{padding:4mm;min-height:24mm}.metric-label{font-size:8px;color:#666575;font-weight:700;text-transform:uppercase}
.metric-value{font-size:17px;font-weight:800;margin-top:3mm;white-space:nowrap}.income{color:#148552}.expense{color:#ba1a1a}.primary{color:#4648d4}
.two-column{display:grid;grid-template-columns:1.55fr 1fr;gap:4mm;margin-bottom:4mm}
.panel{padding:5mm}.panel h2{font-size:14px;margin:0 0 4mm;padding-left:3mm;border-left:2mm solid #4648d4}
.budget-line{display:flex;align-items:baseline;justify-content:space-between;gap:3mm}.budget-amount{font-size:21px;font-weight:800}
.status{padding:2mm 4mm;border-radius:99px;background:#fff2df;color:#9b5205;font-weight:700;text-transform:uppercase}
.track{height:2.4mm;border-radius:99px;background:#e6e3ef;overflow:hidden;margin:3mm 0}.track span{display:block;height:100%;border-radius:99px;background:#4648d4}
.between{display:flex;justify-content:space-between;color:#666575}.good{color:#148552;font-weight:700}.bad{color:#ba1a1a;font-weight:700}
.category-row{margin-bottom:3mm}.category-heading{display:flex;justify-content:space-between;align-items:center}
.category-heading span{display:flex;align-items:center;gap:2mm}.category-heading i{width:2.5mm;height:2.5mm;border-radius:50%}
.category-row small{color:#666575}.category-row .track{margin:1.5mm 0}
.transaction{display:grid;grid-template-columns:15mm 1fr 22mm 30mm;gap:3mm;align-items:center;padding:2.7mm 0;border-bottom:1px solid #e1deea}
.transaction:last-child{border-bottom:0}.transaction-date{color:#666575}.transaction-name{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.category-pill{padding:1.5mm 2.5mm;border-radius:99px;background:#fdecec;color:#ba1a1a;text-align:center;text-transform:uppercase;font-size:8px}
.expense-amount{text-align:right;color:#ba1a1a}.empty{color:#666575;padding:4mm 0}
.savings-amount{font-size:20px;font-weight:800}.savings-line{display:flex;justify-content:space-between;align-items:baseline}
.insights{background:#f2f0ff}.insight{display:grid;grid-template-columns:3mm auto 1fr;gap:2mm;align-items:baseline;margin:2.5mm 0}
.insight i{width:2.3mm;height:2.3mm;background:#4648d4;border-radius:50%}.insight span{color:#666575}
.footer{display:flex;justify-content:space-between;border-top:1px solid #d9d6e5;margin-top:4mm;padding-top:3mm;color:#666575;font-size:8px}
.footer strong{color:#4648d4}.private{margin-top:1mm;text-align:right;color:#666575;font-size:8px}
</style>
</head>
<body>
  <header class="header">
    <div class="brand"><div class="brand-mark">Fi</div><div><div class="brand-name">FinCoach</div><div class="brand-subtitle">FINANCIAL REPORT</div></div></div>
    <h1>${escapeHtml(artifact.title)}</h1>
    <div class="header-meta"><strong>${escapeHtml(selectedPeriod)}</strong><br>Generated ${escapeHtml(formatGeneratedAt(artifact.generatedAt))}</div>
  </header>
  <main class="content">
    <div class="document-meta"><span class="pill">${documentTypeLabel(report.selection)}</span><span>Calculated from your recorded FinCoach data</span></div>
    <section class="metric-grid">
      <div class="metric"><div class="metric-label">Income</div><div class="metric-value income">${escapeHtml(formatReportMoney(report.totalIncome))}</div></div>
      <div class="metric"><div class="metric-label">Expenses</div><div class="metric-value expense">${escapeHtml(formatReportMoney(report.totalExpenses))}</div></div>
      <div class="metric"><div class="metric-label">Net balance</div><div class="metric-value ${report.netBalance < 0 ? 'expense' : 'primary'}">${escapeHtml(formatPdfMoney(report.netBalance))}</div></div>
      <div class="metric"><div class="metric-label">Transactions</div><div class="metric-value primary">${escapeHtml(report.transactionCount)}</div></div>
    </section>
    <section class="two-column">
      <div class="panel">
        <h2>Monthly budget</h2>
        <div class="budget-line"><span><strong class="budget-amount">${escapeHtml(formatReportMoney(report.budget.spent))}</strong> ${hasBudget ? `of ${escapeHtml(formatReportMoney(report.budget.limit))}` : 'spent'}</span><span class="status">${escapeHtml(budgetLabel)}</span></div>
        <div class="track"><span style="width:${budgetPercentage}%"></span></div>
        <div class="between"><span>${escapeHtml(budgetStatus)}</span><span class="${!hasBudget ? '' : report.budget.exceeded > 0 ? 'bad' : 'good'}">${!hasBudget ? 'No budget' : report.budget.exceeded > 0 ? 'Over budget' : 'Within budget'}</span></div>
      </div>
      <div class="panel"><h2>Spending by category</h2>${categoryRows(report)}</div>
    </section>
    <section class="two-column">
      <div class="panel">
        <h2>Expense details</h2>
        ${expenseRows(expenses)}
        <div class="between" style="margin-top:2mm"><span>Showing ${Math.min(5, expenses.length)} of ${expenses.length} expense transactions</span><strong>${escapeHtml(report.transactionCount)} transactions</strong></div>
      </div>
      <div class="panel">
        <h2>Savings progress</h2>
        <div class="savings-line"><span><strong class="savings-amount">${escapeHtml(formatReportMoney(report.savings.current))}</strong> saved</span><strong class="primary">${escapeHtml(report.savings.percentage)}%</strong></div>
        <div class="track"><span style="width:${Math.min(100, Math.max(0, report.savings.progressPercentage))}%;background:#148552"></span></div>
        <div class="between"><span>Target</span><strong>${escapeHtml(formatReportMoney(report.savings.target))}</strong></div>
        <div class="between" style="margin-top:3mm"><span>Remaining</span><strong>${escapeHtml(formatReportMoney(report.savings.remaining))}</strong></div>
      </div>
    </section>
    <section class="panel insights"><h2>FinCoach insights</h2>${insightRows(report)}</section>
    <footer class="footer"><span><strong>FinCoach</strong> - Educational financial guidance, not licensed financial advice.</span><span>Page 1 of 1</span></footer>
    <div class="private">Private - generated for the authenticated user</div>
  </main>
</body>
</html>`;
}
