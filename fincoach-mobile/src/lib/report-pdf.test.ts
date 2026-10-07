import { describe, expect, test } from 'vitest';

import {
  buildFinancialReportHtml,
  createReportPdfArtifact,
} from './report-pdf';
import { compileFinancialReport } from './report-domain';
import type {
  ReportSelection,
  ReportSourceData,
  TransactionWithCategory,
} from './types';

const selection: ReportSelection = {
  preset: 'current_month',
  startDate: '2026-07-01',
  endDate: '2026-07-31',
  categoryId: null,
  reportType: 'monthly',
};

function transaction(
  id: string,
  date: string,
  amount: number,
  description: string,
): TransactionWithCategory {
  return {
    id,
    user_id: 'user-1',
    category_id: 1,
    amount,
    transaction_date: date,
    description,
    source: 'manual',
    receipt_image_path: null,
    created_at: `${date}T08:00:00Z`,
    updated_at: `${date}T08:00:00Z`,
    category: {
      id: 1,
      user_id: null,
      name: 'Food',
      type: 'expense',
      icon: null,
      color: '#4648D4',
    },
  };
}

const source: ReportSourceData = {
  transactions: [
    transaction('expense-1', '2026-07-18', 100, 'test'),
    transaction('expense-2', '2026-07-14', 49.7, 'IPOH KOPI KIA'),
  ],
  monthlyBudgets: [
    {
      id: 'budget-1',
      user_id: 'user-1',
      month: '2026-07-01',
      limit_amount: 600,
      created_at: '',
      updated_at: '',
    },
  ],
  categoryLimits: [],
  savingsGoals: [
    {
      id: 'goal-1',
      user_id: 'user-1',
      name: 'Car',
      target_amount: 460000,
      current_amount: 0,
      deadline: null,
      created_at: '',
      updated_at: '',
    },
  ],
};

describe('financial report PDF document', () => {
  test('creates a clear stable monthly title, filename, key, and owner storage path', () => {
    const artifact = createReportPdfArtifact(
      'user-1',
      selection,
      null,
      new Date('2026-07-18T10:00:00Z'),
    );

    expect(artifact).toEqual({
      title: 'July 2026 Financial Summary',
      fileName: 'FinCoach_July_2026_Financial_Summary.pdf',
      reportKey: 'monthly:2026-07-01:2026-07-31:all',
      storagePath:
        'user-1/monthly-2026-07-01-2026-07-31-all.pdf',
      generatedAt: '2026-07-18T10:00:00.000Z',
    });
  });

  test('uses a category-specific title when the user filters the report', () => {
    const artifact = createReportPdfArtifact(
      'user-1',
      {
        ...selection,
        categoryId: 1,
        reportType: 'monthly_category',
      },
      'Food',
      new Date('2026-07-18T10:00:00Z'),
    );

    expect(artifact.title).toBe('July 2026 Food Spending Report');
    expect(artifact.fileName).toBe(
      'FinCoach_July_2026_Food_Spending_Report.pdf',
    );
    expect(artifact.reportKey.endsWith(':1')).toBe(true);
  });

  test('labels multi-month documents without calling them monthly reports', () => {
    const multiMonthSelection: ReportSelection = {
      preset: 'last_3_months',
      startDate: '2026-05-01',
      endDate: '2026-07-31',
      categoryId: null,
      reportType: 'multi_month',
    };
    const artifact = createReportPdfArtifact(
      'user-1',
      multiMonthSelection,
      null,
      new Date('2026-07-19T10:00:00Z'),
    );
    const report = compileFinancialReport(source, multiMonthSelection);
    const html = buildFinancialReportHtml(report, source, artifact);

    expect(artifact.title).toBe(
      'May - July 2026 Financial Summary',
    );
    expect(html).toContain('MULTI-MONTH PDF');
    expect(html).not.toContain('>MONTHLY PDF<');
  });

  test('builds the approved A4 summary from real values and escapes user text', () => {
    const unsafeSource: ReportSourceData = {
      ...source,
      transactions: [
        ...source.transactions,
        transaction(
          'expense-3',
          '2026-07-19',
          5,
          '<script>alert("x")</script>',
        ),
      ],
    };
    const report = compileFinancialReport(unsafeSource, selection);
    const artifact = createReportPdfArtifact(
      'user-1',
      selection,
      null,
      new Date('2026-07-19T09:30:00+08:00'),
    );
    const html = buildFinancialReportHtml(report, unsafeSource, artifact);

    expect(html).toContain('<title>July 2026 Financial Summary</title>');
    expect(html).toContain('@page{size:A4;margin:0}');
    expect(html).toContain('RM 154.70');
    expect(html).toContain('-RM 154.70');
    expect(html).not.toContain('RM -154.70');
    expect(html).toContain('RM 445.30');
    expect(html).toContain('3 transactions');
    expect(html).toContain('IPOH KOPI KIA');
    expect(html).toContain('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
    expect(html).not.toContain('<script>alert("x")</script>');
    expect(html).toContain('Educational financial guidance');
  });
});
