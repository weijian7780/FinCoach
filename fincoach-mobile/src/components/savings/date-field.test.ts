import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

describe('Savings date field native compatibility', () => {
  test('does not require the RNCDatePicker native module', () => {
    const source = readFileSync(join(projectRoot, 'src', 'components', 'savings', 'date-field.tsx'), 'utf8');
    const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>;
    };
    const appJson = readFileSync(join(projectRoot, 'app.json'), 'utf8');

    expect(source).not.toContain('@react-native-community/datetimepicker');
    expect(packageJson.dependencies).not.toHaveProperty('@react-native-community/datetimepicker');
    expect(appJson).not.toContain('@react-native-community/datetimepicker');
  });

  test('progress ring does not require native SVG ViewManagers', () => {
    const source = readFileSync(join(projectRoot, 'src', 'components', 'savings', 'progress-ring.tsx'), 'utf8');
    const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8')) as {
      dependencies: Record<string, string>;
    };

    expect(source).not.toContain('react-native-svg');
    expect(packageJson.dependencies).not.toHaveProperty('react-native-svg');
  });
});
