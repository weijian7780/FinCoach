import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CoachApiError } from '@/lib/coach-api';

import type {
  CoachActionPayload,
  CoachConversation,
  CoachMessage,
  CoachMessagePage,
  CoachReportAttempt,
  CoachTurnResponse,
} from '@/lib/types';

const fixtures = vi.hoisted(() => ({
  params: { sessionId: 'session-a' },
  auth: {} as Record<string, unknown>,
  list: vi.fn(),
  messages: vi.fn(),
  send: vi.fn(),
  create: vi.fn(),
  confirm: vi.fn(),
  cancel: vi.fn(),
  complete: vi.fn(),
  report: vi.fn(),
  feedback: vi.fn(),
  source: vi.fn(),
  attemptStatus: vi.fn(),
  renewAttempt: vi.fn(),
  saveAttempt: vi.fn(),
  loadAttempt: vi.fn(),
  clearAttempt: vi.fn(),
  startHeartbeat: vi.fn(),
  heartbeatStop: vi.fn(),
  nextId: 0,
}));

// Real React state/effects are exercised. Only native views, device APIs and
// remote services are substituted, so these tests need neither a phone nor DOM.
vi.mock('@expo/vector-icons', () => ({ MaterialCommunityIcons: 'Icon' }));
vi.mock('@react-native-community/netinfo', () => ({ default: { addEventListener: () => () => {} } }));
vi.mock('expo-crypto', () => ({ randomUUID: () => `message-${++fixtures.nextId}` }));
vi.mock('expo-router', async () => {
  const React = await import('react');
  return {
    router: {
      setParams: (params: typeof fixtures.params) => { fixtures.params = params; },
      push: vi.fn(),
    },
    useFocusEffect: (effect: () => void | (() => void)) => React.useEffect(effect, [effect]),
    useLocalSearchParams: () => fixtures.params,
  };
});
vi.mock('react-native', () => ({
  ActivityIndicator: 'ActivityIndicator', FlatList: 'FlatList',
  KeyboardAvoidingView: 'KeyboardAvoidingView', ScrollView: 'ScrollView', View: 'View',
}));
vi.mock('react-native-reanimated', () => ({
  default: { View: 'AnimatedView' }, useReducedMotion: () => true,
  FadeIn: {}, FadeInDown: {}, FadeOut: {},
}));
vi.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) }));
vi.mock('@/components/coach/coach-insight-strip', () => ({ CoachInsightStrip: 'CoachInsightStrip' }));
vi.mock('@/components/coach/coach-message', () => ({ CoachMessage: 'CoachMessage', CoachTypingIndicator: 'Typing' }));
vi.mock('@/components/ui/animated-pressable', () => ({ AnimatedPressable: 'Pressable' }));
vi.mock('@/components/ui/app-text', () => ({ AppText: 'Text', AppTextInput: 'TextInput' }));
vi.mock('@/components/ui/consent-selector', () => ({ ConsentSelector: 'ConsentSelector' }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => fixtures.auth }));
vi.mock('@/lib/coach-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/coach-api')>()),
  listCoachConversations: fixtures.list, listCoachMessages: fixtures.messages,
  sendCoachMessage: fixtures.send, createCoachConversation: fixtures.create,
  confirmCoachAction: fixtures.confirm, cancelCoachAction: fixtures.cancel,
  completeCoachAction: fixtures.complete, setCoachMessageFeedback: fixtures.feedback,
  getReportAttempt: fixtures.attemptStatus, renewReportAttempt: fixtures.renewAttempt,
}));
vi.mock('@/lib/coach-actions', () => ({ generateCoachReport: fixtures.report }));
vi.mock('@/lib/report-attempt', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/report-attempt')>();
  return {
    ...actual,
    saveReportAttempt: fixtures.saveAttempt,
    loadReportAttempt: fixtures.loadAttempt,
    clearReportAttempt: fixtures.clearAttempt,
    startReportAttemptHeartbeat: fixtures.startHeartbeat,
  };
});
vi.mock('@/lib/reports', () => ({ fetchReportSourceData: fixtures.source }));
vi.mock('@/lib/savings', () => ({ fetchSavingsGoals: async () => [] }));

import CoachScreen from './coach-screen';

let renderer: ReactTestRenderer;
let owner = 0;

function conversation(id: string): CoachConversation {
  return { id, user_id: `user-${owner}`, title: id, created_at: '2026-10-15T00:00:00Z', updated_at: '2026-10-15T00:00:00Z', last_message_at: '2026-10-15T00:00:00Z' };
}

function message(id: string, sessionId = 'session-a', role: 'user' | 'assistant' = 'assistant'): CoachMessage {
  return {
    id, session_id: sessionId, user_id: `user-${owner}`, role, content: id,
    reply_to_message_id: null, status: 'completed', error_code: null,
    model: null, prompt_tokens: null, completion_tokens: null, feedback: null,
    ui_payload: {}, created_at: '2026-10-15T00:00:00Z', sources: [],
  };
}

function reportMessage(overrides: Partial<CoachMessage> = {}): CoachMessage {
  return {
    ...message('report-message'),
    ui_payload: {
      type: 'action', action_id: 'report-action', action_type: 'generate_report',
      status: 'approved', title: 'October report', description: '',
      arguments: {}, fields: [], confirm_label: 'Generate',
    },
    ...overrides,
  };
}

function executedReport(proposed: CoachMessage): CoachMessage {
  const payload = proposed.ui_payload as CoachActionPayload;
  return { ...proposed, ui_payload: { ...payload, status: 'executed', result: {} } };
}

function attemptFor(
  attemptId: string,
  overrides: Partial<CoachReportAttempt> = {},
): CoachReportAttempt {
  return {
    attempt_id: attemptId,
    message_id: 'report-message',
    action_id: 'report-action',
    status: 'active',
    storage_path: `user-${owner}/coach/${attemptId}.pdf`,
    period: 'current_month',
    report_type: 'monthly',
    start_date: '2026-10-01',
    end_date: '2026-10-31',
    category_id: null,
    category_name: null,
    report_id: null, lease_valid: true, server_time: '2030-01-01T00:00:00Z',
    lease_expires_at: '2030-01-01T00:05:00Z',
    ...overrides,
  };
}

function savedAttempt(attemptId: string) {
  return {
    userId: `user-${owner}`,
    messageId: 'report-message',
    actionId: 'report-action',
    attemptId,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function listProps() {
  return renderer.root.findByType('FlatList' as never).props;
}

async function mount() {
  await act(async () => { renderer = create(<CoachScreen />); });
}

async function compose(content: string) {
  await act(async () => {
    renderer.root.findByProps({ accessibilityLabel: 'Message FinCoach' }).props.onChangeText(content);
  });
}

function sendButton() {
  return renderer.root.findByProps({ accessibilityLabel: 'Send message' });
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  ++owner;
  fixtures.params = { sessionId: 'session-a' };
  fixtures.auth = {
    session: { user: { id: `user-${owner}` } },
    profile: { spending_records_consent: 'granted' }, updateProfile: vi.fn(),
  };
  fixtures.list.mockReset().mockResolvedValue([conversation('session-a'), conversation('session-b')]);
  fixtures.messages.mockReset().mockImplementation(async (id: string) => ({ messages: [message(`${id}-answer`, id)], next_before: null }));
  fixtures.send.mockReset();
  fixtures.create.mockReset().mockResolvedValue(conversation('created'));
  fixtures.confirm.mockReset();
  fixtures.cancel.mockReset();
  fixtures.complete.mockReset();
  fixtures.report.mockReset();
  fixtures.feedback.mockReset();
  fixtures.source.mockReset().mockResolvedValue({ transactions: [], monthlyBudgets: [], savingsGoals: [] });
  fixtures.attemptStatus.mockReset();
  fixtures.renewAttempt.mockReset();
  fixtures.saveAttempt.mockReset().mockResolvedValue(undefined);
  fixtures.loadAttempt.mockReset().mockResolvedValue(null);
  fixtures.clearAttempt.mockReset().mockResolvedValue(undefined);
  fixtures.startHeartbeat.mockReset().mockImplementation(() => ({ stop: fixtures.heartbeatStop }));
  fixtures.heartbeatStop.mockReset();
});

afterEach(async () => {
  if (renderer) await act(async () => { renderer.unmount(); });
});

function headerTitle() {
  return renderer.root.findAllByType('Text' as never)
    .find((node) => node.props.numberOfLines === 1)!.props.children;
}

describe('opening a saved chat', () => {
  it('shows its messages without waiting for the conversation list', async () => {
    const list = deferred<CoachConversation[]>();
    fixtures.list.mockReturnValue(list.promise);
    await mount();
    expect(fixtures.messages).toHaveBeenCalledWith('session-a', { limit: 30 });
    expect(listProps().data.map((item: CoachMessage) => item.id)).toEqual(['session-a-answer']);
    expect(headerTitle()).toBe('FinCoach');
    await act(async () => { list.resolve([conversation('session-a')]); });
    expect(headerTitle()).toBe('session-a');
  });

  it('still shows messages when the conversation list fails', async () => {
    fixtures.list.mockRejectedValue(new Error('list down'));
    await mount();
    expect(listProps().data.map((item: CoachMessage) => item.id)).toEqual(['session-a-answer']);
  });

  it('opens a chat deleted elsewhere as an empty draft', async () => {
    fixtures.messages.mockRejectedValue(new CoachApiError(404, 'Conversation not found.'));
    await mount();
    expect(listProps().data).toEqual([]);
    expect(renderer.root.findAllByProps({ children: 'Coach unavailable' })).toHaveLength(0);
  });

  it('never shows a previous chat page that arrives after switching', async () => {
    const first = deferred<CoachMessagePage>();
    fixtures.messages.mockImplementation(async (id: string) => (
      id === 'session-a' ? first.promise : { messages: [message(`${id}-answer`, id)], next_before: null }
    ));
    await mount();
    await act(async () => {
      fixtures.params = { sessionId: 'session-b' };
      renderer.update(<CoachScreen />);
    });
    await act(async () => { first.resolve({ messages: [message('session-a-answer')], next_before: null }); });
    expect(listProps().data.map((item: CoachMessage) => item.id)).toEqual(['session-b-answer']);
  });
});

describe('coaching screen asynchronous behavior', () => {
  it('submits one turn when send is pressed twice before React renders', async () => {
    const pending = deferred<CoachTurnResponse>();
    fixtures.send.mockReturnValue(pending.promise);
    await mount();
    await compose('Explain emergency savings');
    await act(async () => {
      const press = sendButton().props.onPress;
      press();
      press();
    });
    expect(fixtures.send).toHaveBeenCalledTimes(1);
    expect(listProps().data.filter((item: CoachMessage) => item.role === 'user')).toHaveLength(1);
  });

  it('does not put a late reply into a newly opened chat', async () => {
    const pending = deferred<CoachTurnResponse>();
    fixtures.send.mockReturnValue(pending.promise);
    await mount();
    await compose('Explain emergency savings');
    await act(async () => { sendButton().props.onPress(); });
    const messageId = fixtures.send.mock.calls[0][1] as string;
    await act(async () => {
      renderer.root.findByProps({ accessibilityLabel: 'New conversation' }).props.onPress();
      renderer.update(<CoachScreen />);
    });
    await act(async () => {
      pending.resolve({ user_message: message(messageId, 'session-a', 'user'), assistant_message: message('old-reply'), sources: [] });
    });
    expect(listProps().data).toEqual([]);
    await compose('A fresh question');
    expect(sendButton().props.disabled).toBe(false);
  });

  it('discards older-message pages after changing conversations', async () => {
    const pending = deferred<CoachMessagePage>();
    fixtures.messages.mockImplementation(async (id: string, options: { before?: string }) => options.before
      ? pending.promise
      : { messages: [message(`${id}-answer`, id)], next_before: 'older-cursor' });
    await mount();
    await act(async () => { listProps().onScroll({ nativeEvent: { contentOffset: { y: 0 } } }); });
    await act(async () => {
      fixtures.params = { sessionId: 'session-b' };
      renderer.update(<CoachScreen />);
    });
    await act(async () => { pending.resolve({ messages: [message('old-page')], next_before: null }); });
    expect(listProps().data.map((item: CoachMessage) => item.id)).toEqual(['session-b-answer']);
  });

  it('retries the original clarification payload with the original message id', async () => {
    fixtures.send.mockRejectedValue(new Error('response lost'));
    await mount();
    const reply = { assistant_message_id: 'session-a-answer', value: '2026-10-16' };
    await act(async () => {
      listProps().renderItem({ item: message('session-a-answer') }).props.onFollowUp('Tomorrow', reply);
    });
    const originalId = fixtures.send.mock.calls[0][1];
    await act(async () => {
      const retry = renderer.root.findAllByType('Pressable' as never)
        .find((node) => node.findAllByType('Text' as never).some((child) => child.props.children === 'Retry'));
      retry!.props.onPress();
    });
    expect(fixtures.send.mock.calls[1].slice(0, 4)).toEqual(['session-a', originalId, 'Tomorrow', reply]);
  });

  it('creates one conversation and keeps the reply when a draft receives its saved id', async () => {
    fixtures.params = { sessionId: 'new' };
    fixtures.send.mockImplementation(async (id: string, messageId: string) => ({
      user_message: message(messageId, id, 'user'), assistant_message: message('new-answer', id), sources: [],
    }));
    await mount();
    await compose('Explain emergency savings');
    await act(async () => { sendButton().props.onPress(); });
    expect(fixtures.create).toHaveBeenCalledTimes(1);
    expect(fixtures.send.mock.calls[0][0]).toBe('created');
    expect(listProps().data.some((item: CoachMessage) => item.id === 'new-answer')).toBe(true);
  });

  it('submits one confirmation when confirm is pressed twice before rendering', async () => {
    const pending = deferred<unknown>();
    fixtures.confirm.mockReturnValue(pending.promise);
    await mount();
    const proposed = {
      ...message('action-message'), ui_payload: {
        type: 'action', action_id: 'action-1', action_type: 'create_reminder', status: 'pending',
        title: 'Pay rent', description: 'Review reminder', arguments: {}, fields: [], confirm_label: 'Confirm',
      },
    };
    await act(async () => {
      const press = listProps().renderItem({ item: proposed }).props.onActionConfirm;
      void press(proposed);
      void press(proposed);
    });
    expect(fixtures.confirm).toHaveBeenCalledTimes(1);
  });

  it('does not carry Change details text into a different conversation', async () => {
    const pending = deferred<{ message: CoachMessage }>();
    fixtures.cancel.mockReturnValue(pending.promise);
    await mount();
    const proposed = {
      ...message('action-message'), ui_payload: {
        type: 'action' as const, action_id: 'action-1', action_type: 'create_reminder' as const,
        status: 'pending' as const, title: 'Rent', description: '', arguments: {},
        fields: [{ label: 'Title', value: 'Rent' }], confirm_label: 'Confirm',
      },
    };
    await act(async () => { void listProps().renderItem({ item: proposed }).props.onActionChange(proposed); });
    await act(async () => {
      fixtures.params = { sessionId: 'session-b' };
      renderer.update(<CoachScreen />);
    });
    await act(async () => { pending.resolve({ message: proposed }); });
    expect(renderer.root.findByProps({ accessibilityLabel: 'Message FinCoach' }).props.value).toBe('');
  });

  it('restores an already completed reply after a send response was lost', async () => {
    fixtures.send.mockRejectedValue(new Error('response lost'));
    await mount();
    await compose('Explain emergency savings');
    await act(async () => { sendButton().props.onPress(); });
    const messageId = fixtures.send.mock.calls[0][1] as string;
    fixtures.messages.mockResolvedValue({
      messages: [message(messageId, 'session-a', 'user'), { ...message('recovered'), reply_to_message_id: messageId }],
      next_before: null,
    });
    await act(async () => {
      // Token refresh changes the session object and reruns the focused refresh.
      fixtures.auth = { ...fixtures.auth, session: { user: { id: `user-${owner}` }, access_token: 'refreshed' } };
      renderer.update(<CoachScreen />);
    });
    expect(listProps().data.map((item: CoachMessage) => item.id)).toEqual([messageId, 'recovered']);
    expect(renderer.root.findAllByProps({ accessibilityRole: 'alert' })).toHaveLength(0);
    expect(fixtures.send).toHaveBeenCalledTimes(1);
  });

  it('retries a lost report completion without regenerating or marking the PDF failed', async () => {
    const proposed = reportMessage();
    const attempt = attemptFor('attempt-42');
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('attempt-42'));
    fixtures.attemptStatus.mockResolvedValue(attempt);
    fixtures.confirm.mockResolvedValue({
      message: proposed,
      effect: { type: 'generate_report', arguments: {}, attempt },
    });
    fixtures.report.mockResolvedValue({
      title: 'October report',
      fileName: 'FinCoach_October_2026.pdf',
      generatedAt: '2026-10-16T00:00:00.000Z',
      storagePath: attempt.storage_path,
    });
    fixtures.complete.mockRejectedValueOnce(new Error('completion response lost'))
      .mockResolvedValue({ message: executedReport(proposed) });
    fixtures.attemptStatus.mockResolvedValue(attempt);
    fixtures.renewAttempt.mockResolvedValue(attempt);
    fixtures.saveAttempt.mockImplementation(async (record: ReturnType<typeof savedAttempt>) => {
      fixtures.loadAttempt.mockResolvedValue(record);
    });
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });
    expect(fixtures.complete.mock.calls.map((call) => call[2])).toEqual([true]);
    expect(fixtures.heartbeatStop).toHaveBeenCalledTimes(1);

    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });
    // Retry reacquires the exact saved lease before completing again.
    expect(fixtures.confirm).toHaveBeenCalledTimes(2);
    expect(fixtures.attemptStatus).toHaveBeenCalledWith('report-message', 'attempt-42');
    // The already-rendered PDF was never regenerated or overwritten.
    expect(fixtures.report).toHaveBeenCalledTimes(1);
    expect(fixtures.complete.mock.calls.map((call) => [call[2], call[4]]))
      .toEqual([[true, 'attempt-42'], [true, 'attempt-42']]);
    expect(fixtures.complete.mock.calls[0][3]).toEqual({
      title: 'October report',
      file_name: 'FinCoach_October_2026.pdf',
      generated_at: '2026-10-16T00:00:00.000Z',
    });
    expect(fixtures.clearAttempt).toHaveBeenCalledWith(
      `user-${owner}`, 'report-message', 'report-action',
    );
  });

  it('reacquires the expired uploaded attempt after an app restart before rendering', async () => {
    const proposed = reportMessage();
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('expired-upload'));
    fixtures.attemptStatus.mockResolvedValue(attemptFor('expired-upload', {
      lease_valid: false, server_time: '2030-01-01T00:06:00Z', lease_expires_at: '2030-01-01T00:05:00Z',
    }));
    fixtures.confirm.mockResolvedValue({ message: proposed,
      effect: { type: 'generate_report', arguments: {}, attempt: attemptFor('expired-upload') } });
    fixtures.report.mockResolvedValue({ title: 'Resumed', fileName: 'resumed.pdf', generatedAt: '2030-01-01T00:00:00Z' });
    fixtures.complete.mockResolvedValue({ message: executedReport(proposed) });
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });
    expect(fixtures.confirm).toHaveBeenCalledWith('report-message', 'report-action', 'expired-upload');
    expect(fixtures.confirm.mock.invocationCallOrder[0]).toBeLessThan(fixtures.report.mock.invocationCallOrder[0]);
    expect(fixtures.complete.mock.calls[0][4]).toBe('expired-upload');
  });

  it('never renders a competing device claim or sends a failed completion for it', async () => {
    const proposed = reportMessage();
    fixtures.confirm.mockRejectedValue(new CoachApiError(409, 'Already generating', 'action_in_progress'));
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });
    expect(fixtures.report).not.toHaveBeenCalled();
    expect(fixtures.complete).not.toHaveBeenCalled();
  });

  it('stops completion if its heartbeat loses the lease during rendering', async () => {
    const proposed = reportMessage();
    fixtures.confirm.mockImplementation(async (_m: string, _a: string, id: string) => ({
      message: proposed, effect: { type: 'generate_report', arguments: {}, attempt: attemptFor(id) },
    }));
    fixtures.report.mockImplementation(async () => {
      fixtures.startHeartbeat.mock.calls[0][0].onLost();
      return { title: 'Late', fileName: 'late.pdf', generatedAt: '2030-01-01T00:00:00Z' };
    });
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });
    expect(fixtures.complete).not.toHaveBeenCalled();
    expect(fixtures.clearAttempt).not.toHaveBeenCalled();
    expect(fixtures.heartbeatStop).toHaveBeenCalledTimes(1);
  });

  it('persists before confirming and renders only that exact server attempt', async () => {
    const proposed = reportMessage();
    fixtures.confirm.mockImplementation(async (_m: string, _a: string, id: string) => ({
      message: proposed, effect: { type: 'generate_report', arguments: {}, attempt: attemptFor(id) },
    }));
    fixtures.report.mockResolvedValue({ title: 'October report', fileName: 'report.pdf',
      generatedAt: '2030-01-01T00:00:00Z' });
    fixtures.complete.mockResolvedValue({ message: executedReport(proposed) });
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });
    const planned = fixtures.saveAttempt.mock.calls[0][0];
    expect(fixtures.saveAttempt.mock.invocationCallOrder[0]).toBeLessThan(fixtures.confirm.mock.invocationCallOrder[0]);
    expect(fixtures.report).toHaveBeenCalledWith(`user-${owner}`, attemptFor(planned.attemptId), undefined, expect.any(Function));
    expect(fixtures.startHeartbeat).toHaveBeenCalledTimes(1);
    expect(fixtures.heartbeatStop).toHaveBeenCalledTimes(1);
  });

  it('reconciles a lost confirmation instead of starting a second attempt', async () => {
    const proposed = reportMessage();
    fixtures.confirm.mockRejectedValue(new Error('response lost'));
    fixtures.attemptStatus.mockImplementation(
      async (_messageId: string, attemptId: string) => attemptFor(attemptId),
    );
    fixtures.report.mockImplementation(
      async (_userId: string, target: CoachReportAttempt) => ({
        title: 'October report',
        fileName: 'FinCoach_October_2026.pdf',
        generatedAt: '2026-10-16T00:00:00.000Z',
        storagePath: target.storage_path,
      }),
    );
    fixtures.complete.mockResolvedValue({ message: executedReport(proposed) });
    fixtures.renewAttempt.mockResolvedValue(attemptFor('attempt'));
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });

    const plannedId = fixtures.saveAttempt.mock.calls[0][0].attemptId as string;
    expect(fixtures.confirm).toHaveBeenCalledTimes(1);
    expect(fixtures.attemptStatus).toHaveBeenCalledWith('report-message', plannedId);
    // The server reused the reserved id, so the record is not rewritten.
    expect(fixtures.saveAttempt).toHaveBeenCalledTimes(1);
    expect(fixtures.report).toHaveBeenCalledWith(`user-${owner}`, attemptFor(plannedId), undefined, expect.any(Function));
    expect(fixtures.complete.mock.calls[0][4]).toBe(plannedId);
  });

  it('shows a completed report as executed when mounting after a lost response', async () => {
    const proposed = reportMessage();
    fixtures.messages.mockResolvedValue({ messages: [proposed], next_before: null });
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('attempt-9'));
    fixtures.attemptStatus.mockResolvedValue(
      attemptFor('attempt-9', { status: 'completed', report_id: 77 }),
    );
    await mount();
    await act(async () => {});

    const rendered = listProps().data[0] as CoachMessage;
    expect(rendered.ui_payload).toMatchObject({
      status: 'executed',
      result: {
        report_id: 77,
        storage_path: `user-${owner}/coach/attempt-9.pdf`,
      },
    });
    // The published report was never regenerated by a second attempt.
    expect(fixtures.confirm).not.toHaveBeenCalled();
    expect(fixtures.report).not.toHaveBeenCalled();
    expect(fixtures.clearAttempt).toHaveBeenCalledWith(
      `user-${owner}`, 'report-message', 'report-action',
    );
  });

  it('keeps the persisted attempt when the server cannot be reached for reconciliation', async () => {
    const proposed = reportMessage();
    fixtures.confirm.mockRejectedValue(new Error('offline'));
    fixtures.attemptStatus.mockRejectedValue(new Error('offline'));
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });

    expect(fixtures.clearAttempt).not.toHaveBeenCalled();
    expect(fixtures.report).not.toHaveBeenCalled();
    expect(renderer.root.findAllByProps({ accessibilityRole: 'alert' }).length)
      .toBeGreaterThan(0);
  });

  it('does not start a second attempt while a persisted reservation is unverifiable', async () => {
    const proposed = reportMessage();
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('attempt-8'));
    fixtures.attemptStatus.mockRejectedValue(new Error('offline'));
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });

    expect(fixtures.confirm).not.toHaveBeenCalled();
    expect(fixtures.saveAttempt).not.toHaveBeenCalled();
    expect(fixtures.clearAttempt).not.toHaveBeenCalled();
    expect(fixtures.report).not.toHaveBeenCalled();
  });

  it('discards the persisted attempt when a report is cancelled', async () => {
    const proposed = reportMessage();
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('attempt-3'));
    fixtures.cancel.mockResolvedValue({
      message: {
        ...proposed,
        ui_payload: { ...(proposed.ui_payload as object), status: 'cancelled' },
      },
    });
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionCancel(proposed); });

    expect(fixtures.cancel).toHaveBeenCalledWith('report-message', 'report-action');
    expect(fixtures.clearAttempt).toHaveBeenCalledWith(
      `user-${owner}`, 'report-message', 'report-action',
    );
  });

  it('records a failed generation before discarding the reserved attempt', async () => {
    const proposed = reportMessage();
    const attempt = attemptFor('attempt-5');
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('attempt-5'));
    fixtures.attemptStatus.mockResolvedValue(attempt);
    fixtures.confirm.mockResolvedValue({
      message: proposed,
      effect: { type: 'generate_report', arguments: {}, attempt },
    });
    fixtures.report.mockRejectedValue(new Error('PDF engine failed'));
    fixtures.complete.mockResolvedValue({
      message: {
        ...proposed,
        ui_payload: { ...(proposed.ui_payload as object), status: 'failed' },
      },
    });
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });

    expect(fixtures.complete.mock.calls[0][2]).toBe(false);
    expect(fixtures.complete.mock.calls[0][4]).toBe('attempt-5');
    expect(fixtures.clearAttempt).toHaveBeenCalledWith(
      `user-${owner}`, 'report-message', 'report-action',
    );
  });

  it('keeps the local attempt when the failed generation could not be recorded', async () => {
    const proposed = reportMessage();
    const attempt = attemptFor('attempt-6');
    fixtures.loadAttempt.mockResolvedValue(savedAttempt('attempt-6'));
    fixtures.attemptStatus.mockResolvedValue(attempt);
    fixtures.confirm.mockResolvedValue({
      message: proposed,
      effect: { type: 'generate_report', arguments: {}, attempt },
    });
    fixtures.report.mockRejectedValue(new Error('PDF engine failed'));
    fixtures.complete.mockRejectedValue(new Error('offline'));
    await mount();
    await act(async () => { await listProps().renderItem({ item: proposed }).props.onActionConfirm(proposed); });

    expect(fixtures.clearAttempt).not.toHaveBeenCalled();
  });

  it('discards spending insights that arrive after spending consent was withdrawn', async () => {
    const pending = deferred<unknown>();
    fixtures.source.mockReturnValue(pending.promise);
    await mount();
    await act(async () => {
      fixtures.auth = { ...fixtures.auth, profile: { spending_records_consent: 'withdrawn' } };
      renderer.update(<CoachScreen />);
    });
    await act(async () => {
      pending.resolve({ transactions: [], savingsGoals: [], monthlyBudgets: [{ limit_amount: 500 }] });
    });
    // The empty-state subtree is supplied to FlatList as an element. It still
    // receives current insight props even when this conversation is nonempty.
    const empty = listProps().ListEmptyComponent;
    const strip = empty.props.children.find((child: { type: string }) => child.type === 'CoachInsightStrip');
    expect(strip.props.cards).toEqual([]);
  });

  it.each(['granted', 'denied'])('keeps the selected clarification after consent is %s', async (consent) => {
    fixtures.auth = {
      ...fixtures.auth, profile: { spending_records_consent: 'unset' },
      updateProfile: async () => ({ ok: true }),
    };
    fixtures.send.mockRejectedValue(new Error('controlled end'));
    await mount();
    const reply = { assistant_message_id: 'session-a-answer', value: 'monthly_report' };
    await act(async () => {
      listProps().renderItem({ item: message('session-a-answer') }).props.onFollowUp('Monthly report', reply);
    });
    expect(fixtures.send).not.toHaveBeenCalled();
    await act(async () => {
      renderer.root.findByType('ConsentSelector' as never).props.onChange(consent);
    });
    expect(fixtures.send.mock.calls[0].slice(2, 4)).toEqual(['Monthly report', reply]);
  });

  it('does not submit a queued question into a different chat after consent saves', async () => {
    const pending = deferred<{ ok: true }>();
    const updateProfile = vi.fn().mockReturnValue(pending.promise);
    fixtures.auth = { ...fixtures.auth, profile: { spending_records_consent: 'unset' }, updateProfile };
    await mount();
    await compose('Monthly report');
    await act(async () => { sendButton().props.onPress(); });
    await act(async () => {
      const save = renderer.root.findByType('ConsentSelector' as never).props.onChange;
      save('granted');
      save('granted');
    });
    expect(updateProfile).toHaveBeenCalledTimes(1);
    await act(async () => {
      fixtures.params = { sessionId: 'session-b' };
      renderer.update(<CoachScreen />);
    });
    await act(async () => { pending.resolve({ ok: true }); });
    expect(fixtures.send).not.toHaveBeenCalled();
    expect(renderer.root.findByProps({ accessibilityLabel: 'Message FinCoach' }).props.value).toBe('');
  });
});
