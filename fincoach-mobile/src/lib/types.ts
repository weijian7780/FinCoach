export type ConsentStatus = 'unset' | 'granted' | 'denied' | 'withdrawn';

export type Profile = {
  avatar_url: string | null;
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
  id: number;
  name: string;
  type: 'expense' | 'income';
  icon: string | null;
};

// ---- ERD BUDGET (per category, per month) ----
export type Budget = {
  id: number;
  user_id: string;
  category_id: number;
  amount: number;
  month: string; // YYYY-MM-DD (first day of month)
  created_at: string;
  updated_at: string;
};

// ---- ERD SAVINGS_GOAL (many per user) ----
export type SavingsGoal = {
  id: number;
  user_id: string;
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null;
  created_at: string;
  updated_at: string;
};

export type SavingsGoalInput = {
  name: string;
  target_amount: number;
  current_amount?: number;
  deadline?: string | null;
};

// ---- ERD REPORT (log of generated reports) ----
export type Report = {
  id: number;
  user_id: string;
  period: string;
  type: string;
  generated_at: string;
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
