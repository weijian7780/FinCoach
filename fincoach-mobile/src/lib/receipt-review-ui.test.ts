import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('receipt review safeguards', () => {
  test('shows fields that require manual attention without the processor badge', () => {
    const source = read('src', 'app', 'transactions', 'review.tsx');

    expect(source).toContain('reviewWarnings');
    expect(source).toContain('Needs your attention');
    expect(source).not.toContain('processorPill');
    expect(source).not.toContain('PaddleOCR + Gemini text cleanup');

    const scanSource = read('src', 'app', 'transactions', 'scan.tsx');
    expect(scanSource).toContain('Checking receipt text');
  });
});
