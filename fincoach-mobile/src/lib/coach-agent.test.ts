import { describe, expect, it } from 'vitest';

import {
  clarificationReply,
  isCoachAction,
  isCoachChoices,
  isCoachClarification,
  isCoachReadClarification,
  reportSelectionFromCoachAction,
} from './coach-agent';

describe('coach agent interaction domain', () => {
  it('recognises a read question without a write action type', () => {
    expect(isCoachReadClarification({
      type: 'read_clarification',
      question: 'Which month?',
      input_type: 'single_select',
      field: 'month',
      options: [{ id: 'july', label: 'July', value: '2026-07' }],
      allow_other: true,
    })).toBe(true);
  });

  it('rejects a read clarification with malformed options or input mode', () => {
    expect(isCoachReadClarification({
      type: 'read_clarification',
      question: 'Which month?',
      input_type: 'single_select',
      field: 'month',
      options: [{ id: 'july', label: 'July' }],
      allow_other: true,
    })).toBe(false);
    expect(isCoachReadClarification({
      type: 'read_clarification',
      question: 'Which month?',
      input_type: 'carousel',
      field: 'month',
      options: [],
      allow_other: true,
    })).toBe(false);
  });

  it('keeps read and write clarification guards mutually exclusive', () => {
    const readPayload = {
      type: 'read_clarification',
      question: 'Which month?',
      input_type: 'single_select',
      field: 'month',
      options: [],
      allow_other: true,
    };
    expect(isCoachAction(readPayload)).toBe(false);
    expect(isCoachClarification(readPayload)).toBe(false);
  });

  it('recognises only supported clarification and action payloads', () => {
    expect(isCoachClarification({
      type: 'clarification',
      action_type: 'create_reminder',
      question: 'When?',
      input_type: 'date',
      field: 'due_at',
      options: [],
      allow_other: true,
      draft: {},
    })).toBe(true);
    expect(isCoachClarification({
      type: 'clarification',
      question: 'When?',
      input_type: 'date',
      field: 'due_at',
      options: [],
      allow_other: true,
      draft: {},
    })).toBe(false);
    expect(isCoachAction({
      type: 'action',
      action_id: 'action-1',
      action_type: 'create_reminder',
      status: 'pending',
      title: 'Create reminder?',
      description: 'Review it.',
      confirm_label: 'Create reminder',
      arguments: {},
      fields: [],
    })).toBe(true);
    expect(isCoachAction({ type: 'action', action_type: 'delete_everything' })).toBe(false);
  });

  it('lets a user answer a suggestion or flexible Other text naturally', () => {
    expect(clarificationReply({ label: 'Tomorrow', value: '2026-07-25' })).toEqual({
      content: 'Tomorrow',
      value: '2026-07-25',
    });
    expect(clarificationReply(null, '  Next Friday after class, around 6 pm  ')).toEqual({
      content: 'Next Friday after class, around 6 pm',
      value: 'Next Friday after class, around 6 pm',
    });
    expect(clarificationReply(null, '   ')).toBeNull();
  });

  it('maps an approved report action into the existing report selection model', () => {
    expect(reportSelectionFromCoachAction({
      period: 'current_month',
      start_date: '2026-07-01',
      end_date: '2026-07-31',
      category_name: null,
    })).toEqual({
      preset: 'current_month',
      reportType: 'monthly',
      startDate: '2026-07-01',
      endDate: '2026-07-31',
      categoryId: null,
    });
  });
});

describe('coach LLM choice payloads', () => {
  const valid = {
    type: 'coach_choices',
    input_type: 'single_select',
    options: [
      { id: 'c1', label: 'Repay PTPTN', query: 'How do I repay PTPTN?' },
      { id: 'c2', label: 'My balance', query: 'How much PTPTN do I owe?' },
    ],
  };

  it('recognises a well-formed choice payload', () => {
    expect(isCoachChoices(valid)).toBe(true);
  });

  it('rejects wrong type, empty, and malformed options', () => {
    expect(isCoachChoices({ ...valid, type: 'read_clarification' })).toBe(false);
    expect(isCoachChoices({ type: 'coach_choices', options: [] })).toBe(false);
    expect(isCoachChoices({ type: 'coach_choices', options: [{ id: 'c1', label: 'x' }] })).toBe(false);
    expect(isCoachChoices({ type: 'coach_choices', options: [{ id: 'c1', label: '', query: 'q' }] })).toBe(false);
    expect(isCoachChoices(undefined)).toBe(false);
    expect(isCoachChoices({ follow_ups: [] })).toBe(false);
  });

  it('does not mistake a choice payload for a read clarification', () => {
    expect(isCoachReadClarification(valid)).toBe(false);
  });
});
