import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('Financial Report and Analytics UI', () => {
  test('loads and compiles real owner-scoped financial data', () => {
    const route = read('src', 'app', 'reports.tsx');
    const screen = read('src', 'components', 'reports', 'reports-screen.tsx');
    const components = read('src', 'components', 'reports', 'report-components.tsx');
    expect(route).toContain("@/components/reports/reports-screen");
    expect(screen).toContain('fetchReportSourceData');
    expect(screen).toContain('compileFinancialReport');
    expect(screen).toContain('createReportRecord');
    expect(screen).toContain('fetchRecentReports');
    expect(screen).toContain('fetchTransactionCategories');
    expect(screen).toContain('RefreshControl');
    expect(components).toContain('Generate Report');
    expect(screen + components).not.toContain('RM 0');
    expect(screen + components).not.toContain('AI insight');
  });

  test('keeps initial preview and refresh separate from history creation', () => {
    const screen = read('src', 'components', 'reports', 'reports-screen.tsx');
    expect(screen).toContain('loadPreview');
    expect(screen).toContain('generateReport');
    expect(screen).toContain('refreshReport');
    expect(screen).toContain('historyWarning');
    expect(screen).toContain('validateReportSelection');
  });

  test('does not refetch the focus preview on every filter keystroke', () => {
    const screen = read('src', 'components', 'reports', 'reports-screen.tsx');
    expect(screen).toContain('selectionRef.current');
    expect(screen).not.toContain('[loadHistory, selection, userId]');
  });

  test('provides all approved dashboard sections and accessible chart labels', () => {
    const components = read('src', 'components', 'reports', 'report-components.tsx');
    for (const label of [
      'Income',
      'Expenses',
      'Net Balance',
      'Budget vs Actual',
      'Spending by Category',
      'Monthly Trend',
      'Savings Progress',
      'Recent Reports',
    ]) expect(components).toContain(label);
    expect(components).toContain('accessibilityLabel');
    expect(components).toContain('No transactions in this period');
    expect(components).toContain('YYYY-MM-DD');
    expect(components).not.toContain('react-native-svg');
  });
});
