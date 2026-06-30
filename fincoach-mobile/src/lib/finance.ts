import { supabase } from '@/lib/supabase';
import type { Budget, Category, SavingsGoal, SavingsGoalInput } from '@/lib/types';

// First day of the current month as YYYY-MM-DD (the key BUDGET rows are stored under).
export function currentMonthStart() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${now.getFullYear()}-${month}-01`;
}

// ---------- CATEGORY (shared lookup) ----------
export async function fetchCategories() {
  const { data, error } = await supabase.from('categories').select('*').order('id', { ascending: true });
  if (error) throw error;
  return (data ?? []) as Category[];
}

// ---------- USER_CATEGORIES (which categories the user tracks) ----------
export async function fetchTrackedCategoryIds(userId: string) {
  const { data, error } = await supabase.from('user_categories').select('category_id').eq('user_id', userId);
  if (error) throw error;
  return (data ?? []).map((row) => row.category_id as number);
}

// Replace the user's tracked set with exactly `categoryIds`.
export async function setTrackedCategories(userId: string, categoryIds: number[]) {
  const { error: deleteError } = await supabase.from('user_categories').delete().eq('user_id', userId);
  if (deleteError) throw deleteError;

  if (categoryIds.length === 0) return;
  const rows = categoryIds.map((category_id) => ({ user_id: userId, category_id }));
  const { error } = await supabase.from('user_categories').insert(rows);
  if (error) throw error;
}

// ---------- BUDGET (per category, per month) ----------
export async function fetchBudgets(userId: string, month: string) {
  const { data, error } = await supabase.from('budgets').select('*').eq('user_id', userId).eq('month', month);
  if (error) throw error;
  return (data ?? []) as Budget[];
}

export async function upsertBudget(userId: string, categoryId: number, amount: number, month: string) {
  const { error } = await supabase.from('budgets').upsert(
    { user_id: userId, category_id: categoryId, amount, month, updated_at: new Date().toISOString() },
    { onConflict: 'user_id,category_id,month' },
  );
  if (error) throw error;
}

export async function deleteBudget(userId: string, categoryId: number, month: string) {
  const { error } = await supabase
    .from('budgets')
    .delete()
    .eq('user_id', userId)
    .eq('category_id', categoryId)
    .eq('month', month);
  if (error) throw error;
}

// ---------- SAVINGS_GOAL (many per user) ----------
export async function fetchSavingsGoals(userId: string) {
  const { data, error } = await supabase
    .from('savings_goals')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: true });
  if (error) throw error;
  return (data ?? []) as SavingsGoal[];
}

export async function createSavingsGoal(userId: string, input: SavingsGoalInput) {
  const { data, error } = await supabase
    .from('savings_goals')
    .insert({ user_id: userId, ...input })
    .select('*')
    .single();
  if (error) throw error;
  return data as SavingsGoal;
}

export async function updateSavingsGoal(id: number, patch: Partial<SavingsGoalInput>) {
  const { data, error } = await supabase
    .from('savings_goals')
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq('id', id)
    .select('*')
    .single();
  if (error) throw error;
  return data as SavingsGoal;
}

export async function deleteSavingsGoal(id: number) {
  const { error } = await supabase.from('savings_goals').delete().eq('id', id);
  if (error) throw error;
}
