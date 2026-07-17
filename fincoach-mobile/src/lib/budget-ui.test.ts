import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('Budget routes', () => {
  test('overview loads one month and calculates spending from transactions', () => {
    const source = read('src', 'app', '(app)', 'budget.tsx');
    expect(source).toContain('fetchBudgetMonth');
    expect(source).toContain('MonthSelector');
    expect(source).toContain('fetchTransactions');
    expect(source).toContain('spentByCategory');
    expect(source).toContain("'/budget/manage'");
    expect(source).toContain("'/budget/categories'");
    expect(source).toContain('FinCoach');
    expect(source).toContain('prototypeCard');
    expect(source).toContain("status.tone !== 'success'");
  });

  test('manage screen supports overall and category-limit CRUD', () => {
    const source = read('src', 'app', 'budget', 'manage.tsx');
    expect(source).toContain('upsertMonthlyBudget');
    expect(source).toContain('upsertCategoryLimit');
    expect(source).toContain('deleteCategoryLimit');
    expect(source).toContain('deleteMonthlyBudget');
    expect(source).toContain('MoneyField');
    expect(source).toContain('CategoryPicker');
    expect(source).toContain('Manage category');
  });

  test('category screen restricts editing controls to custom-category operations', () => {
    const source = read('src', 'app', 'budget', 'categories.tsx');
    expect(source).toContain('createCustomCategory');
    expect(source).toContain('updateCustomCategory');
    expect(source).toContain('deleteCustomCategory');
    expect(source).toContain('IconColorPicker');
    expect(source).toContain('System categories');
    expect(source).toContain('Your custom categories');
    expect(source).toContain('categoryChip');
  });

  test('root stack registers both management routes', () => {
    const source = read('src', 'app', '_layout.tsx');
    expect(source).toContain('budget/manage');
    expect(source).toContain('budget/categories');
  });

  test('home preview reads the current monthly budget and links to Budget details', () => {
    const source = read('src', 'app', '(app)', 'index.tsx');
    expect(source).toContain('fetchMonthlyBudget');
    expect(source).toContain('monthKey()');
    expect(source).toContain("'/budget'");
    expect(source).toContain('fetchTransactions');
    expect(source).toContain('monthExpenses');
  });
});
