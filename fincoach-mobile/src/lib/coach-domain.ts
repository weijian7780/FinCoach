import type { CoachConversation, CoachMessage, CoachTurnResponse } from './types';

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

export function shouldShowCoachSuggestions(
  messages: readonly CoachMessage[],
  isLoading: boolean,
): boolean {
  return !isLoading && messages.length === 0;
}

function statusOf(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null || !('status' in error)) return undefined;
  const status = (error as { status?: unknown }).status;
  return typeof status === 'number' ? status : undefined;
}

export function coachErrorMessage(error: unknown): string {
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
