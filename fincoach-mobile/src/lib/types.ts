export type ConsentStatus = 'unset' | 'granted' | 'denied' | 'withdrawn';

export type Profile = {
  avatar_url: string | null;
  auto_backup_enabled: boolean;
  coaching_style: string | null;
  created_at: string;
  email: string;
  financial_status: string | null;
  full_name: string | null;
  id: string;
  income_source: string | null;
  monthly_allowance: number | null;
  onboarding_completed: boolean;
  spending_records_consent: ConsentStatus;
  university: string | null;
  updated_at: string;
  year_of_study: string | null;
};

export type ProfileUpdate = Partial<
  Pick<
    Profile,
    | 'avatar_url'
    | 'auto_backup_enabled'
    | 'coaching_style'
    | 'email'
    | 'financial_status'
    | 'full_name'
    | 'income_source'
    | 'monthly_allowance'
    | 'onboarding_completed'
    | 'spending_records_consent'
    | 'university'
    | 'year_of_study'
  >
>;

// ---- ERD CATEGORY (shared lookup) ----
export type Category = {
  color: string | null;
  id: number;
  icon: string | null;
  name: string;
  type: 'expense' | 'income';
  user_id: string | null;
};

export type CustomCategoryInput = {
  color: string;
  icon: string;
  name: string;
};

// ---- MONTHLY BUDGET (overall limit for one calendar month) ----
export type MonthlyBudget = {
  created_at: string;
  id: string;
  limit_amount: number;
  month: string;
  updated_at: string;
  user_id: string;
};

// ---- ERD BUDGET (category limit for one calendar month) ----
export type CategoryLimit = {
  amount: number;
  category_id: number;
  created_at: string;
  id: number;
  month: string;
  updated_at: string;
  user_id: string;
};

export type Budget = CategoryLimit;

export type BudgetMonthData = {
  categories: Category[];
  categoryLimits: CategoryLimit[];
  monthlyBudget: MonthlyBudget | null;
};

// ---- ERD TRANSACTION (manual or receipt-derived) ----
export type Transaction = {
  id: string;
  user_id: string;
  category_id: number;
  amount: number;
  transaction_date: string;
  description: string | null;
  source: string;
  receipt_image_path: string | null;
  created_at: string;
  updated_at: string;
};

export type TransactionWithCategory = Transaction & {
  category: Category;
};

export type TransactionWriteInput = Pick<
  Transaction,
  'id' | 'category_id' | 'amount' | 'transaction_date' | 'description' | 'source' | 'receipt_image_path'
>;

export type ReceiptItemDraft = {
  description: string;
  amount: number;
  confidence?: number;
};

export type ReceiptExtractionDraft = {
  merchant: string;
  transactionDate: string;
  totalAmount: string;
  suggestedCategory: string;
  items: ReceiptItemDraft[];
  confidence: {
    merchant: number;
    transactionDate: number;
    totalAmount: number;
    category: number;
  };
  rawLines: string[];
  enhancementStatus?: 'applied' | 'not_needed' | 'not_configured' | 'failed';
  reviewRequired?: boolean;
  reviewWarnings?: string[];
};

// ---- ERD SAVINGS_GOAL (many per user) ----
export type SavingsGoal = {
  id: string;
  user_id: string;
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null;
  created_at: string;
  updated_at: string;
};

export type SavingsGoalWriteInput = {
  name: string;
  target_amount: number;
  deadline: string | null;
};

export type SavingsContribution = {
  id: number;
  goal_id: string;
  amount: number;
  contributed_on: string;
  note: string | null;
  created_at: string;
};

export type SavingsContributionInput = {
  amount: number;
  contributed_on: string;
  note?: string | null;
};

// ---- ALERT AND REMINDER MANAGEMENT ----
export type NotificationType =
  | 'budget_warning'
  | 'budget_exceeded'
  | 'savings_deadline'
  | 'savings_milestone'
  | 'spending_reminder'
  | 'bill_reminder';

export type AlertKind = 'alert' | 'insight';
export type AlertFilter = 'all' | 'insights' | 'alerts';
export type ReminderRecurrence = 'none' | 'weekly' | 'monthly' | 'yearly';
export type SpendingFrequency = 'daily' | 'weekly';
export type AlertDeliveryStatus =
  | 'pending'
  | 'sending'
  | 'sent'
  | 'delivered'
  | 'partially_delivered'
  | 'retryable'
  | 'failed'
  | 'no_active_device';

export type NotificationPreferences = {
  user_id: string;
  budget_enabled: boolean;
  savings_enabled: boolean;
  savings_lead_days: number;
  savings_reminder_time: string;
  savings_milestones_enabled: boolean;
  spending_enabled: boolean;
  spending_frequency: SpendingFrequency;
  spending_weekday: number | null;
  spending_reminder_time: string;
  bills_enabled: boolean;
  default_bill_lead_days: number;
  default_bill_reminder_time: string;
  timezone: string;
  created_at: string;
  updated_at: string;
};

export type NotificationPreferencesUpdate = Partial<
  Omit<NotificationPreferences, 'user_id' | 'created_at' | 'updated_at'>
>;

export type BillReminder = {
  id: string;
  user_id: string;
  type: 'bill';
  title: string;
  amount: number | null;
  due_at: string;
  lead_days: number;
  recurrence: ReminderRecurrence;
  recurrence_anchor_day: number;
  enabled: boolean;
  next_trigger_at: string | null;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
};

export type BillReminderWriteInput = Pick<
  BillReminder,
  'title' | 'amount' | 'due_at' | 'lead_days' | 'recurrence' | 'recurrence_anchor_day' | 'enabled'
>;

export type AlertSourceData = {
  month?: string;
  milestone?: number;
  periodStart?: string;
  [key: string]: string | number | boolean | null | undefined;
};

export type AlertRecord = {
  id: string;
  user_id: string;
  type: NotificationType;
  kind: AlertKind;
  title: string;
  message: string;
  budget_id: string | null;
  category_limit_id: number | null;
  savings_goal_id: string | null;
  reminder_id: string | null;
  source_data: AlertSourceData;
  dedupe_key: string;
  scheduled_for: string | null;
  delivered_at: string | null;
  read_at: string | null;
  dismissed_at: string | null;
  delivery_status: AlertDeliveryStatus;
  delivery_error: string | null;
  delivery_attempt_count: number;
  delivery_claimed_at: string | null;
  next_delivery_attempt_at: string | null;
  delivery_receipts: Record<string, unknown>;
  created_at: string;
};

export type AlertWriteInput = Pick<
  AlertRecord,
  | 'type'
  | 'kind'
  | 'title'
  | 'message'
  | 'budget_id'
  | 'category_limit_id'
  | 'savings_goal_id'
  | 'reminder_id'
  | 'source_data'
  | 'dedupe_key'
  | 'scheduled_for'
>;

// ---- FINANCIAL REPORT AND ANALYTICS ----
export type ReportPreset = 'current_month' | 'previous_month' | 'last_3_months' | 'custom';

export type ReportType =
  | 'monthly'
  | 'monthly_category'
  | 'multi_month'
  | 'multi_month_category'
  | 'custom'
  | 'custom_category';

export type ReportSelection = {
  preset: ReportPreset;
  startDate: string;
  endDate: string;
  categoryId: number | null;
  reportType: ReportType;
};

export type ReportSourceData = {
  transactions: TransactionWithCategory[];
  monthlyBudgets: MonthlyBudget[];
  categoryLimits: CategoryLimit[];
  savingsGoals: SavingsGoal[];
};

export type ReportCategoryTotal = {
  categoryId: number;
  name: string;
  color: string | null;
  amount: number;
  percentage: number;
  transactionCount: number;
};

export type ReportTrendPoint = {
  month: string;
  income: number;
  expenses: number;
  net: number;
};

export type ReportCategoryBudget = {
  categoryId: number;
  limit: number;
  spent: number;
  remaining: number;
  exceeded: number;
  percentage: number;
  progressPercentage: number;
};

export type FinancialReport = {
  selection: ReportSelection;
  totalIncome: number;
  totalExpenses: number;
  netBalance: number;
  transactionCount: number;
  categoryTotals: ReportCategoryTotal[];
  trend: ReportTrendPoint[];
  budget: {
    limit: number;
    spent: number;
    remaining: number;
    exceeded: number;
    percentage: number;
    progressPercentage: number;
  };
  categoryBudgets: ReportCategoryBudget[];
  savings: {
    current: number;
    target: number;
    remaining: number;
    percentage: number;
    progressPercentage: number;
  };
};

// ---- ERD REPORT (immutable log of generated reports) ----
export type Report = {
  id: number;
  user_id: string;
  period: string;
  type: ReportType;
  generated_at: string;
};

// ---- FINANCIAL DATA EXPORT AND BACKUP ----
export type ExportFormat = 'csv' | 'pdf';
export type ExportContentType = 'transaction' | 'budget' | 'savings' | 'report';
export type OperationStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type BackupType = 'manual' | 'automatic';

export type ExportSelection = {
  format: ExportFormat;
  startDate: string;
  endDate: string;
  contents: ExportContentType[];
};

export type ExportSourceData = {
  transactions: TransactionWithCategory[];
  monthlyBudgets: MonthlyBudget[];
  categoryLimits: CategoryLimit[];
  savingsGoals: SavingsGoal[];
  reports: Report[];
};

export type DataExportRecord = {
  id: string;
  user_id: string;
  format: ExportFormat;
  status: OperationStatus;
  file_name: string;
  file_size_bytes: number | null;
  date_from: string;
  date_to: string;
  completed_at: string | null;
  created_at: string;
};

export type ExportContentRecord = {
  export_id: string;
  content_type: ExportContentType;
};

export type BackupRecord = {
  id: string;
  user_id: string;
  backup_type: BackupType;
  status: OperationStatus;
  file_name: string;
  storage_path: string | null;
  file_size_bytes: number | null;
  checksum_sha256: string | null;
  schema_version: number;
  last_restore_status: OperationStatus | null;
  last_restored_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type BackupSourceData = {
  profile: Profile | null;
  customCategories: Category[];
  transactions: Transaction[];
  monthlyBudgets: MonthlyBudget[];
  categoryLimits: CategoryLimit[];
  savingsGoals: SavingsGoal[];
  savingsContributions: SavingsContribution[];
  reports: Report[];
  notificationPreferences: NotificationPreferences | null;
  reminders: BillReminder[];
  alerts: AlertRecord[];
};

export type FinancialBackupDocumentV1 = {
  schemaVersion: 1;
  createdAt: string;
  userId: string;
  appVersion: string;
  data: BackupSourceData;
};

export type RestoreFinancialBackupResult = {
  profile: number;
  customCategories: number;
  transactions: number;
  monthlyBudgets: number;
  categoryLimits: number;
  savingsGoals: number;
  savingsContributions: number;
  reports: number;
  notificationPreferences: number;
  reminders: number;
  alerts: number;
};

// ---- AI FINANCIAL COACHING ----
export type CoachSource = {
  title: string | null;
  source: string | null;
  similarity: number;
  rank: number;
};

export type CoachMessage = {
  id: string;
  session_id: string;
  user_id: string;
  role: 'user' | 'assistant';
  content: string;
  reply_to_message_id: string | null;
  status: 'completed' | 'failed';
  error_code: string | null;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  created_at: string;
  sources: CoachSource[];
};

export type CoachConversation = {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at: string;
};

export type CoachTurnResponse = {
  user_message: CoachMessage;
  assistant_message: CoachMessage;
  sources: CoachSource[];
};
