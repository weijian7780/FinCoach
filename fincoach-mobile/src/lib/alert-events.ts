import { createIdempotentAlert, ensureNotificationPreferences } from './alerts';
import { buildBudgetDedupeKey, buildSavingsDedupeKey, getCrossedBudgetThreshold, getCrossedSavingsMilestones } from './alerts-domain';
import { fetchBudgetMonth } from './budget';
import { fetchTransactions } from './transactions';
import type { AlertRecord, AlertWriteInput, BudgetMonthData, NotificationPreferences, SavingsGoal, TransactionWithCategory } from './types';

type BudgetEventDependencies = {
  fetchPreferences: (userId: string) => Promise<NotificationPreferences>;
  fetchTransactions: (userId: string) => Promise<TransactionWithCategory[]>;
  fetchBudgetMonth: (userId: string, month: string) => Promise<BudgetMonthData>;
  createAlert: (userId: string, input: AlertWriteInput) => Promise<AlertRecord>;
};

type SavingsEventDependencies = Pick<BudgetEventDependencies, 'fetchPreferences' | 'createAlert'>;

const defaultDependencies: BudgetEventDependencies = {
  fetchPreferences: ensureNotificationPreferences,
  fetchTransactions,
  fetchBudgetMonth,
  createAlert: createIdempotentAlert,
};

function transactionMonth(item: TransactionWithCategory) {
  return `${item.transaction_date.slice(0, 7)}-01`;
}

function isExpense(item: TransactionWithCategory | null | undefined) {
  return item?.category.type === 'expense';
}

function amountForMonth(item: TransactionWithCategory | null, month: string) {
  return item && isExpense(item) && transactionMonth(item) === month ? item.amount : 0;
}

function amountForCategory(item: TransactionWithCategory | null, month: string, categoryId: number) {
  return item && isExpense(item) && transactionMonth(item) === month && item.category_id === categoryId ? item.amount : 0;
}

function budgetAlertInput(input: {
  budgetId: string | null;
  categoryLimitId: number | null;
  categoryName?: string;
  currentUsed: number;
  limit: number;
  month: string;
  scope: 'overall' | 'category';
  sourceId: string | number;
  threshold: 'warning' | 'exceeded';
}): AlertWriteInput {
  const percentage = Math.round((input.currentUsed / input.limit) * 100);
  const subject = input.scope === 'category' ? `${input.categoryName ?? 'Category'} limit` : 'Monthly budget';
  const exceeded = input.threshold === 'exceeded';
  return {
    type: exceeded ? 'budget_exceeded' : 'budget_warning',
    kind: 'alert',
    title: exceeded ? `${subject} exceeded` : `${subject} is almost reached`,
    message: exceeded
      ? `You have used ${percentage}% of this limit. Review your spending.`
      : `You have used ${percentage}% of this limit. RM ${Math.max(0, input.limit - input.currentUsed).toFixed(2)} remains.`,
    budget_id: input.budgetId,
    category_limit_id: input.categoryLimitId,
    savings_goal_id: null,
    reminder_id: null,
    source_data: { month: input.month, scope: input.scope, categoryName: input.categoryName ?? null },
    dedupe_key: buildBudgetDedupeKey({ scope: input.scope, sourceId: input.sourceId, month: input.month, threshold: input.threshold }),
    scheduled_for: null,
  };
}

export async function emitBudgetAlertsAfterTransactionChange(
  userId: string,
  previousTransaction: TransactionWithCategory | null,
  currentTransaction: TransactionWithCategory,
  dependencies: BudgetEventDependencies = defaultDependencies,
): Promise<number> {
  const preferences = await dependencies.fetchPreferences(userId);
  if (!preferences.budget_enabled || (!isExpense(previousTransaction) && !isExpense(currentTransaction))) return 0;

  const months = new Set<string>();
  if (isExpense(previousTransaction)) months.add(transactionMonth(previousTransaction!));
  if (isExpense(currentTransaction)) months.add(transactionMonth(currentTransaction));
  const transactions = await dependencies.fetchTransactions(userId);
  let created = 0;

  for (const month of months) {
    const budget = await dependencies.fetchBudgetMonth(userId, month);
    const monthTransactions = transactions.filter((item) => isExpense(item) && transactionMonth(item) === month);
    const currentOverall = monthTransactions.reduce((sum, item) => sum + item.amount, 0);
    const previousOverall = currentOverall - amountForMonth(currentTransaction, month) + amountForMonth(previousTransaction, month);

    if (budget.monthlyBudget) {
      const threshold = getCrossedBudgetThreshold(previousOverall, currentOverall, budget.monthlyBudget.limit_amount);
      if (threshold) {
        await dependencies.createAlert(userId, budgetAlertInput({ budgetId: budget.monthlyBudget.id, categoryLimitId: null, currentUsed: currentOverall, limit: budget.monthlyBudget.limit_amount, month, scope: 'overall', sourceId: budget.monthlyBudget.id, threshold }));
        created += 1;
      }
    }

    const impactedCategories = new Set<number>();
    if (previousTransaction && amountForMonth(previousTransaction, month)) impactedCategories.add(previousTransaction.category_id);
    if (amountForMonth(currentTransaction, month)) impactedCategories.add(currentTransaction.category_id);
    for (const categoryId of impactedCategories) {
      const limit = budget.categoryLimits.find((item) => item.category_id === categoryId);
      if (!limit) continue;
      const currentUsed = monthTransactions.filter((item) => item.category_id === categoryId).reduce((sum, item) => sum + item.amount, 0);
      const previousUsed = currentUsed - amountForCategory(currentTransaction, month, categoryId) + amountForCategory(previousTransaction, month, categoryId);
      const threshold = getCrossedBudgetThreshold(previousUsed, currentUsed, limit.amount);
      if (!threshold) continue;
      const categoryName = budget.categories.find((item) => item.id === categoryId)?.name;
      await dependencies.createAlert(userId, budgetAlertInput({ budgetId: budget.monthlyBudget?.id ?? null, categoryLimitId: limit.id, categoryName, currentUsed, limit: limit.amount, month, scope: 'category', sourceId: limit.id, threshold }));
      created += 1;
    }
  }
  return created;
}

export async function emitSavingsMilestonesAfterContribution(
  userId: string,
  goal: SavingsGoal,
  previousAmount: number,
  currentAmount: number,
  dependencies: SavingsEventDependencies = defaultDependencies,
): Promise<number> {
  const preferences = await dependencies.fetchPreferences(userId);
  if (!preferences.savings_enabled || !preferences.savings_milestones_enabled) return 0;
  const milestones = getCrossedSavingsMilestones(previousAmount, currentAmount, goal.target_amount);
  for (const milestone of milestones) {
    const complete = milestone === 100;
    await dependencies.createAlert(userId, {
      type: 'savings_milestone',
      kind: 'insight',
      title: complete ? 'Savings goal completed' : `${milestone}% savings milestone reached`,
      message: complete ? `You reached your ${goal.name} target.` : `Your ${goal.name} goal is now at least ${milestone}% funded.`,
      budget_id: null,
      category_limit_id: null,
      savings_goal_id: goal.id,
      reminder_id: null,
      source_data: { milestone },
      dedupe_key: buildSavingsDedupeKey(goal.id, 'milestone', milestone),
      scheduled_for: null,
    });
  }
  return milestones.length;
}
