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
    expect(source).not.toContain("'/budget/categories'");
    expect(source).toContain('FinCoach');
    expect(source).toContain('prototypeCard');
    expect(source).toContain("status.tone !== 'success'");
    expect(source).toContain('getUnbudgetedCategorySpending');
    expect(source).toContain('No limit set');
    expect(source).toContain('spent this month');
    expect(source).toContain('categoryId: String(category.id)');
    expect(source).toContain('Edit monthly budget');
  });

  test('manage screen supports overall and category-limit CRUD', () => {
    const source = read('src', 'app', 'budget', 'manage.tsx');
    expect(source).toContain('upsertMonthlyBudget');
    expect(source).toContain('upsertCategoryLimit');
    expect(source).toContain('deleteCategoryLimit');
    expect(source).toContain('deleteMonthlyBudget');
    expect(source).toContain('MoneyField');
    expect(source).toContain('CategoryPicker');
    expect(source).toContain('CategoryLimitRow');
    expect(source).toContain('BudgetProgress');
    expect(source).toContain('MONTHLY SPENDING LIMIT');
    expect(source).toContain('assigned');
    expect(source).toContain('available');
    expect(source).toContain('Add category limit');
    expect(source).toContain('suggestedCategoryId');
    expect(source).toContain('Manage expense categories');
    expect(source).not.toContain('Manage category settings');
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
    expect(source).toContain('Upload personal category image');
    expect(source).toContain('Category appearance');
    expect(source).toContain('appearanceMode');
    expect(source).toContain('Personal image selected');
    expect(source).toContain('Remove personal category image');
    expect(source).toContain("appearanceMode === 'image' && pendingImage");
    expect(source).not.toContain('Use Material icon instead');
    expect(source).toContain('uploadCategoryIcon');
    expect(source).toContain('icon_image_path');
  });

  test('custom categories can search the complete Material icon set', () => {
    const source = read('src', 'components', 'budget', 'icon-color-picker.tsx');
    expect(source).toContain('MaterialIcons.glyphMap');
    expect(source).toContain('Search all Material icons');
    expect(source).toContain('visibleIcons');
  });

  test('all category surfaces use the shared image-aware icon component', () => {
    const sources = [
      read('src', 'app', '(app)', 'budget.tsx'),
      read('src', 'app', 'budget', 'categories.tsx'),
      read('src', 'app', 'transactions', 'manage.tsx'),
      read('src', 'app', 'transactions', '[transactionId].tsx'),
      read('src', 'components', 'budget', 'category-limit-row.tsx'),
      read('src', 'components', 'budget', 'category-picker.tsx'),
      read('src', 'components', 'transactions', 'transaction-row.tsx'),
    ];
    sources.forEach((source) => expect(source).toContain('CategoryIcon'));
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
