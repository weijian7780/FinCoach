import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('receipt review safeguards', () => {
  test('shows text-cleanup status and fields that require manual attention', () => {
    const source = read('src', 'app', 'transactions', 'review.tsx');

    expect(source).toContain('enhancementStatus');
    expect(source).toContain('reviewWarnings');
    expect(source).toContain('Needs your attention');
    expect(source).toContain('PaddleOCR + Gemini text cleanup');
    expect(source).toContain('not_needed');
    expect(source).toContain('High-confidence PaddleOCR result');

    const scanSource = read('src', 'app', 'transactions', 'scan.tsx');
    expect(scanSource).toContain('Checking receipt text');
  });
});
