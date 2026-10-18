import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const componentDir = join(projectRoot, 'src', 'components', 'budget');

const componentFiles = [
  'month-selector.tsx',
  'budget-progress.tsx',
  'status-badge.tsx',
  'money-field.tsx',
  'category-picker.tsx',
  'category-limit-row.tsx',
  'icon-color-picker.tsx',
];

describe('Budget component compatibility and accessibility', () => {
  test('does not depend on missing native SVG or date-picker ViewManagers', () => {
    const source = componentFiles
      .map((name) => readFileSync(join(componentDir, name), 'utf8'))
      .join('\n');

    expect(source).not.toContain('react-native-svg');
    expect(source).not.toContain('@react-native-community/datetimepicker');
  });

  test('exposes labels for month navigation, money input, and selection controls', () => {
    const source = componentFiles
      .map((name) => readFileSync(join(componentDir, name), 'utf8'))
      .join('\n');

    expect(source).toContain('Previous month');
    expect(source).toContain('Next month');
    expect(source).toContain('accessibilityLabel={label}');
    expect(source).toContain('accessibilityRole="checkbox"');
    expect(source).toContain('accessibilityRole="radio"');
    expect(source).toContain('accessibilityLabel={`Remove ${category.name} limit`}');
  });
});
