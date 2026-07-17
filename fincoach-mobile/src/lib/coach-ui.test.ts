import { describe, expect, it } from 'vitest';

import {
  coachDeleteConfirmation,
  coachSourceLabel,
  nextCoachSendState,
  validateCoachTitle,
} from './coach-ui';

describe('coach UI state', () => {
  it('moves through sending, failed, retry, and success states', () => {
    expect(nextCoachSendState({ status: 'idle' }, { type: 'send', content: 'Help' })).toEqual({
      status: 'sending',
      content: 'Help',
    });
    expect(nextCoachSendState({ status: 'sending', content: 'Help' }, { type: 'failure' })).toEqual({
      status: 'failed',
      content: 'Help',
    });
    expect(nextCoachSendState({ status: 'failed', content: 'Help' }, { type: 'retry' })).toEqual({
      status: 'sending',
      content: 'Help',
    });
    expect(nextCoachSendState({ status: 'sending', content: 'Help' }, { type: 'success' })).toEqual({ status: 'idle' });
  });

  it('shows a useful source label only when evidence exists', () => {
    expect(coachSourceLabel({ title: 'Budget Guide', source: 'guide.pdf', similarity: 0.82, rank: 1 })).toBe(
      'Budget Guide · 82% match',
    );
    expect(coachSourceLabel({ title: null, source: null, similarity: 0.8, rank: 1 })).toBeNull();
  });

  it('validates trimmed conversation names and provides explicit delete copy', () => {
    expect(validateCoachTitle(' Semester plan ')).toBeNull();
    expect(validateCoachTitle('   ')).toContain('required');
    expect(validateCoachTitle('x'.repeat(81))).toContain('80');
    expect(coachDeleteConfirmation('Semester plan')).toContain('cannot be undone');
    expect(coachDeleteConfirmation('Semester plan')).toContain('Semester plan');
  });
});
