import type {
  MonthlyBudget,
  SavingsGoal,
  TransactionWithCategory,
} from './types';

export type CoachInsightTone = 'critical' | 'healthy' | 'neutral' | 'warning';

export type CoachInsightCard = {
  detail: string;
  id: 'budget' | 'savings' | 'spending';
  prompt: string;
  title: string;
  tone: CoachInsightTone;
};

type CoachInsightInput = {
  includeRecordedSpending?: boolean;
  monthlyBudget: MonthlyBudget | null;
  now?: Date;
  savingsGoals: readonly SavingsGoal[];
  transactions: readonly TransactionWithCategory[];
};

function roundMoney(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function formatMoney(value: number) {
  return `RM${roundMoney(Math.max(0, value)).toLocaleString('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function monthPrefix(now: Date) {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${now.getFullYear()}-${month}`;
}

function budgetCard(
  monthlyBudget: MonthlyBudget,
  expenses: readonly TransactionWithCategory[],
): CoachInsightCard {
  const spent = roundMoney(expenses.reduce((sum, transaction) => sum + transaction.amount, 0));
  const limit = Math.max(0, monthlyBudget.limit_amount);
  const percentage = limit > 0 ? Math.round((spent / limit) * 100) : 0;
  const exceeded = spent > limit;
  const difference = roundMoney(Math.abs(limit - spent));
  const tone: CoachInsightTone = exceeded
    ? 'critical'
    : percentage >= 80
      ? 'warning'
      : 'healthy';

  return {
    id: 'budget',
    tone,
    title: exceeded
      ? `${formatMoney(difference)} over budget`
      : `${formatMoney(difference)} remaining`,
    detail: `${percentage}% used · ${formatMoney(spent)} of ${formatMoney(limit)}`,
    prompt: 'Where can I cut spending?',
  };
}

function spendingCard(
  expenses: readonly TransactionWithCategory[],
): CoachInsightCard | null {
  const byCategory = new Map<string, number>();
  for (const transaction of expenses) {
    const categoryName = transaction.category.name;
    byCategory.set(categoryName, roundMoney((byCategory.get(categoryName) ?? 0) + transaction.amount));
  }
  const highest = [...byCategory.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0];
  if (!highest) return null;

  const [categoryName, amount] = highest;
  return {
    id: 'spending',
    tone: 'neutral',
    title: `${categoryName}: ${formatMoney(amount)}`,
    detail: 'Highest recorded expense category this month',
    prompt: `How can I reduce ${categoryName} spending?`,
  };
}

function savingsCard(
  savingsGoals: readonly SavingsGoal[],
): CoachInsightCard | null {
  const goal = [...savingsGoals]
    .filter((item) => item.target_amount > 0 && item.current_amount < item.target_amount)
    .sort((left, right) => {
      if (left.deadline && right.deadline) return left.deadline.localeCompare(right.deadline);
      if (left.deadline) return -1;
      if (right.deadline) return 1;
      return left.created_at.localeCompare(right.created_at);
    })[0];
  if (!goal) return null;

  const remaining = roundMoney(goal.target_amount - goal.current_amount);
  const percentage = Math.round((goal.current_amount / goal.target_amount) * 100);
  const deadline = goal.deadline
    ? ` · Due ${new Intl.DateTimeFormat('en-MY', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(`${goal.deadline}T00:00:00Z`))}`
    : '';

  return {
    id: 'savings',
    tone: 'neutral',
    title: `${formatMoney(remaining)} to ${goal.name}`,
    detail: `${percentage}% saved${deadline}`,
    prompt: `Am I on track for my ${goal.name} goal?`,
  };
}

export function buildCoachInsightCards(input: CoachInsightInput): CoachInsightCard[] {
  const includeRecordedSpending = input.includeRecordedSpending ?? true;
  const currentMonth = monthPrefix(input.now ?? new Date());
  const expenses = includeRecordedSpending
    ? input.transactions.filter((transaction) => (
      transaction.category.type === 'expense'
      && transaction.transaction_date.startsWith(currentMonth)
    ))
    : [];
  const cards: CoachInsightCard[] = [];

  if (includeRecordedSpending && input.monthlyBudget) {
    cards.push(budgetCard(input.monthlyBudget, expenses));
  }
  if (includeRecordedSpending) {
    const spending = spendingCard(expenses);
    if (spending) cards.push(spending);
  }
  const savings = savingsCard(input.savingsGoals);
  if (savings) cards.push(savings);

  return cards;
}
