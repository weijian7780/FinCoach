import { describe, expect, test, vi } from 'vitest';
import { saveReceiptTransaction, TransactionDraftConflictError } from './transactions';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));

function fixture() {
  const items = Array.from({ length: 30 }, (_, i) => ({ description: `Item ${i}: ${'long description '.repeat(30)}`, amount: 1, modifiers: ['large', 'no ice'] }));
  const input = { id: 'stable-id', category_id: 1, amount: 30, transaction_date: '2026-10-15', description: 'Scanned receipt', source: 'Merchant', receipt_image_path: 'owner/stable-id.jpg', receipt_items: items };
  const state = { id: input.id, uploading: false, uploaded: false };
  let row: any = null;
  let imageExists = false;
  let writes = 0;
  const failure = new TypeError('Response lost');
  const builder: any = {};
  for (const method of ['select', 'eq']) builder[method] = () => builder;
  builder.insert = vi.fn((value: any) => { row = value; writes++; return builder; });
  builder.single = vi.fn(async () => { throw failure; });
  builder.maybeSingle = vi.fn(async () => ({ data: row, error: null }));
  const bucket = {
    upload: vi.fn(async () => { imageExists = true; return { data: { path: input.receipt_image_path }, error: null }; }),
    remove: vi.fn(),
    createSignedUrl: vi.fn(async () => ({ data: imageExists ? { signedUrl: 'signed-image' } : null, error: imageExists ? null : failure })),
  };
  const client: any = { from: () => builder, storage: { from: () => bucket } };
  const save = (payload = input) => saveReceiptTransaction('owner', payload, state, async () => new ArrayBuffer(2), 'image/jpeg', client);
  return { input, state, builder, bucket, save, failure, row: () => row, writes: () => writes, imageExists: () => imageExists };
}

describe('receipt retry integrity', () => {
  test('lost insert response plus retry produces one expense with all items and its image', async () => {
    const f = fixture();
    const first = await f.save();
    const second = await f.save();
    expect(first).toEqual(second);
    expect(f.writes()).toBe(1);
    expect(f.bucket.upload).toHaveBeenCalledTimes(1);
    expect(f.bucket.remove).not.toHaveBeenCalled();
    expect(f.imageExists()).toBe(true);
    expect(f.row().receipt_items).toEqual(f.input.receipt_items);
    expect(f.row().receipt_items).toHaveLength(30);
  });
  test('uncertain insert and failed recovery retain the image for a later retry', async () => {
    const f = fixture();
    f.builder.maybeSingle.mockResolvedValueOnce({ data: null, error: null }).mockRejectedValueOnce(f.failure);
    await expect(f.save()).rejects.toBe(f.failure);
    expect(f.imageExists()).toBe(true);
    expect(f.state.uploading).toBe(false);
    await expect(f.save()).resolves.toEqual(f.row());
    expect(f.writes()).toBe(1);
    expect(f.bucket.remove).not.toHaveBeenCalled();
  });
  test('lost upload response is recovered by confirming the stored object', async () => {
    const f = fixture();
    const upload = f.bucket.upload.getMockImplementation()!;
    f.bucket.upload.mockImplementationOnce(async () => { await upload(); throw f.failure; });
    await f.save();
    expect(f.bucket.createSignedUrl).toHaveBeenCalledTimes(1);
    expect(f.writes()).toBe(1);
  });
  test('overlapping saves cannot race and edited retries cannot overwrite a commit', async () => {
    const f = fixture();
    const pending = f.save();
    await expect(f.save()).rejects.toThrow('already being saved');
    await pending;
    await expect(f.save({ ...f.input, receipt_items: [] })).rejects.toBeInstanceOf(TransactionDraftConflictError);
    expect(f.writes()).toBe(1);
  });
});
