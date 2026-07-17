import { formatMoney, parseMoney } from '@/lib/savings-domain';
import type { Category, TransactionWithCategory } from '@/lib/types';

export type TransactionType = 'expense' | 'income';

export type TransactionFormInput = {
  type: TransactionType;
  amount: string;
  source: string;
  transactionDate: string;
  description: string;
  categoryId: number | null;
};

export type TransactionFieldErrors = Partial<Record<keyof TransactionFormInput, string>>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isValidIsoDate(value: string) {
  if (!ISO_DATE.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export function validateTransactionInput(
  input: TransactionFormInput,
  categories: Category[],
  today: string,
): TransactionFieldErrors {
  const errors: TransactionFieldErrors = {};
  const amount = parseMoney(input.amount);
  const source = input.source.trim();
  const category = categories.find((candidate) => candidate.id === input.categoryId);

  if (amount == null || amount <= 0) errors.amount = 'Enter an amount greater than RM 0.';
  if (!source) errors.source = 'Enter a merchant or income source.';
  else if (source.length > 120) errors.source = 'Source must be 120 characters or fewer.';

  if (!input.categoryId || !category) errors.categoryId = 'Choose a category.';
  else if (category.type !== input.type) {
    errors.categoryId = `Choose an ${input.type} category.`;
  }

  if (!isValidIsoDate(input.transactionDate)) errors.transactionDate = 'Choose a valid transaction date.';
  else if (input.transactionDate > today) errors.transactionDate = 'Transaction date cannot be in the future.';

  if (input.description.trim().length > 300) errors.description = 'Note must be 300 characters or fewer.';
  return errors;
}

export function groupTransactionsByDate(transactions: TransactionWithCategory[]) {
  const groups: { date: string; items: TransactionWithCategory[] }[] = [];
  for (const transaction of transactions) {
    const last = groups.at(-1);
    if (last?.date === transaction.transaction_date) last.items.push(transaction);
    else groups.push({ date: transaction.transaction_date, items: [transaction] });
  }
  return groups;
}

export function filterTransactions(transactions: TransactionWithCategory[], categoryId: number | null) {
  return categoryId == null
    ? transactions
    : transactions.filter((transaction) => transaction.category_id === categoryId);
}

export function formatTransactionAmount(transaction: TransactionWithCategory) {
  const formatted = formatMoney(transaction.amount);
  return transaction.category.type === 'income' ? `+${formatted}` : `-${formatted}`;
}
