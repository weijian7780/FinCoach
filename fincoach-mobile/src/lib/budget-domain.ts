export type LimitStatusLabel =
  | 'Within Limit'
  | 'Approaching Limit'
  | 'Limit Reached'
  | 'Exceeded';

export type LimitStatus = {
  label: LimitStatusLabel;
  tone: 'success' | 'warning' | 'danger';
};

export type CustomCategoryInput = {
  name: string;
  icon: string;
  color: string;
};

export type CustomCategoryErrors = Partial<Record<keyof CustomCategoryInput, string>>;

const MONTH_KEY = /^(\d{4})-(\d{2})-01$/;

function roundMoney(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function readMonth(value: string) {
  const match = MONTH_KEY.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) return null;
  return { year, monthIndex };
}

export function monthKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}-01`;
}

export function shiftMonth(value: string, amount: number) {
  const parsed = readMonth(value);
  if (!parsed) throw new Error('Invalid budget month.');
  return monthKey(new Date(parsed.year, parsed.monthIndex + amount, 1, 12));
}

export function formatBudgetMonth(value: string) {
  const parsed = readMonth(value);
  if (!parsed) return value;
  return new Intl.DateTimeFormat('en-MY', {
    month: 'long',
    year: 'numeric',
  }).format(new Date(parsed.year, parsed.monthIndex, 1, 12));
}

export function parseBudgetMoney(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null;
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return null;
  return roundMoney(parsed);
}

export function formatBudgetMoney(value: number) {
  return `RM ${roundMoney(value).toLocaleString('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function getLimitMetrics(usedAmount: number, limitAmount: number) {
  const used = roundMoney(Math.max(0, usedAmount));
  const limit = roundMoney(Math.max(0, limitAmount));
  const remaining = roundMoney(Math.max(0, limit - used));
  const exceeded = roundMoney(Math.max(0, used - limit));
  const ratio = limit > 0 ? used / limit : 0;

  return {
    usedAmount: used,
    limitAmount: limit,
    remainingAmount: remaining,
    exceededAmount: exceeded,
    ratio,
    progressRatio: Math.min(1, ratio),
    percentage: Math.round(ratio * 100),
  };
}

export function getLimitStatus(usedAmount: number, limitAmount: number): LimitStatus {
  const used = roundMoney(Math.max(0, usedAmount));
  const limit = roundMoney(Math.max(0, limitAmount));

  if (limit > 0 && used > limit) return { label: 'Exceeded', tone: 'danger' };
  if (limit > 0 && used === limit) return { label: 'Limit Reached', tone: 'danger' };
  if (limit > 0 && used / limit >= 0.8) {
    return { label: 'Approaching Limit', tone: 'warning' };
  }
  return { label: 'Within Limit', tone: 'success' };
}

export function validateMonthlyBudget(value: string, allocatedTotal: number) {
  const amount = parseBudgetMoney(value);
  if (amount == null || amount <= 0) return 'Enter an overall budget greater than RM 0.';
  const allocated = roundMoney(Math.max(0, allocatedTotal));
  if (amount < allocated) {
    return `Overall budget cannot be lower than the ${formatBudgetMoney(allocated)} already allocated.`;
  }
  return null;
}

export function validateCategoryAllocation(
  value: string,
  context: { overallLimit: number; otherAllocated: number },
) {
  const amount = parseBudgetMoney(value);
  if (amount == null || amount <= 0) return 'Enter a category limit greater than RM 0.';
  const available = roundMoney(Math.max(0, context.overallLimit - context.otherAllocated));
  if (amount > available) {
    return `Only ${formatBudgetMoney(available)} remains available for this category.`;
  }
  return null;
}

export function validateCustomCategory(
  input: CustomCategoryInput,
  existingNames: string[],
): CustomCategoryErrors {
  const errors: CustomCategoryErrors = {};
  const name = input.name.trim();
  const duplicate = existingNames.find(
    (existing) => existing.trim().toLocaleLowerCase('en') === name.toLocaleLowerCase('en'),
  );

  if (!name) errors.name = 'Enter a category name.';
  else if (name.length > 50) errors.name = 'Category name must be 50 characters or fewer.';
  else if (duplicate) errors.name = `A category named ${duplicate.trim()} already exists.`;

  if (!input.icon) errors.icon = 'Choose an icon.';
  if (!input.color) errors.color = 'Choose a colour.';
  return errors;
}
