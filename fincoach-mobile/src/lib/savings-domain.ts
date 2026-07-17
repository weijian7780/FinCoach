export type GoalInput = {
  name: string;
  targetAmount: string;
  deadline: string;
};

export type ContributionInput = {
  amount: string;
  contributedOn: string;
  note: string;
};

export type FieldErrors<T> = Partial<Record<keyof T, string>>;

export type GoalStatus = {
  label: 'Goal reached!' | 'Almost there!' | 'On Track' | 'Needs Attention';
  color: string;
};

const DAY_MS = 86_400_000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function roundMoney(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function parseIsoDate(value: string) {
  if (!ISO_DATE.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const timestamp = Date.UTC(year, month - 1, day);
  const parsed = new Date(timestamp);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }
  return timestamp;
}

function daysBetween(from: string, to: string) {
  const fromTime = parseIsoDate(from);
  const toTime = parseIsoDate(to);
  if (fromTime == null || toTime == null) return null;
  return Math.round((toTime - fromTime) / DAY_MS);
}

export function isoDateToLocalDate(value: string) {
  if (parseIsoDate(value) == null) return null;
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day, 12);
}

export function formatGoalDate(value: string | null) {
  if (!value) return 'No deadline';
  const timestamp = parseIsoDate(value);
  if (timestamp == null) return value;
  return new Intl.DateTimeFormat('en-MY', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(timestamp));
}

export function parseMoney(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null;
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return null;
  return roundMoney(parsed);
}

export function formatMoney(value: number) {
  return `RM ${roundMoney(value).toLocaleString('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function todayIsoDate(now = new Date()) {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function validateGoalInput(
  input: GoalInput,
  context: { today: string; currentAmount: number },
): FieldErrors<GoalInput> {
  const errors: FieldErrors<GoalInput> = {};
  const name = input.name.trim();
  const target = parseMoney(input.targetAmount);

  if (!name) {
    errors.name = 'Enter a goal purpose.';
  } else if (name.length > 100) {
    errors.name = 'Goal purpose must be 100 characters or fewer.';
  }

  if (target == null || target <= 0) {
    errors.targetAmount = 'Enter a target amount greater than RM 0.';
  } else if (target < roundMoney(context.currentAmount)) {
    errors.targetAmount = `Target cannot be lower than the ${formatMoney(context.currentAmount)} already saved.`;
  }

  if (input.deadline && parseIsoDate(input.deadline) == null) {
    errors.deadline = 'Choose a valid deadline.';
  } else if (input.deadline && input.deadline < context.today) {
    errors.deadline = 'Choose today or a future date.';
  }

  return errors;
}

export function validateContributionInput(
  input: ContributionInput,
  context: { today: string; remainingAmount: number },
): FieldErrors<ContributionInput> {
  const errors: FieldErrors<ContributionInput> = {};
  const amount = parseMoney(input.amount);
  const remaining = roundMoney(Math.max(0, context.remainingAmount));

  if (amount == null || amount <= 0) {
    errors.amount = 'Enter a contribution greater than RM 0.';
  } else if (amount > remaining) {
    errors.amount = `Contribution cannot exceed the ${formatMoney(remaining)} remaining.`;
  }

  if (!input.contributedOn) {
    errors.contributedOn = 'Choose a contribution date.';
  } else if (parseIsoDate(input.contributedOn) == null) {
    errors.contributedOn = 'Choose a valid contribution date.';
  } else if (input.contributedOn > context.today) {
    errors.contributedOn = 'Contribution date cannot be in the future.';
  }

  if (input.note.trim().length > 200) {
    errors.note = 'Note must be 200 characters or fewer.';
  }

  return errors;
}

export function getSavingsMetrics(currentAmount: number, targetAmount: number) {
  const current = roundMoney(Math.max(0, currentAmount));
  const target = roundMoney(Math.max(0, targetAmount));
  const remainingAmount = roundMoney(Math.max(0, target - current));
  const ratio = target > 0 ? Math.min(1, current / target) : 0;

  return {
    currentAmount: current,
    targetAmount: target,
    remainingAmount,
    ratio,
    percentage: Math.round(ratio * 100),
  };
}

export function getGoalStatus(
  goal: {
    currentAmount: number;
    targetAmount: number;
    createdAt: string;
    deadline: string | null;
  },
  today: string,
): GoalStatus {
  const metrics = getSavingsMetrics(goal.currentAmount, goal.targetAmount);

  if (metrics.targetAmount > 0 && metrics.currentAmount >= metrics.targetAmount) {
    return { label: 'Goal reached!', color: '#06a96b' };
  }

  if (goal.deadline && goal.deadline < today) {
    return { label: 'Needs Attention', color: '#b07400' };
  }

  if (metrics.ratio >= 0.8) {
    return { label: 'Almost there!', color: '#06a96b' };
  }

  if (goal.deadline) {
    const createdDate = goal.createdAt.slice(0, 10);
    const totalDays = daysBetween(createdDate, goal.deadline);
    const elapsedDays = daysBetween(createdDate, today);
    if (totalDays != null && elapsedDays != null) {
      const expectedProgress = Math.min(1, Math.max(0, elapsedDays) / Math.max(1, totalDays));
      if (metrics.ratio >= Math.max(0, expectedProgress - 0.1)) {
        return { label: 'On Track', color: '#4648d4' };
      }
    }
  } else if (metrics.ratio >= 0.4) {
    return { label: 'On Track', color: '#4648d4' };
  }

  return { label: 'Needs Attention', color: '#b07400' };
}

export function getSavingsSuggestion(
  goal: { currentAmount: number; targetAmount: number; deadline: string | null },
  today: string,
) {
  const metrics = getSavingsMetrics(goal.currentAmount, goal.targetAmount);

  if (metrics.targetAmount > 0 && metrics.currentAmount >= metrics.targetAmount) {
    return 'Goal reached. Keep these savings set aside for their intended purpose.';
  }

  if (!goal.deadline) {
    return `${formatMoney(metrics.remainingAmount)} remains. Set a deadline to calculate a weekly saving amount.`;
  }

  const daysRemaining = daysBetween(today, goal.deadline);
  if (daysRemaining == null) {
    return `${formatMoney(metrics.remainingAmount)} remains. Choose a valid deadline to calculate a saving plan.`;
  }
  if (daysRemaining < 0) {
    return `${formatMoney(metrics.remainingAmount)} remains and the deadline has passed. Choose a new deadline or revise your contribution plan.`;
  }
  if (daysRemaining === 0) {
    return `${formatMoney(metrics.remainingAmount)} remains to reach this goal today.`;
  }

  const weeksRemaining = Math.max(1, Math.ceil(daysRemaining / 7));
  const weeklyAmount = roundMoney(metrics.remainingAmount / weeksRemaining);
  return `Save about ${formatMoney(weeklyAmount)} per week to reach this goal by ${formatGoalDate(goal.deadline)}.`;
}
