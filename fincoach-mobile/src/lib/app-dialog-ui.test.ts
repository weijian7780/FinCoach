import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    if (!/\.tsx?$/.test(name) || /\.(test|spec)\.tsx?$/.test(name)) return [];
    return [path];
  });
}

describe('FinCoach app dialog UI', () => {
  test('mounts the global provider and exposes stable dialog methods', () => {
    const layout = read('src', 'app', '_layout.tsx');
    const provider = read('src', 'components', 'ui', 'app-dialog.tsx');

    expect(layout).toContain('AppDialogProvider');
    expect(provider).toContain('useAppDialog');
    expect(provider).toContain('alert: showAlert');
    expect(provider).toContain('confirm: showConfirm');
  });

  test('uses branded typography, tone variants and accessible modal semantics', () => {
    const provider = read('src', 'components', 'ui', 'app-dialog.tsx');

    expect(provider).toContain('authFont.bold');
    expect(provider).toContain("destructive:");
    expect(provider).toContain("warning:");
    expect(provider).toContain("success:");
    expect(provider).toContain('accessibilityViewIsModal');
    expect(provider).toContain('onRequestClose');
    expect(provider).toContain('maxWidth: 380');
  });

  test('removes native application alerts from non-test source files', () => {
    const offenders = sourceFiles(join(root, 'src'))
      .filter((path) => readFileSync(path, 'utf8').includes('Alert.alert('));

    expect(offenders).toEqual([]);
  });
});
