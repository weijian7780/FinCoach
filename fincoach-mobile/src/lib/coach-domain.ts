import type {
  CoachConversation,
  CoachMessage,
  CoachTurnResponse,
  ConsentStatus,
} from './types';

export function sortConversations(
  conversations: readonly CoachConversation[],
): CoachConversation[] {
  return [...conversations].sort((left, right) => {
    const byTime = Date.parse(right.last_message_at) - Date.parse(left.last_message_at);
    return byTime || left.id.localeCompare(right.id);
  });
}

export function mergeTurn(
  messages: readonly CoachMessage[],
  turn: CoachTurnResponse,
): CoachMessage[] {
  const assistant = { ...turn.assistant_message, sources: [...turn.sources] };
  const byId = new Map<string, CoachMessage>();
  for (const message of [...messages, turn.user_message, assistant]) {
    byId.set(message.id, message);
  }
  return [...byId.values()].sort((left, right) => {
    const byTime = Date.parse(left.created_at) - Date.parse(right.created_at);
    return byTime || left.id.localeCompare(right.id);
  });
}

export function canSendCoachMessage(content: string, isSending: boolean): boolean {
  const length = content.trim().length;
  return !isSending && length >= 1 && length <= 1000;
}

const RECORDED_SPENDING_QUESTION = /\b(expenses?|spend|spending|spent|transactions?|purchases?|reports?|last month|previous month|compare|comparison|belanja|perbelanjaan|transaksi)\b/i;

export function shouldRequestSpendingConsent(
  content: string,
  consent: ConsentStatus,
): boolean {
  return consent !== 'granted' && RECORDED_SPENDING_QUESTION.test(content.trim());
}

export function shouldShowCoachSuggestions(
  messages: readonly CoachMessage[],
  isLoading: boolean,
): boolean {
  return !isLoading && messages.length === 0;
}

// --- Follow-up chips (Flag A: paced micro-coaching) -------------------------
// The coach answers ONE intent per turn (single locked format). When the user
// packed several intents into one message, or the answer asked for a figure, we
// surface the dropped thread as a tappable chip instead of leaving it unanswered.
// Pure and client-side: no API change, no extra network round-trip.
//
// A 'send' chip fires a fresh, self-contained query (it will route on its own).
// A 'prefill' chip only populates the composer — used when sending would require
// inventing the user's own number (e.g. their take-home pay). We never auto-send
// a financial figure the user did not type.
export type CoachFollowUpChip =
  | { readonly label: string; readonly kind: 'send'; readonly query: string }
  | { readonly label: string; readonly kind: 'prefill'; readonly text: string };

// The assistant asked for take-home (net) pay — the gross-income continuation.
const ASSISTANT_ASKS_TAKE_HOME = /take-?home\s+(?:\(net\)\s+)?pay/i;

// Intent families detectable in the USER's own words (not the answer).
const PERSONAL_STATUS_CUE = /\b(?:over\s+budget|my\s+budget|my\s+spending|how\s+much\s+(?:did|have)\s+i\s+spen|on\s+track|my\s+(?:savings\s+)?goal|my\s+balance)\b/i;
const ALLOCATION_CUE = /\b(?:allocate|split|divide|50\s*\/\s*30\s*\/\s*20|budgeting\s+(?:rule|method|framework))\b/i;
const STATUTORY_CUE = /\b(?:epf|kwsp|socso|perkeso|eis|income\s+tax)\b/i;

export function getCoachFollowUpChips(
  lastUserText: string,
  lastAssistantText: string,
): CoachFollowUpChip[] {
  const user = (lastUserText ?? '').trim();
  const assistant = (lastAssistantText ?? '').trim();
  if (!user && !assistant) return [];

  // Highest priority: the answer asked for take-home pay. Offer a PREFILL (not a
  // send) so the user supplies their real figure rather than a canned amount.
  // The scaffold is "How to split RM" — deliberately no "my", so the completed
  // message ("How to split RM3200") routes to the education/allocation path and
  // fires the deterministic 50/30/20 split on the user's real net figure. Phrasing
  // it as "my take-home pay" would route to personal records and skip that split.
  if (ASSISTANT_ASKS_TAKE_HOME.test(assistant)) {
    return [{ label: 'Split my take-home pay', kind: 'prefill', text: 'How to split RM' }];
  }

  // Multi-intent: only when the user packed 2+ distinct families into one turn.
  // A single-intent message was fully answered, so it needs no follow-up chip.
  const hasPersonal = PERSONAL_STATUS_CUE.test(user);
  const hasAllocation = ALLOCATION_CUE.test(user);
  const hasStatutory = STATUTORY_CUE.test(user);
  const familyCount = [hasPersonal, hasAllocation, hasStatutory].filter(Boolean).length;
  if (familyCount < 2) return [];

  // Offer the threads the single-format answer most likely dropped, ranked by how
  // often they get displaced by an allocation/education answer. Cap at 3.
  const chips: CoachFollowUpChip[] = [];
  if (hasPersonal) {
    chips.push({ label: 'Check my budget status', kind: 'send', query: 'How am I doing on my budget this month?' });
  }
  if (hasStatutory) {
    chips.push({ label: 'Current EPF rate', kind: 'send', query: 'What is the current EPF contribution rate for employees?' });
  }
  if (hasAllocation) {
    chips.push({ label: 'How to split my budget', kind: 'send', query: 'How should I split my monthly budget across categories?' });
  }
  return chips.slice(0, 3);
}

function statusOf(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null || !('status' in error)) return undefined;
  const status = (error as { status?: unknown }).status;
  return typeof status === 'number' ? status : undefined;
}

function codeOf(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null || !('code' in error)) return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === 'string' ? code : undefined;
}

export function coachErrorMessage(error: unknown): string {
  const reportErrors: Record<string, string> = {
    update_required: 'Update FinCoach to generate this report.',
    action_in_progress: 'Report generation is already in progress. Please wait before retrying.',
    attempt_expired: 'The report session expired. Retry to resume it safely.',
    attempt_id_reused: 'This report attempt has ended. Retry to start a new attempt.',
    report_artifact_invalid: 'The uploaded PDF could not be verified. Retry to check the report again.',
  };
  const reportError = reportErrors[codeOf(error) ?? ''];
  if (reportError) return reportError;
  if (codeOf(error) === 'network') {
    return 'FinCoach could not reach its server. Try again shortly or switch networks.';
  }
  if (codeOf(error) === 'offline') {
    return 'No internet connection. Your message has not been sent.';
  }
  if (codeOf(error) === 'timeout') {
    return 'FinCoach is still preparing your answer. Reopen this chat to check it before retrying.';
  }
  if (codeOf(error) === 'consent_required') {
    return 'Review the AI provider disclosure before sending this message.';
  }
  switch (statusOf(error)) {
    case 401:
      return 'Your session expired. Please sign in again.';
    case 404:
      return 'This conversation is no longer available.';
    case 409:
      return 'That message is already being processed.';
    case 429:
      return 'Too many coaching requests. Please wait and try again.';
    case 502:
      return 'The financial coach is temporarily unavailable.';
    case 504:
      return 'The financial coach is taking too long. Please retry.';
    default:
      return 'Unable to reach the financial coach. Check your connection and retry.';
  }
}
