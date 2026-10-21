import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

import { base64ByteLength, categoryIconExtension } from '@/lib/category-icon-domain';

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

describe('custom category image helpers', () => {
  test('calculates decoded image size from padded base64', () => {
    expect(base64ByteLength('YQ==')).toBe(1);
    expect(base64ByteLength('YWI=')).toBe(2);
    expect(base64ByteLength('YWJj')).toBe(3);
  });

  test('accepts supported picked-image formats and safely defaults to JPEG', () => {
    expect(categoryIconExtension('file:///image.jpeg', 'image/png')).toBe('png');
    expect(categoryIconExtension('file:///image.webp')).toBe('webp');
    expect(categoryIconExtension('file:///image.unknown')).toBe('jpg');
  });

  test('migration creates a limited public bucket with owner-scoped writes', () => {
    const migration = readFileSync(
      join(projectRoot, 'supabase', 'migrations', '20260719084346_support_custom_category_images.sql'),
      'utf8',
    );
    expect(migration).toContain("add column if not exists icon_image_path text");
    expect(migration).toContain("'category-icons'");
    expect(migration).toContain('2097152');
    expect(migration).toContain("(storage.foldername(name))[1] = (select auth.uid()::text)");
    expect(migration).toContain('restore_financial_backup_v1');
  });
});
