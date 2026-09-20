import { describe, expect, it } from 'vitest';

import {
  canSendCoachMessage,
  coachErrorMessage,
  getCoachFollowUpChips,
  mergeTurn,
  shouldRequestSpendingConsent,
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
  feedback: null,
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

  it('requests consent before sending questions that require recorded spending', () => {
    expect(shouldRequestSpendingConsent('what my expenses now', 'unset')).toBe(true);
    expect(shouldRequestSpendingConsent('How many transactions do I have?', 'denied')).toBe(true);
    expect(shouldRequestSpendingConsent('Compare my spending with last month', 'withdrawn')).toBe(true);
    expect(shouldRequestSpendingConsent('Where can I cut spending?', 'unset')).toBe(true);
    expect(shouldRequestSpendingConsent('Generate my monthly report', 'unset')).toBe(true);
    expect(shouldRequestSpendingConsent('Explain PTPTN repayment', 'unset')).toBe(false);
    expect(shouldRequestSpendingConsent('what my expenses now', 'granted')).toBe(false);
  });

  it('maps API states to safe user-facing copy', () => {
    expect(coachErrorMessage({ status: 401 })).toContain('sign in');
    expect(coachErrorMessage({ status: 429 })).toContain('Too many');
    expect(coachErrorMessage({ status: 504 })).toContain('taking too long');
    expect(coachErrorMessage({ status: 0, code: 'timeout' })).toContain('still preparing');
    expect(coachErrorMessage({ status: 0, code: 'offline' })).toContain('No internet connection');
    expect(coachErrorMessage(new Error('api-key=secret'))).not.toContain('secret');
  });
});

describe('coach follow-up chips', () => {
  it('offers a PREFILL (never a canned amount) when the answer asks for take-home pay', () => {
    const chips = getCoachFollowUpChips(
      'i earn 5000 before epf, how to split my budget',
      '**Insight** ... **Recommended action** Tell me your monthly take-home pay so I can allocate it accurately.',
    );
    expect(chips).toHaveLength(1);
    expect(chips[0].kind).toBe('prefill');
    // The chip must not carry a fabricated ringgit figure for the user to send blind.
    // It scaffolds "How to split RM" (no "my") so the completed reply routes to the
    // deterministic allocation split rather than a personal-records lookup.
    expect(chips[0].kind === 'prefill' && chips[0].text).toBe('How to split RM');
  });

  it('surfaces the dropped threads when the user packed several intents into one turn', () => {
    const chips = getCoachFollowUpChips(
      'am i over budget and also how to allocate rm4000 and whats the epf rate',
      '**Insight** The 50/30/20 framework allocates RM2,000 to needs [S1]. **Recommended action** Automate savings.',
    );
    const labels = chips.map((chip) => chip.label);
    // The allocation half was answered; budget-status and EPF were dropped -> chips.
    expect(labels).toContain('Check my budget status');
    expect(labels).toContain('Current EPF rate');
    expect(chips.every((chip) => chip.kind === 'send')).toBe(true);
    expect(chips.length).toBeLessThanOrEqual(3);
  });

  it('offers nothing for a single-intent message that was fully answered', () => {
    expect(getCoachFollowUpChips('am i over budget this month', 'You have RM50 left [S1].')).toEqual([]);
    expect(getCoachFollowUpChips('what is the 50/30/20 rule', 'It allocates 50% to needs [S1].')).toEqual([]);
    expect(getCoachFollowUpChips('', '')).toEqual([]);
  });

  it('prioritises the take-home prefill over multi-intent send chips', () => {
    // A gross multi-intent turn still leads with the net-pay prefill, not a split.
    const chips = getCoachFollowUpChips(
      'my gross is 5000, how to allocate and whats epf',
      'Tell me your monthly take-home (net) pay so I can allocate it accurately.',
    );
    expect(chips).toHaveLength(1);
    expect(chips[0].kind).toBe('prefill');
  });
});
