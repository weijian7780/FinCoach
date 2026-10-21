import { fetchAllRows } from '@/lib/pagination';
import { supabase } from '@/lib/supabase';
import { transactionMatchesInput } from '@/lib/transaction-domain';
import type { Category, TransactionWithCategory, TransactionWriteInput } from '@/lib/types';

type QueryResult = { data: unknown; error: unknown; count?: number | null };

type TransactionQuery = PromiseLike<QueryResult> & {
  range: (from: number, to: number) => TransactionQuery;
  delete: () => TransactionQuery;
  eq: (column: string, value: unknown) => TransactionQuery;
  gte: (column: string, value: unknown) => TransactionQuery;
  lte: (column: string, value: unknown) => TransactionQuery;
  limit: (value: number) => TransactionQuery;
  insert: (value: Record<string, unknown>) => TransactionQuery;
  maybeSingle: () => Promise<QueryResult>;
  order: (column: string, options: Record<string, unknown>) => TransactionQuery;
  or: (filters: string) => TransactionQuery;
  select: (...args: unknown[]) => TransactionQuery;
  single: () => Promise<QueryResult>;
  update: (value: Record<string, unknown>) => TransactionQuery;
};

type StorageBucket = {
  upload: (
    path: string,
    body: ArrayBuffer,
    options: { contentType: string; upsert: boolean },
  ) => Promise<QueryResult>;
  remove: (paths: string[]) => Promise<QueryResult>;
  createSignedUrl: (path: string, expiresIn: number) => Promise<QueryResult>;
};

export type TransactionDataClient = {
  from: (table: string) => TransactionQuery;
  storage: { from: (bucket: string) => StorageBucket };
};

const defaultClient = supabase as unknown as TransactionDataClient;
const transactionSelection = '*, category:categories(*)';

export class TransactionDraftConflictError extends Error {
  constructor(public readonly existing: TransactionWithCategory) {
    super('This draft was already saved with different values. Review the saved transaction.');
    this.name = 'TransactionDraftConflictError';
  }
}

/** Bound duplicate candidates by owner and calendar month, with an overflow sentinel. */
export async function fetchIncomeCandidates(userId: string, input: Pick<TransactionWriteInput, 'category_id' | 'amount' | 'transaction_date'>, client: TransactionDataClient = defaultClient) {
  const [year, month] = input.transaction_date.split('-').map(Number);
  const endDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const prefix = input.transaction_date.slice(0, 7);
  const { data, error } = await client.from('transactions').select(transactionSelection)
    .eq('user_id', userId).eq('category_id', input.category_id).eq('amount', input.amount)
    .gte('transaction_date', `${prefix}-01`).lte('transaction_date', `${prefix}-${endDay}`)
    .order('transaction_date', { ascending: false }).limit(51);
  throwIfError(error);
  const entries = (data ?? []) as TransactionWithCategory[];
  return { entries: entries.slice(0, 50), truncated: entries.length > 50 };
}

/** Insert once; recover a lost response using the same UUID without retrying the write. */
export async function createTransactionWithRecovery(userId: string, input: TransactionWriteInput, client: TransactionDataClient = defaultClient) {
  try {
    return await createTransaction(userId, input, client);
  } catch (originalError) {
    let existing: TransactionWithCategory | null;
    try { existing = await fetchTransaction(input.id, userId, client); }
    catch { throw originalError; }
    if (!existing || existing.user_id !== userId) throw originalError;
    if (!transactionMatchesInput(existing, input)) throw new TransactionDraftConflictError(existing);
    return existing;
  }
}

function throwIfError(error: unknown) {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string) {
  if (!data) throw new Error(message);
  return data as T;
}

export async function fetchTransactions(
  userId: string,
  client: TransactionDataClient = defaultClient,
) {
  return fetchAllRows<TransactionWithCategory>(() => client
    .from('transactions')
    .select(transactionSelection, { count: 'exact' })
    .eq('user_id', userId)
    .order('transaction_date', { ascending: false })
    .order('created_at', { ascending: false })
    .order('id', { ascending: false }));
}

export async function fetchTransactionCategories(
  userId: string,
  client: TransactionDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('categories')
    .select('*')
    .or(`user_id.is.null,user_id.eq.${userId}`)
    .order('type', { ascending: true })
    .order('name', { ascending: true });
  throwIfError(error);
  return (data ?? []) as Category[];
}

export async function fetchTransaction(
  transactionId: string,
  userId: string,
  client: TransactionDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('transactions')
    .select(transactionSelection)
    .eq('id', transactionId)
    .eq('user_id', userId)
    .maybeSingle();
  throwIfError(error);
  return data as TransactionWithCategory | null;
}

export async function createTransaction(
  userId: string,
  input: TransactionWriteInput,
  client: TransactionDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('transactions')
    .insert({ user_id: userId, ...input })
    .select(transactionSelection)
    .single();
  throwIfError(error);
  return requireRow<TransactionWithCategory>(data, 'Transaction was created but no row was returned.');
}

export async function updateTransaction(
  transactionId: string,
  userId: string,
  input: Omit<TransactionWriteInput, 'id'>,
  client: TransactionDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('transactions')
    .update({ ...input, updated_at: new Date().toISOString() })
    .eq('id', transactionId)
    .eq('user_id', userId)
    .select(transactionSelection)
    .single();
  throwIfError(error);
  return requireRow<TransactionWithCategory>(data, 'Transaction was updated but no row was returned.');
}

export async function deleteTransaction(
  transactionId: string,
  userId: string,
  client: TransactionDataClient = defaultClient,
) {
  const { error } = await client
    .from('transactions')
    .delete()
    .eq('id', transactionId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function uploadReceiptImage(
  path: string,
  bytes: ArrayBuffer,
  contentType: string,
  client: TransactionDataClient = defaultClient,
) {
  const { data, error } = await client.storage
    .from('receipts')
    .upload(path, bytes, { contentType, upsert: false });
  throwIfError(error);
  return requireRow<{ path: string }>(data, 'Receipt image was uploaded but no path was returned.');
}

export async function deleteReceiptImage(
  path: string,
  client: TransactionDataClient = defaultClient,
) {
  const { error } = await client.storage.from('receipts').remove([path]);
  throwIfError(error);
}

export async function createReceiptSignedUrl(
  path: string,
  expiresIn = 300,
  client: TransactionDataClient = defaultClient,
) {
  const { data, error } = await client.storage.from('receipts').createSignedUrl(path, expiresIn);
  throwIfError(error);
  return requireRow<{ signedUrl: string }>(data, 'Receipt URL could not be created.').signedUrl;
}

/** A receipt draft retains its ID and upload state until its commit is confirmed. */
export async function saveReceiptTransaction(
  userId: string,
  input: TransactionWriteInput,
  state: { id: string; uploading: boolean; uploaded: boolean },
  readBytes: () => Promise<ArrayBuffer>,
  contentType: string,
  client: TransactionDataClient = defaultClient,
) {
  if (state.uploading) throw new Error('This receipt is already being saved.');
  if (input.id !== state.id || !input.receipt_image_path) throw new Error('Invalid receipt draft.');
  state.uploading = true;
  try {
    const existing = await fetchTransaction(state.id, userId, client);
    if (existing) {
      if (!transactionMatchesInput(existing, input)) throw new TransactionDraftConflictError(existing);
      return existing;
    }
    if (!state.uploaded) {
      const bytes = await readBytes();
      try { await uploadReceiptImage(input.receipt_image_path, bytes, contentType, client); }
      catch (uploadError) {
        // The upload may have committed despite a lost response. Verify before continuing.
        try { await createReceiptSignedUrl(input.receipt_image_path, 300, client); }
        catch { throw uploadError; }
      }
      state.uploaded = true;
    }
    return await createTransactionWithRecovery(userId, input, client);
  } finally {
    // The image must survive unknown database outcomes; a retry resolves by ID.
    state.uploading = false;
  }
}
