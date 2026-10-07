import {
  createReceiptSignedUrl,
  createTransaction,
  createTransactionWithRecovery,
  fetchIncomeCandidates,
  TransactionDraftConflictError,
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
    single: vi.fn(), maybeSingle: vi.fn(), gte: vi.fn(), lte: vi.fn(), limit: vi.fn(),
  };
  for (const method of ['select', 'eq', 'order', 'or', 'insert', 'update', 'delete', 'gte', 'lte', 'limit'] as const) {
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

describe('income candidates and draft recovery', () => {
  const input = { id: transaction.id, category_id: 2, amount: 12.5, transaction_date: '2026-07-14', description: 'Lunch', source: 'manual', receipt_image_path: null };
  test.each([['2026-12-31', '2026-12-01', '2026-12-31'], ['2027-01-01', '2027-01-01', '2027-01-31'], ['2028-02-01', '2028-02-01', '2028-02-29']])('bounds %s by calendar month and owner', async (date, start, end) => {
    const { builder, client } = createClient({ data: [transaction] });
    await expect(fetchIncomeCandidates('user-1', { ...input, transaction_date: date }, client)).resolves.toEqual({ entries: [transaction], truncated: false });
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
    expect(builder.eq).toHaveBeenCalledWith('category_id', 2);
    expect(builder.eq).toHaveBeenCalledWith('amount', 12.5);
    expect(builder.gte).toHaveBeenCalledWith('transaction_date', start);
    expect(builder.lte).toHaveBeenCalledWith('transaction_date', end);
    expect(builder.limit).toHaveBeenCalledWith(51);
  });
  test('marks full candidate results instead of claiming a complete check', async () => {
    const { client } = createClient({ data: Array.from({ length: 51 }, () => transaction) });
    const result = await fetchIncomeCandidates('user-1', input, client);
    expect(result.entries).toHaveLength(50);
    expect(result.truncated).toBe(true);
  });
  test('inserts once on success without a recovery read', async () => {
    const { builder, client } = createClient({ data: transaction });
    await expect(createTransactionWithRecovery('user-1', input, client)).resolves.toEqual(transaction);
    expect(builder.insert).toHaveBeenCalledTimes(1);
    expect(builder.maybeSingle).not.toHaveBeenCalled();
  });
  test('recovers a lost response by ID and owner without repeating the write', async () => {
    const { builder, client } = createClient({ data: transaction });
    builder.single.mockRejectedValueOnce(new TypeError('Network request failed'));
    await expect(createTransactionWithRecovery('user-1', input, client)).resolves.toEqual(transaction);
    expect(builder.insert).toHaveBeenCalledTimes(1);
    expect(builder.eq).toHaveBeenCalledWith('id', transaction.id);
    expect(builder.eq).toHaveBeenCalledWith('user_id', 'user-1');
  });
  test('preserves the original error when recovery cannot see an existing row', async () => {
    const failure = new TypeError('Network request failed');
    const { builder, client } = createClient();
    builder.single.mockRejectedValueOnce(failure);
    await expect(createTransactionWithRecovery('user-1', input, client)).rejects.toBe(failure);
    expect(builder.insert).toHaveBeenCalledTimes(1);
  });
  test('does not overwrite a conflicting saved payment', async () => {
    const { builder, client } = createClient({ data: { ...transaction, amount: 500 } });
    builder.single.mockResolvedValueOnce({ data: null, error: { code: '23505' } });
    await expect(createTransactionWithRecovery('user-1', input, client)).rejects.toBeInstanceOf(TransactionDraftConflictError);
    expect(builder.update).not.toHaveBeenCalled();
  });
  test('never exposes a different owner through recovery', async () => {
    const failure = new TypeError('Network request failed');
    const { builder, client } = createClient({ data: { ...transaction, user_id: 'another-user' } });
    builder.single.mockRejectedValueOnce(failure);
    await expect(createTransactionWithRecovery('user-1', input, client)).rejects.toBe(failure);
  });
  test('preserves the insert error if its recovery read also fails', async () => {
    const failure = new TypeError('Network request failed');
    const { builder, client } = createClient();
    builder.single.mockRejectedValueOnce(failure);
    builder.maybeSingle.mockRejectedValueOnce(new Error('Read unavailable'));
    await expect(createTransactionWithRecovery('user-1', input, client)).rejects.toBe(failure);
    expect(builder.insert).toHaveBeenCalledTimes(1);
  });
  test('propagates candidate query errors', async () => {
    const failure = new Error('Denied');
    const { client } = createClient({ error: failure });
    await expect(fetchIncomeCandidates('user-1', input, client)).rejects.toBe(failure);
  });
});

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
