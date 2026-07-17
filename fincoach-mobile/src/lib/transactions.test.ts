import {
  createReceiptSignedUrl,
  createTransaction,
  deleteReceiptImage,
  deleteTransaction,
  fetchTransaction,
  fetchTransactions,
  updateTransaction,
  uploadReceiptImage,
} from '@/lib/transactions';
import { describe, expect, test, vi } from 'vitest';

vi.mock('@/lib/supabase', () => ({ supabase: {} }));

const transaction = {
  id: 'transaction-1',
  user_id: 'user-1',
  category_id: 2,
  amount: 12.5,
  transaction_date: '2026-07-14',
  description: 'Lunch',
  source: 'manual',
  receipt_image_path: null,
  created_at: '2026-07-14T08:00:00Z',
  updated_at: '2026-07-14T08:00:00Z',
  category: { id: 2, user_id: null, name: 'Food', type: 'expense', icon: 'restaurant', color: '#F97316' },
};

function createClient(result: { data?: unknown; error?: unknown } = {}) {
  const response = { data: result.data ?? null, error: result.error ?? null };
  const builder: Record<string, ReturnType<typeof vi.fn>> & {
    then?: (resolve: (value: typeof response) => unknown, reject?: (reason: unknown) => unknown) => Promise<unknown>;
  } = {
    select: vi.fn(), eq: vi.fn(), order: vi.fn(), or: vi.fn(), insert: vi.fn(), update: vi.fn(), delete: vi.fn(),
    single: vi.fn(), maybeSingle: vi.fn(),
  };
  for (const method of ['select', 'eq', 'order', 'or', 'insert', 'update', 'delete'] as const) {
    builder[method].mockReturnValue(builder);
  }
  builder.single.mockResolvedValue(response);
  builder.maybeSingle.mockResolvedValue(response);
  builder.then = (resolve, reject) => Promise.resolve(response).then(resolve, reject);

  const bucket = {
    upload: vi.fn().mockResolvedValue(response),
    remove: vi.fn().mockResolvedValue(response),
    createSignedUrl: vi.fn().mockResolvedValue(response),
  };
  const client = {
    from: vi.fn().mockReturnValue(builder),
    storage: { from: vi.fn().mockReturnValue(bucket) },
  };
  return { builder, bucket, client };
}

describe('transaction persistence', () => {
  test('lists owner transactions with category details newest first', async () => {
    const { builder, client } = createClient({ data: [transaction] });
    await expect(fetchTransactions('user-1', client)).resolves.toEqual([transaction]);
    expect(client.from).toHaveBeenCalledWith('transactions');
    expect(builder.select).toHaveBeenCalledWith('*, category:categories(*)');
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builder.order).toHaveBeenNthCalledWith(1, 'transaction_date', { ascending: false });
    expect(builder.order).toHaveBeenNthCalledWith(2, 'created_at', { ascending: false });
  });

  test('fetches one transaction using both id and owner id', async () => {
    const { builder, client } = createClient({ data: transaction });
    await expect(fetchTransaction('transaction-1', 'user-1', client)).resolves.toEqual(transaction);
    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', 'transaction-1');
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');
  });

  test('creates a transaction with explicit ownership', async () => {
    const { builder, client } = createClient({ data: transaction });
    const input = {
      id: 'transaction-1', category_id: 2, amount: 12.5, transaction_date: '2026-07-14',
      description: 'Lunch', source: 'manual', receipt_image_path: null,
    };
    await createTransaction('user-1', input, client);
    expect(builder.insert).toHaveBeenCalledWith({ user_id: 'user-1', ...input });
  });

  test('updates editable fields and filters by owner', async () => {
    const { builder, client } = createClient({ data: transaction });
    const input = {
      category_id: 2, amount: 15, transaction_date: '2026-07-14', description: 'Dinner',
      source: 'manual', receipt_image_path: null,
    };
    await updateTransaction('transaction-1', 'user-1', input, client);
    expect(builder.update).toHaveBeenCalledWith(expect.objectContaining(input));
    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', 'transaction-1');
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');
  });

  test('deletes only by transaction id and owner id', async () => {
    const { builder, client } = createClient();
    await deleteTransaction('transaction-1', 'user-1', client);
    expect(builder.eq).toHaveBeenNthCalledWith(1, 'id', 'transaction-1');
    expect(builder.eq).toHaveBeenNthCalledWith(2, 'user_id', 'user-1');
  });

  test('propagates database errors', async () => {
    const error = new Error('RLS denied');
    const { client } = createClient({ error });
    await expect(fetchTransactions('user-1', client)).rejects.toBe(error);
  });
});

describe('private receipt storage', () => {
  test('uploads an image using the receipts bucket and explicit content type', async () => {
    const { bucket, client } = createClient({ data: { path: 'user-1/transaction-1.jpg' } });
    const bytes = new ArrayBuffer(4);
    await uploadReceiptImage('user-1/transaction-1.jpg', bytes, 'image/jpeg', client);
    expect(client.storage.from).toHaveBeenCalledWith('receipts');
    expect(bucket.upload).toHaveBeenCalledWith('user-1/transaction-1.jpg', bytes, {
      contentType: 'image/jpeg', upsert: false,
    });
  });

  test('deletes an image and creates a short-lived signed URL', async () => {
    const { bucket, client } = createClient({ data: { signedUrl: 'https://signed.test/receipt' } });
    await expect(createReceiptSignedUrl('user-1/transaction-1.jpg', 300, client)).resolves.toBe(
      'https://signed.test/receipt',
    );
    await deleteReceiptImage('user-1/transaction-1.jpg', client);
    expect(bucket.createSignedUrl).toHaveBeenCalledWith('user-1/transaction-1.jpg', 300);
    expect(bucket.remove).toHaveBeenCalledWith(['user-1/transaction-1.jpg']);
  });
});
