import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('Savings goal management UI', () => {
  test('implements selected option 3 without changing goal CRUD', () => {
    const source = read('src', 'app', 'savings', 'manage.tsx');

    expect(source).toContain('ProgressRing');
    expect(source).toContain('Your new goal');
    expect(source).toContain('Start with a clear target');
    expect(source).toContain('Deadline is optional');
    expect(source).toContain('createSavingsGoal');
    expect(source).toContain('updateSavingsGoal');
  });

  test('uses the selected date-field treatment', () => {
    const source = read('src', 'components', 'savings', 'date-field.tsx');

    expect(source).toContain("placeholder = 'Select date'");
    expect(source).toContain('leadingIcon');
    expect(source).not.toContain('@react-native-community/datetimepicker');
  });
});
