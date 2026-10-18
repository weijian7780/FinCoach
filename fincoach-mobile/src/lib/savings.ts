import { supabase } from '@/lib/supabase';
import type {
  SavingsContribution,
  SavingsContributionInput,
  SavingsGoal,
  SavingsGoalWriteInput,
} from '@/lib/types';

type QueryResult = { data: unknown; error: unknown };

type SavingsQuery = PromiseLike<QueryResult> & {
  select: (...args: unknown[]) => SavingsQuery;
  eq: (column: string, value: unknown) => SavingsQuery;
  order: (column: string, options: Record<string, unknown>) => SavingsQuery;
  insert: (value: Record<string, unknown>) => SavingsQuery;
  update: (value: Record<string, unknown>) => SavingsQuery;
  delete: () => SavingsQuery;
  single: () => Promise<QueryResult>;
  maybeSingle: () => Promise<QueryResult>;
};

export type SavingsDataClient = {
  from: (table: string) => SavingsQuery;
};

const defaultClient = supabase as unknown as SavingsDataClient;

function throwIfError(error: unknown) {
  if (error) throw error;
}

function requireRow<T>(data: unknown, message: string) {
  if (!data) throw new Error(message);
  return data as T;
}

export async function fetchSavingsGoals(userId: string, client: SavingsDataClient = defaultClient) {
  const { data, error } = await client
    .from('savings_goals')
    .select('*')
    .eq('user_id', userId)
    .order('deadline', { ascending: true, nullsFirst: false })
    .order('created_at', { ascending: true });
  throwIfError(error);
  return (data ?? []) as SavingsGoal[];
}

export async function fetchSavingsGoal(
  goalId: string,
  userId: string,
  client: SavingsDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('savings_goals')
    .select('*')
    .eq('id', goalId)
    .eq('user_id', userId)
    .maybeSingle();
  throwIfError(error);
  return data as SavingsGoal | null;
}

export async function createSavingsGoal(
  userId: string,
  input: SavingsGoalWriteInput,
  client: SavingsDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('savings_goals')
    .insert({ user_id: userId, ...input })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<SavingsGoal>(data, 'Savings goal was created but no row was returned.');
}

export async function updateSavingsGoal(
  goalId: string,
  userId: string,
  input: SavingsGoalWriteInput,
  client: SavingsDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('savings_goals')
    .update({ ...input, updated_at: new Date().toISOString() })
    .eq('id', goalId)
    .eq('user_id', userId)
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<SavingsGoal>(data, 'Savings goal was updated but no row was returned.');
}

export async function deleteSavingsGoal(
  goalId: string,
  userId: string,
  client: SavingsDataClient = defaultClient,
) {
  const { error } = await client
    .from('savings_goals')
    .delete()
    .eq('id', goalId)
    .eq('user_id', userId);
  throwIfError(error);
}

export async function fetchSavingsContributions(
  goalId: string,
  client: SavingsDataClient = defaultClient,
) {
  const { data, error } = await client
    .from('savings_contributions')
    .select('*')
    .eq('goal_id', goalId)
    .order('contributed_on', { ascending: false })
    .order('created_at', { ascending: false });
  throwIfError(error);
  return (data ?? []) as SavingsContribution[];
}

export async function addSavingsContribution(
  goalId: string,
  input: SavingsContributionInput,
  client: SavingsDataClient = defaultClient,
) {
  const note = input.note?.trim() || null;
  const { data, error } = await client
    .from('savings_contributions')
    .insert({ goal_id: goalId, amount: input.amount, contributed_on: input.contributed_on, note })
    .select('*')
    .single();
  throwIfError(error);
  return requireRow<SavingsContribution>(data, 'Contribution was added but no row was returned.');
}

export async function deleteSavingsContribution(
  contributionId: number,
  client: SavingsDataClient = defaultClient,
) {
  const { error } = await client.from('savings_contributions').delete().eq('id', contributionId);
  throwIfError(error);
}
