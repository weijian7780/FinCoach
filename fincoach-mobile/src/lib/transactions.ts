import { supabase } from '@/lib/supabase';
import type { Category, TransactionWithCategory, TransactionWriteInput } from '@/lib/types';

type QueryResult = { data: unknown; error: unknown };

type TransactionQuery = PromiseLike<QueryResult> & {
  delete: () => TransactionQuery;
  eq: (column: string, value: unknown) => TransactionQuery;
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
  const { data, error } = await client
    .from('transactions')
    .select(transactionSelection)
    .eq('user_id', userId)
    .order('transaction_date', { ascending: false })
    .order('created_at', { ascending: false });
  throwIfError(error);
  return (data ?? []) as TransactionWithCategory[];
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
