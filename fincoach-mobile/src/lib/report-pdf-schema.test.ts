import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) =>
  readFileSync(join(root, ...parts), 'utf8');

describe('report PDF persistence schema', () => {
  test('stores one private owner-scoped PDF for each report selection', () => {
    const migration = read(
      'supabase',
      'migrations',
      '20260719010000_enable_report_pdf_history.sql',
    );

    for (const column of [
      'title',
      'file_name',
      'storage_path',
      'report_key',
      'start_date',
      'end_date',
      'category_id',
    ]) {
      expect(migration).toContain(`add column if not exists ${column}`);
    }
    expect(migration).toContain(
      'unique (user_id, report_key)',
    );
    expect(migration).toContain(
      "delete from public.reports where storage_path is null",
    );
    expect(migration).toContain("'financial-reports'");
    expect(migration).toContain("array['application/pdf']");
    expect(migration).toContain(
      "(storage.foldername(name))[1] = (select auth.uid()::text)",
    );
    expect(migration).toContain(
      'create policy "Users can update own reports"',
    );
  });
});
