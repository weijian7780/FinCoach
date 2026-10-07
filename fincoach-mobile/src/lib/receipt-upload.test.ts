import { describe, expect, test } from 'vitest';

import { buildReceiptUploadForm } from '@/lib/receipt-upload';

describe('receipt OCR upload', () => {
  test('adds a real Blob to multipart FormData', () => {
    const file = new Blob(['receipt bytes'], { type: 'image/jpeg' });

    const form = buildReceiptUploadForm(file);
    const part = form.get('file');

    expect(part).toBeInstanceOf(Blob);
    expect((part as Blob).type).toBe('image/jpeg');
  });
});
