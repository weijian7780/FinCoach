import { describe, expect, it, vi } from 'vitest';

import {
  coachDeleteConfirmation,
  coachFollowUpChips,
  nextCoachFeedback,
  coachSourceDisclosure,
  coachSourceLabel,
  nextCoachSendState,
  parseCoachMarkdown,
  parseCoachResponseSections,
  validateCoachTitle,
  scheduleCoachPendingNotice,
} from './coach-ui';

describe('coach UI state', () => {
  it('shows the long wait notice after 15 seconds and cancels late updates', () => {
    vi.useFakeTimers();
    const visible: boolean[] = [];
    try {
      const cancel = scheduleCoachPendingNotice((value) => visible.push(value));
      vi.advanceTimersByTime(14_999);
      expect(visible).toEqual([false]);
      vi.advanceTimersByTime(1);
      expect(visible).toEqual([false, true]);
      cancel();
      const cancelRetry = scheduleCoachPendingNotice((value) => visible.push(value));
      expect(visible).toEqual([false, true, false]);
      cancelRetry();
      vi.advanceTimersByTime(150_000);
      expect(visible).toEqual([false, true, false]);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it('moves through sending, failed, retry, and success states', () => {
    expect(nextCoachSendState(
      { status: 'idle' },
      { type: 'send', content: 'Help', messageId: 'message-1' },
    )).toEqual({
      status: 'sending',
      content: 'Help',
      messageId: 'message-1',
    });
    expect(nextCoachSendState(
      { status: 'sending', content: 'Help', messageId: 'message-1' },
      { type: 'failure' },
    )).toEqual({
      status: 'failed',
      content: 'Help',
      messageId: 'message-1',
    });
    expect(nextCoachSendState(
      { status: 'failed', content: 'Help', messageId: 'message-1' },
      { type: 'retry' },
    )).toEqual({
      status: 'sending',
      content: 'Help',
      messageId: 'message-1',
    });
    expect(nextCoachSendState(
      { status: 'sending', content: 'Help', messageId: 'message-1' },
      { type: 'success' },
    )).toEqual({ status: 'idle' });
  });

  it('shows a useful source label only when evidence exists', () => {
    expect(coachSourceLabel({ title: 'Budget Guide', source: 'guide.pdf', similarity: 0.82, rank: 1 })).toBe(
      'Budget Guide · 82% match',
    );
    expect(coachSourceLabel({
      title: 'official_ptptn_loan_guidance.md',
      source: 'official_ptptn_loan_guidance.md',
      similarity: 0.42,
      rank: 1,
    })).toBe('PTPTN Loan Guidance · 42% match');
    expect(coachSourceLabel({ title: null, source: null, similarity: 0.8, rank: 1 })).toBeNull();
  });

  it('parses Markdown bold markers into renderable text segments', () => {
    expect(parseCoachMarkdown('Save **RM50** this month.')).toEqual([
      { text: 'Save ', bold: false },
      { text: 'RM50', bold: true },
      { text: ' this month.', bold: false },
    ]);
    expect(parseCoachMarkdown('Keep **unfinished')).toEqual([
      { text: 'Keep **unfinished', bold: false },
    ]);
  });

  it('separates structured coaching responses into scannable sections', () => {
    expect(parseCoachResponseSections([
      '**Insight**',
      'Food spending reached **RM180**.',
      '',
      '**Recommended action**',
      'Set a **RM40 weekly limit**.',
      '',
      '**Educational guidance**',
      'Review the plan against your actual needs.',
    ].join('\n'))).toEqual([
      { kind: 'insight', title: 'Insight', content: 'Food spending reached **RM180**.' },
      { kind: 'action', title: 'Recommended action', content: 'Set a **RM40 weekly limit**.' },
      {
        kind: 'guidance',
        title: 'Educational guidance',
        content: 'Review the plan against your actual needs.',
      },
    ]);

    expect(parseCoachResponseSections('Start by tracking food spending.')).toEqual([
      { kind: 'body', title: null, content: 'Start by tracking food spending.' },
    ]);
  });

  it('renders a public explanation without an empty action card', () => {
    const sections = parseCoachResponseSections([
      '**Insight**',
      'The agency coordinates development projects.',
      '',
      'Which programme would you like to apply for?',
      '',
      '**Educational guidance**',
      'This is educational guidance, not licensed financial advice.',
    ].join('\n'));
    expect(sections.map((section) => section.kind)).toEqual(['insight', 'guidance']);
    expect(sections[0].content).toContain('Which programme');
  });

  it('keeps evidence collapsed until the user asks to view it', () => {
    expect(coachSourceDisclosure(3, false)).toEqual({
      label: 'View sources (3)',
      showSources: false,
    });
    expect(coachSourceDisclosure(3, true)).toEqual({
      label: 'Hide sources',
      showSources: true,
    });
    expect(coachSourceDisclosure(0, true)).toEqual({
      label: 'No sources',
      showSources: false,
    });
  });

  it('reads backend-selected follow-up chips from the ui_payload', () => {
    expect(
      coachFollowUpChips({
        follow_ups: [
          { label: 'Where can I cut spending?', query: 'Where can I cut spending?' },
          { label: 'Compare with last month', query: 'Compare my spending with last month' },
        ],
      }),
    ).toEqual([
      { label: 'Where can I cut spending?', query: 'Where can I cut spending?' },
      { label: 'Compare with last month', query: 'Compare my spending with last month' },
    ]);
  });

  it('returns no chips for empty, missing, or non-suggestion payloads', () => {
    expect(coachFollowUpChips(undefined)).toEqual([]);
    expect(coachFollowUpChips({})).toEqual([]);
    expect(
      coachFollowUpChips({
        type: 'clarification',
        action_type: 'create_reminder',
        question: 'When?',
        input_type: 'date',
        field: 'due',
        options: [],
        allow_other: false,
        draft: {},
      }),
    ).toEqual([]);
  });

  it('drops malformed chips and caps the list at three', () => {
    expect(
      coachFollowUpChips({
        follow_ups: [
          { label: 'Keep', query: 'Keep me' },
          { label: '', query: 'blank label' },
          { label: 'no query', query: '   ' },
          { label: 'A', query: 'a' },
          { label: 'B', query: 'b' },
          { label: 'C', query: 'c' },
        ] as never,
      }),
    ).toEqual([
      { label: 'Keep', query: 'Keep me' },
      { label: 'A', query: 'a' },
      { label: 'B', query: 'b' },
    ]);
  });

  it('selects feedback and clears it when the selected option is tapped again', () => {
    expect(nextCoachFeedback(null, 'helpful')).toBe('helpful');
    expect(nextCoachFeedback('helpful', 'helpful')).toBeNull();
    expect(nextCoachFeedback('helpful', 'not_helpful')).toBe('not_helpful');
  });

  it('validates trimmed conversation names and provides explicit delete copy', () => {
    expect(validateCoachTitle(' Semester plan ')).toBeNull();
    expect(validateCoachTitle('   ')).toContain('required');
    expect(validateCoachTitle('x'.repeat(81))).toContain('80');
    expect(coachDeleteConfirmation('Semester plan')).toContain('cannot be undone');
    expect(coachDeleteConfirmation('Semester plan')).toContain('Semester plan');
  });
});
