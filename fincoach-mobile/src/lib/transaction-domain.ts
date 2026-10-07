import { formatMoney, parseMoney } from '@/lib/savings-domain';
import type { Category, Profile, TransactionWithCategory, TransactionWriteInput } from '@/lib/types';

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

/** Build an editable draft; expected income is never recorded without confirmation. */
export function buildProfileIncomeDraft(profile: Pick<Profile, 'monthly_allowance' | 'income_source'>, categories: Category[], today: string): TransactionFormInput | null {
  const amount = parseMoney(String(profile.monthly_allowance ?? ''));
  if (amount == null || amount <= 0) return null;
  const source = ['Allowance', 'Part-time job', 'Scholarship', 'PTPTN'].includes(profile.income_source ?? '') ? profile.income_source! : '';
  const incomeCategories = categories.filter((category) => category.type === 'income');
  const category = incomeCategories.find((item) => source && item.name.toLowerCase() === source.toLowerCase())
    ?? incomeCategories.find((item) => item.name.toLowerCase() === 'income');
  return { type: 'income', amount: String(amount), source, transactionDate: today, description: '', categoryId: category?.id ?? null };
}

/** Advisory matching preserves genuine equal installments as separate payments. */
export function findSimilarIncomeEntries(entries: TransactionWithCategory[], draft: TransactionFormInput) {
  return entries.filter((entry) => entry.category.type === 'income' && entry.category_id === draft.categoryId
    && Number(entry.amount) === parseMoney(draft.amount)
    && entry.transaction_date.slice(0, 7) === draft.transactionDate.slice(0, 7)
    && entry.source.trim().toLowerCase() === draft.source.trim().toLowerCase());
}

/** Recovery accepts only the identical persisted financial payload. */
export function transactionMatchesInput(transaction: TransactionWithCategory, input: TransactionWriteInput) {
  return transaction.id === input.id && transaction.category_id === input.category_id
    && Number(transaction.amount) === input.amount && transaction.transaction_date === input.transaction_date
    && transaction.source.trim() === input.source.trim()
    && (transaction.description?.trim() || null) === (input.description?.trim() || null)
    && transaction.receipt_image_path === input.receipt_image_path;
}

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
