import { describe, expect, it } from 'vitest';

import {
  canSendCoachMessage,
  coachErrorMessage,
  mergeTurn,
  shouldShowCoachSuggestions,
  sortConversations,
} from './coach-domain';
import type { CoachConversation, CoachMessage, CoachTurnResponse } from './types';

const conversation = (id: string, last_message_at: string): CoachConversation => ({
  id,
  user_id: 'user-1',
  title: id,
  created_at: last_message_at,
  updated_at: last_message_at,
  last_message_at,
});

const message = (id: string, role: 'user' | 'assistant', created_at: string): CoachMessage => ({
  id,
  session_id: 'session-1',
  user_id: 'user-1',
  role,
  content: id,
  reply_to_message_id: null,
  status: 'completed',
  error_code: null,
  model: null,
  prompt_tokens: null,
  completion_tokens: null,
  created_at,
  sources: [],
});

describe('coach domain', () => {
  it('sorts saved conversations newest first without mutating input', () => {
    const input = [conversation('older', '2026-07-16T00:00:00Z'), conversation('newer', '2026-07-17T00:00:00Z')];
    expect(sortConversations(input).map((item) => item.id)).toEqual(['newer', 'older']);
    expect(input.map((item) => item.id)).toEqual(['older', 'newer']);
  });

  it('merges a turn chronologically and removes duplicate message ids', () => {
    const existing = [message('old', 'assistant', '2026-07-17T01:00:00Z'), message('user', 'user', '2026-07-17T02:00:00Z')];
    const turn: CoachTurnResponse = {
      user_message: message('user', 'user', '2026-07-17T02:00:00Z'),
      assistant_message: message('reply', 'assistant', '2026-07-17T03:00:00Z'),
      sources: [],
    };
    expect(mergeTurn(existing, turn).map((item) => item.id)).toEqual(['old', 'user', 'reply']);
  });

  it('accepts only trimmed 1 to 1000 character input while idle', () => {
    expect(canSendCoachMessage('  Save money  ', false)).toBe(true);
    expect(canSendCoachMessage('   ', false)).toBe(false);
    expect(canSendCoachMessage('x'.repeat(1001), false)).toBe(false);
    expect(canSendCoachMessage('Save', true)).toBe(false);
  });

  it('shows suggestions only for a settled empty conversation', () => {
    expect(shouldShowCoachSuggestions([], false)).toBe(true);
    expect(shouldShowCoachSuggestions([], true)).toBe(false);
    expect(shouldShowCoachSuggestions([message('one', 'user', '2026-07-17T01:00:00Z')], false)).toBe(false);
  });

  it('maps API states to safe user-facing copy', () => {
    expect(coachErrorMessage({ status: 401 })).toContain('sign in');
    expect(coachErrorMessage({ status: 429 })).toContain('Too many');
    expect(coachErrorMessage({ status: 504 })).toContain('taking too long');
    expect(coachErrorMessage(new Error('api-key=secret'))).not.toContain('secret');
  });
});
