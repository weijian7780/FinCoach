import type { CoachSource } from './types';

export type CoachSendState =
  | { status: 'idle' }
  | { status: 'sending'; content: string }
  | { status: 'failed'; content: string };

export type CoachSendEvent =
  | { type: 'send'; content: string }
  | { type: 'failure' }
  | { type: 'retry' }
  | { type: 'success' };

export function nextCoachSendState(state: CoachSendState, event: CoachSendEvent): CoachSendState {
  if (event.type === 'send') return { status: 'sending', content: event.content.trim() };
  if (event.type === 'failure' && state.status === 'sending') {
    return { status: 'failed', content: state.content };
  }
  if (event.type === 'retry' && state.status === 'failed') {
    return { status: 'sending', content: state.content };
  }
  if (event.type === 'success') return { status: 'idle' };
  return state;
}

export function coachSourceLabel(source: CoachSource): string | null {
  const name = source.title?.trim() || source.source?.trim();
  if (!name) return null;
  return `${name} · ${Math.round(source.similarity * 100)}% match`;
}

export function validateCoachTitle(title: string): string | null {
  const length = title.trim().length;
  if (length === 0) return 'Conversation name is required.';
  if (length > 80) return 'Conversation name must be 80 characters or fewer.';
  return null;
}

export function coachDeleteConfirmation(title: string): string {
  return `Delete “${title}”? This conversation and its messages cannot be undone.`;
}
