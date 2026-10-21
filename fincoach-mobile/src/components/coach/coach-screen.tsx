import { MaterialCommunityIcons } from '@expo/vector-icons';
import NetInfo from '@react-native-community/netinfo';
import { randomUUID } from 'expo-crypto';
import { router, useFocusEffect, useLocalSearchParams, type Href } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentRef } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  ScrollView,
  View,
} from 'react-native';
import Animated, {
  FadeIn,
  FadeInDown,
  FadeOut,
  useReducedMotion,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CoachInsightStrip } from '@/components/coach/coach-insight-strip';
import { CoachMessage, CoachTypingIndicator } from '@/components/coach/coach-message';
import { AnimatedPressable } from '@/components/ui/animated-pressable';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { ConsentSelector } from '@/components/ui/consent-selector';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import {
  CoachApiError,
  cancelCoachAction,
  completeCoachAction,
  confirmCoachAction,
  createCoachConversation,
  getReportAttempt,
  listCoachConversations,
  listCoachMessages,
  renewReportAttempt,
  sendCoachMessage,
  setCoachMessageFeedback,
} from '@/lib/coach-api';
import {
  generateCoachReport,
  type GeneratedCoachReport,
} from '@/lib/coach-actions';
import { isCoachAction } from '@/lib/coach-agent';
import {
  canSendCoachMessage,
  coachErrorMessage,
  getCoachFollowUpChips,
  mergeTurn,
  shouldRequestSpendingConsent,
  shouldShowCoachSuggestions,
  sortConversations,
  type CoachFollowUpChip,
} from '@/lib/coach-domain';
import { buildCoachInsightCards, type CoachInsightCard } from '@/lib/coach-insights';
import { coachMotion } from '@/lib/coach-motion';
import { PROVIDER_CONSENT_VERSION } from '@/lib/coach-provider-consent';
import {
  nextCoachSendState,
  scheduleCoachPendingNotice,
  type CoachFeedback,
  type CoachSendState,
} from '@/lib/coach-ui';
import { createPresetSelection } from '@/lib/report-domain';
import {
  clearReportAttempt,
  loadReportAttempt,
  parseReportAttempt,
  reconcileReportAttempt,
  saveReportAttempt,
  startReportAttemptHeartbeat,
  type ReportAttemptHeartbeat,
} from '@/lib/report-attempt';
import { fetchReportSourceData } from '@/lib/reports';
import { fetchSavingsGoals } from '@/lib/savings';
import type {
  CoachActionPayload,
  CoachConversation,
  CoachInteractionReply,
  CoachMessage as CoachMessageType,
  CoachMessagePage,
  CoachReportAttempt,
} from '@/lib/types';

const SUGGESTIONS = [
  'How am I doing?',
  'Where can I cut spending?',
  'Am I on track for my goal?',
  'Help me save RM50',
] as const;

const COACH_MESSAGE_PAGE_SIZE = 30;

// Hoisted so the list receives the same references on every render; inline
// objects and arrow functions here would re-create list props while typing.
const coachMessageKeyExtractor = (item: CoachMessageType) => item.id;

const coachListContentStyle = {
  paddingHorizontal: 16,
  paddingTop: 16,
  paddingBottom: 18,
  gap: 12,
  flexGrow: 1,
} as const;

// Memory-only cache: it speeds up tab switching without persisting private chats
// to device storage. Every entry is scoped to its owner before it is read back.
const conversationCache = new Map<string, CoachConversation[]>();
const messagePageCache = new Map<string, CoachMessagePage>();
// A rendered PDF is kept by attempt id so a lost completion response is retried
// without regenerating or overwriting the immutable per-attempt file.
const pendingReportCompletions = new Map<string, GeneratedCoachReport>();

async function discardSavedReportAttempt(ownerId: string, messageId: string, actionId: string) {
  const saved = await loadReportAttempt(ownerId, messageId, actionId).catch(() => null);
  if (saved) pendingReportCompletions.delete(`${ownerId}:${saved.attemptId}`);
  await clearReportAttempt(ownerId, messageId, actionId).catch(() => {});
}

function cacheKey(userId: string, sessionId: string) {
  return `${userId}:${sessionId}`;
}

function readCachedConversations(userId: string) {
  return conversationCache.get(userId) ?? null;
}

function writeCachedConversations(userId: string, conversations: CoachConversation[]) {
  conversationCache.set(userId, conversations);
}

function readCachedMessagePage(userId: string, sessionId: string) {
  return messagePageCache.get(cacheKey(userId, sessionId)) ?? null;
}

function writeCachedMessagePage(userId: string, sessionId: string, page: CoachMessagePage) {
  messagePageCache.set(cacheKey(userId, sessionId), page);
}

function prependOlderMessages(
  olderMessages: CoachMessageType[],
  currentMessages: CoachMessageType[],
) {
  const existingIds = new Set(currentMessages.map((message) => message.id));
  return [
    ...olderMessages.filter((message) => !existingIds.has(message.id)),
    ...currentMessages,
  ];
}

export default function CoachScreen() {
  const insets = useSafeAreaInsets();
  const reduceMotion = useReducedMotion();
  const { profile, session, updateProfile } = useAuth();
  const params = useLocalSearchParams<{ sessionId?: string }>();
  const listRef = useRef<FlatList<CoachMessageType>>(null);
  const inputRef = useRef<ComponentRef<typeof TextInput>>(null);
  const [conversation, setConversation] = useState<CoachConversation | null>(null);
  const [messages, setMessages] = useState<CoachMessageType[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendState, setSendState] = useState<CoachSendState>({ status: 'idle' });
  const [isOnline, setIsOnline] = useState(true);
  const [insights, setInsights] = useState<CoachInsightCard[]>([]);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [consentSaving, setConsentSaving] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [pendingConsentQuestion, setPendingConsentQuestion] = useState<{
    content: string;
    messageId?: string;
    interactionReply?: CoachInteractionReply;
  } | null>(null);
  const [activeActionMessageId, setActiveActionMessageId] = useState<string | null>(null);
  const isSending = sendState.status === 'sending';
  const [longWait, setLongWait] = useState(false);
  const pendingMessageId = sendState.status === 'sending' ? sendState.messageId : null;
  useEffect(() => {
    setLongWait(false);
    if (!isSending) return;
    // Completion, retry and unmount cancel this attempt's pending notice.
    return scheduleCoachPendingNotice(setLongWait);
  }, [isSending, pendingMessageId]);
  const userId = session?.user.id;
  const loadSequence = useRef(0);
  const insightSequence = useRef(0);
  const shouldScrollToLatest = useRef(true);
  const sendStateRef = useRef<CoachSendState>({ status: 'idle' });
  const olderRequestRef = useRef<object | null>(null);
  const actionRequestRef = useRef<object | null>(null);
  const consentRequestRef = useRef<object | null>(null);
  const reconcileAttemptsRef = useRef<(items: CoachMessageType[], scope: object) => void>(() => {});
  // Async results belong to the owner and conversation that started them. A
  // route change invalidates that ownership even before its loading effect runs.
  const scopeKey = `${userId ?? ''}:${params.sessionId ?? ''}`;
  const scopeRef = useRef({ key: scopeKey, generation: 0 });
  if (scopeRef.current.key !== scopeKey) {
    scopeRef.current = { key: scopeKey, generation: scopeRef.current.generation + 1 };
  }
  const scopeGeneration = scopeRef.current.generation;
  const updateSendState = useCallback((value: CoachSendState) => {
    // The ref is a synchronous lock: two presses can precede React's next render.
    sendStateRef.current = value;
    setSendState(value);
  }, []);
  useEffect(() => {
    ++loadSequence.current;
    olderRequestRef.current = null;
    actionRequestRef.current = null;
    consentRequestRef.current = null;
    setConsentSaving(false);
    setConsentError(null);
    updateSendState({ status: 'idle' });
    setActiveActionMessageId(null);
    setLoadingOlderMessages(false);
    setSendError(null);
    setInput('');
    setPendingConsentQuestion(null);
  }, [scopeGeneration, updateSendState]);
  useEffect(() => () => {
    scopeRef.current = { ...scopeRef.current, generation: scopeRef.current.generation + 1 };
    ++loadSequence.current;
  }, []);
  const networkWasOfflineRef = useRef(false);
  const includeRecordedSpending = profile?.spending_records_consent === 'granted';
  const insightContextRef = useRef({ userId, includeRecordedSpending });
  insightContextRef.current = { userId, includeRecordedSpending };
  useEffect(() => { setInsights([]); }, [userId, includeRecordedSpending]);
  // The composer keeps the draft in state so the input stays controlled, but
  // reading it back through a ref keeps `send` (and therefore every row's props)
  // stable while typing. Without this, each keystroke rebuilt the callbacks and
  // forced the whole message list to re-render.
  const draftRef = useRef(input);
  useEffect(() => {
    draftRef.current = input;
  }, [input]);
  const load = useCallback(async () => {
    const scope = scopeRef.current;
    const requestId = ++loadSequence.current;
    if (!session) {
      setConversation(null);
      setMessages([]);
      setNextBefore(null);
      setLoading(false);
      setLoadError('Sign in to use your financial coach.');
      return;
    }
    if (sendStateRef.current.status === 'sending') return;
    const ownerId = session.user.id;

    // A draft conversation has no server-side data yet. Showing the empty chat
    // immediately avoids an unnecessary round trip every time New Chat is pressed.
    if (params.sessionId === 'new') {
      shouldScrollToLatest.current = true;
      setConversation(null);
      setMessages([]);
      setNextBefore(null);
      setLoading(false);
      setLoadError(null);
      return;
    }

    const selectConversation = (items: CoachConversation[]) => (
      params.sessionId
        ? items.find((item) => item.id === params.sessionId) ?? null
        : items[0] ?? null
    );
    const cachedConversations = readCachedConversations(ownerId);
    const cachedConversation = cachedConversations
      ? selectConversation(cachedConversations)
      : null;
    const cachedPage = cachedConversation
      ? readCachedMessagePage(ownerId, cachedConversation.id)
      : null;
    const hasCachedPage = Boolean(cachedConversation && cachedPage);
    if (cachedConversation && cachedPage) {
      shouldScrollToLatest.current = true;
      setConversation(cachedConversation);
      setMessages(cachedPage.messages);
      setNextBefore(cachedPage.next_before);
      setLoading(false);
    } else {
      setLoading(true);
    }
    setLoadError(null);
    try {
      const saved = sortConversations(await listCoachConversations());
      if (requestId !== loadSequence.current || scope !== scopeRef.current) return;
      writeCachedConversations(ownerId, saved);
      const selected = selectConversation(saved);
      if (!selected) {
        setConversation(null);
        setMessages([]);
        setNextBefore(null);
      } else {
        setConversation(selected);
        // Keep cached messages visible, then refresh them in the background so a
        // second device or a later reply is not hidden behind stale local state.
        const page = await listCoachMessages(selected.id, { limit: COACH_MESSAGE_PAGE_SIZE });
        if (requestId !== loadSequence.current || scope !== scopeRef.current) return;
        writeCachedMessagePage(ownerId, selected.id, page);
        shouldScrollToLatest.current = true;
        setMessages(page.messages);
        reconcileAttemptsRef.current(page.messages, scope);
        const activeSend = sendStateRef.current;
        const recoveredReply =
          activeSend.status === 'failed' &&
          page.messages.some(
            (message) =>
              message.role === 'assistant' &&
              message.reply_to_message_id === activeSend.messageId,
          );
        if (recoveredReply) {
          setSendError(null);
          updateSendState({ status: 'idle' });
        }
        setNextBefore(page.next_before);
      }
    } catch (error) {
      if (requestId === loadSequence.current && scope === scopeRef.current && !hasCachedPage) {
        setLoadError(coachErrorMessage(error));
      }
    } finally {
      if (requestId === loadSequence.current && scope === scopeRef.current) {
        setLoading(false);
      }
    }
  }, [params.sessionId, session, updateSendState]);

  useEffect(() => {
    return NetInfo.addEventListener((network) => {
      const online =
        network.isConnected !== false && network.isInternetReachable !== false;
      const wasOffline = networkWasOfflineRef.current;

      setIsOnline(online);
      networkWasOfflineRef.current = !online;

      if (online && wasOffline) {
        void load();
      }
    });
  }, [load]);

  const loadInsights = useCallback(async () => {
    const contextMatches = () => userId === insightContextRef.current.userId
      && includeRecordedSpending === insightContextRef.current.includeRecordedSpending;
    if (!contextMatches()) return;
    const requestId = ++insightSequence.current;
    const scope = scopeRef.current;
    const isCurrent = () => contextMatches() && requestId === insightSequence.current && scope === scopeRef.current;
    if (!userId) {
      setInsights([]);
      setInsightsLoading(false);
      return;
    }

    setInsightsLoading(true);
    try {
      if (includeRecordedSpending) {
        const selection = createPresetSelection('current_month');
        const source = await fetchReportSourceData(userId, selection);
        if (!isCurrent()) return;
        setInsights(buildCoachInsightCards({
          includeRecordedSpending,
          monthlyBudget: source.monthlyBudgets[0] ?? null,
          transactions: source.transactions,
          savingsGoals: source.savingsGoals,
        }));
      } else {
        const savingsGoals = await fetchSavingsGoals(userId);
        if (!isCurrent()) return;
        setInsights(buildCoachInsightCards({
          includeRecordedSpending,
          monthlyBudget: null,
          transactions: [],
          savingsGoals,
        }));
      }
    } catch {
      // Insight cards are supplemental. Conversation access remains available if
      // a finance table is temporarily unavailable.
      if (isCurrent()) setInsights([]);
    } finally {
      if (isCurrent()) setInsightsLoading(false);
    }
  }, [includeRecordedSpending, userId]);

  useFocusEffect(useCallback(() => {
    void (async () => {
      await load();
      void loadInsights();
    })();
  }, [load, loadInsights]));

  const ensureConversation = useCallback(async () => {
    if (conversation) return conversation;
    const scope = scopeRef.current;
    const created = await createCoachConversation();
    if (scope !== scopeRef.current) return created;
    setConversation(created);
    if (userId) {
      const cached = readCachedConversations(userId) ?? [];
      writeCachedConversations(userId, sortConversations([created, ...cached]));
    }
    return created;
  }, [conversation, userId]);

  const loadOlderMessages = useCallback(async () => {
    if (!conversation || !nextBefore || olderRequestRef.current || isSending) return;
    const scope = scopeRef.current;
    const request = {};
    olderRequestRef.current = request;
    setLoadingOlderMessages(true);
    shouldScrollToLatest.current = false;
    try {
      const page = await listCoachMessages(conversation.id, {
        limit: COACH_MESSAGE_PAGE_SIZE,
        before: nextBefore,
      });
      if (scope !== scopeRef.current || olderRequestRef.current !== request) return;
      setMessages((current) => {
        const merged = prependOlderMessages(page.messages, current);
        if (userId) {
          writeCachedMessagePage(userId, conversation.id, {
            messages: merged,
            next_before: page.next_before,
          });
        }
        return merged;
      });
      setNextBefore(page.next_before);
    } catch (error) {
      if (scope === scopeRef.current) setSendError(coachErrorMessage(error));
    } finally {
      if (olderRequestRef.current === request) {
        olderRequestRef.current = null;
        setLoadingOlderMessages(false);
      }
    }
  }, [conversation, isSending, loadingOlderMessages, nextBefore, userId]);

  const send = useCallback(async (
    rawContent?: string,
    retryMessageId?: string,
    consentDecisionHandled = false,
    interactionReply?: CoachInteractionReply,
  ) => {
    const content = (rawContent ?? draftRef.current).trim();
    if (!canSendCoachMessage(content, sendStateRef.current.status === 'sending' || loading)
      || actionRequestRef.current || !session) return;
    const scope = scopeRef.current;
    if (
      !consentDecisionHandled
      && profile
      && shouldRequestSpendingConsent(content, profile.spending_records_consent)
    ) {
      // Consent pauses the whole request, including its structured choice and
      // retry ID. Reconstructing it from visible text changes its meaning.
      setPendingConsentQuestion({ content, messageId: retryMessageId, interactionReply });
      setConsentError(null);
      setInput(content);
      return;
    }
    const messageId = retryMessageId ?? randomUUID();

    if (!isOnline) {
      setSendError('No internet connection. Your message has not been sent.');
      updateSendState({ status: 'failed', content, messageId, interactionReply });
      return;
    }

    shouldScrollToLatest.current = true;
    setInput('');
    setSendError(null);
    updateSendState(nextCoachSendState(sendStateRef.current, {
      type: 'send',
      content,
      messageId,
      interactionReply,
    }));
    try {
      const active = await ensureConversation();
      if (scope !== scopeRef.current) return;
      // The server may finish a reply after the device loses its connection.
      // Preserve this route before sending so reconnecting can recover that reply
      // without creating a duplicate conversation or user message.
      if (params.sessionId === 'new') {
        // Promoting this draft to its saved ID is still the same conversation.
        scope.key = `${session.user.id}:${active.id}`;
        router.setParams({ sessionId: active.id });
      }
      const optimistic: CoachMessageType = {
        id: messageId,
        session_id: active.id,
        user_id: session.user.id,
        role: 'user',
        content,
        reply_to_message_id: null,
        status: 'completed',
        error_code: null,
        model: null,
        prompt_tokens: null,
        completion_tokens: null,
        feedback: null,
        ui_payload: {},
        created_at: new Date().toISOString(),
        sources: [],
      };
      setMessages((current) => (
        current.some((message) => message.id === messageId)
          ? current
          : [...current, optimistic]
      ));
      const turn = await sendCoachMessage(
        active.id,
        messageId,
        content,
        interactionReply,
        PROVIDER_CONSENT_VERSION,
      );
      if (scope !== scopeRef.current) return;
      ++loadSequence.current;
      shouldScrollToLatest.current = true;
      setMessages((current) => {
        const updated = mergeTurn(current, turn);
        if (userId) {
          const cached = readCachedMessagePage(userId, active.id);
          writeCachedMessagePage(userId, active.id, {
            messages: mergeTurn(cached?.messages ?? updated, turn),
            next_before: cached?.next_before ?? nextBefore,
          });
        }
        return updated;
      });
      setConversation((current) => current ? { ...current, title: current.title === 'New conversation' ? content.slice(0, 60) : current.title, last_message_at: turn.assistant_message.created_at } : current);
      updateSendState(nextCoachSendState(sendStateRef.current, { type: 'success' }));
    } catch (error) {
      if (scope !== scopeRef.current) return;
      setSendError(coachErrorMessage(error));
      updateSendState(nextCoachSendState(sendStateRef.current, { type: 'failure' }));
    }
  }, [ensureConversation, isOnline, loading, nextBefore, params.sessionId, profile, session, updateSendState, userId]);

  // Rows capture this instead of `send` directly. `send` legitimately changes
  // identity as the send state moves idle -> sending -> idle, and handing it
  // straight to every row would defeat their memoization on each of those moves.
  const sendRef = useRef(send);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  const handleFollowUp = useCallback(
    (prompt: string, interactionReply?: CoachInteractionReply) => {
      void sendRef.current(prompt, undefined, false, interactionReply);
    },
    [],
  );

  const feedbackDisabled = isSending || activeActionMessageId !== null;

  const saveSpendingConsent = useCallback(async (
    value: NonNullable<typeof profile>['spending_records_consent'],
  ) => {
    if (consentRequestRef.current) return;
    const request = {};
    const scope = scopeRef.current;
    const queuedQuestion = pendingConsentQuestion;
    consentRequestRef.current = request;
    setConsentSaving(true);
    setConsentError(null);
    try {
      const result = await updateProfile({ spending_records_consent: value });
      if (scope !== scopeRef.current) return;
      if (!result.ok) {
        setConsentError(result.message);
        return;
      }
      setPendingConsentQuestion(null);
      if (queuedQuestion) {
        setInput('');
        // The backend reads the saved consent status before building context.
        // Granted access includes recorded transactions; declining continues with
        // general guidance while transaction rows remain unavailable.
        void sendRef.current(queuedQuestion.content, queuedQuestion.messageId, true, queuedQuestion.interactionReply);
      }
    } catch (error) {
      if (scope === scopeRef.current) setConsentError(coachErrorMessage(error));
    } finally {
      if (consentRequestRef.current === request) {
        consentRequestRef.current = null;
        setConsentSaving(false);
      }
    }
  }, [pendingConsentQuestion, updateProfile]);

  const saveMessageFeedback = useCallback(async (
    messageId: string,
    feedback: CoachFeedback | null,
  ) => {
    setSendError(null);
    try {
      const updated = await setCoachMessageFeedback(messageId, feedback);
      setMessages((current) => current.map((message) => (
        message.id === messageId
          ? { ...message, feedback: updated.feedback }
          : message
      )));
    } catch (error) {
      setSendError(coachErrorMessage(error));
      throw error;
    }
  }, []);

  const replaceMessage = useCallback((updated: CoachMessageType) => {
    setMessages((current) => {
      const next = current.map((message) => (
        message.id === updated.id ? { ...updated, sources: updated.sources ?? message.sources } : message
      ));
      if (userId && conversation) {
        const cached = readCachedMessagePage(userId, conversation.id);
        writeCachedMessagePage(userId, conversation.id, {
          messages: next,
          next_before: cached?.next_before ?? nextBefore,
        });
      }
      return next;
    });
  }, [conversation, nextBefore, userId]);

  // One persisted attempt holds a live server lease. Its true state is only
  // ever established by asking the owner-scoped endpoint, never by guessing
  // from a lost response. `unresolved` means the answer could not be
  // established: the reservation is kept and no retry may start yet.
  const reconcileStoredAttempt = useCallback(async (
    ownerId: string,
    messageId: string,
    action: CoachActionPayload,
    attemptId?: string,
  ): Promise<{ attempt: CoachReportAttempt | null; unresolved: boolean }> => {
    let savedId = attemptId ?? null;
    if (!savedId) {
      const saved = await loadReportAttempt(ownerId, messageId, action.action_id).catch(() => null);
      savedId = saved?.attemptId ?? null;
    }
    if (!savedId) return { attempt: null, unresolved: false };
    const reconciliation = await reconcileReportAttempt({
      attemptId: savedId,
      fetchAttempt: (id) => getReportAttempt(messageId, id),
    });
    if (reconciliation.kind === 'active' || reconciliation.kind === 'completed') {
      return { attempt: reconciliation.attempt, unresolved: false };
    }
    if (reconciliation.kind === 'missing') {
      // The server proved this reservation can no longer publish a report, so
      // discarding it is safe.
      await clearReportAttempt(ownerId, messageId, action.action_id).catch(() => {});
      return { attempt: null, unresolved: false };
    }
    // An unknown answer keeps the record for a later check.
    return { attempt: null, unresolved: true };
  }, []);

  // A card left "approved" may have finished on another device or before the
  // app restarted. After each fresh page load, reconcile its persisted attempt
  // so the card shows the real outcome instead of restarting the report.
  const reconcileStoredReportAttempts = useCallback(async (
    items: CoachMessageType[],
    scope: object,
  ) => {
    if (!userId) return;
    for (const candidate of items) {
      const payload = candidate.ui_payload;
      if (!isCoachAction(payload)
        || payload.action_type !== 'generate_report' || payload.status !== 'approved') {
        continue;
      }
      if (scope !== scopeRef.current) return;
      const { attempt } = await reconcileStoredAttempt(userId, candidate.id, payload);
      if (scope !== scopeRef.current) return;
      if (!attempt || attempt.status !== 'completed') continue;
      replaceMessage({
        ...candidate,
        ui_payload: {
          ...payload,
          status: 'executed',
          result: {
            title: payload.title,
            storage_path: attempt.storage_path,
            ...(typeof attempt.report_id === 'number' ? { report_id: attempt.report_id } : {}),
          },
        },
      });
      await clearReportAttempt(userId, candidate.id, payload.action_id).catch(() => {});
    }
  }, [reconcileStoredAttempt, replaceMessage, userId]);
  useEffect(() => {
    reconcileAttemptsRef.current = (items, scope) => {
      void reconcileStoredReportAttempts(items, scope);
    };
  }, [reconcileStoredReportAttempts]);

  const confirmAction = useCallback(async (message: CoachMessageType) => {
    if (!session || actionRequestRef.current || sendStateRef.current.status === 'sending'
      || !isCoachAction(message.ui_payload)) return;
    const scope = scopeRef.current;
    const request = {};
    actionRequestRef.current = request;
    const action = message.ui_payload;
    const ownerId = session.user.id;
    setActiveActionMessageId(message.id);
    setSendError(null);
    let heartbeat: ReportAttemptHeartbeat | null = null;
    try {
      if (action.action_type !== 'generate_report') {
        const approved = await confirmCoachAction(message.id, action.action_id);
        if (scope === scopeRef.current) replaceMessage(approved.message);
        return;
      }

      // Reconciliation comes first: a retry resumes the attempt the server
      // already owns instead of starting a second one.
      const stored = await reconcileStoredAttempt(ownerId, message.id, action);
      if (scope !== scopeRef.current) return;
      if (stored.unresolved) {
        // The previous reservation might still be live, so no new attempt may
        // start until the server confirms what happened to it.
        throw new Error('The previous report attempt could not be verified.');
      }
      let attempt = stored.attempt;
      if (attempt?.status !== 'completed') {
        // Even an active saved attempt must be claimed again. This atomically
        // renews a live lease or reacquires an expired one before rendering.
        let plannedAttemptId = attempt?.attempt_id ?? randomUUID();
        for (let claimTry = 0; claimTry < 2; claimTry += 1) {
          await saveReportAttempt({ userId: ownerId, messageId: message.id,
            actionId: action.action_id, attemptId: plannedAttemptId });
          try {
            const confirmed = await confirmCoachAction(message.id, action.action_id, plannedAttemptId);
            if (scope !== scopeRef.current) return;
            replaceMessage(confirmed.message);
            if (isCoachAction(confirmed.message.ui_payload)
              && confirmed.message.ui_payload.status === 'executed') {
              await discardSavedReportAttempt(ownerId, message.id, action.action_id);
              return;
            }
            const parsed = parseReportAttempt(confirmed.effect?.attempt);
            if (!parsed || parsed.attempt_id !== plannedAttemptId
              || parsed.message_id !== message.id || parsed.action_id !== action.action_id) {
              throw new Error('The report attempt was not started.');
            }
            attempt = parsed;
            break;
          } catch (error) {
            if (scope !== scopeRef.current) throw error;
            if (error instanceof CoachApiError && error.code === 'attempt_id_reused' && claimTry === 0) {
              plannedAttemptId = randomUUID();
              continue;
            }
            // A definitive competing claim must never be adopted as our renderer.
            if (error instanceof CoachApiError && error.code === 'action_in_progress') throw error;
            const outcome = await reconcileStoredAttempt(ownerId, message.id, action, plannedAttemptId);
            attempt = outcome.attempt;
            if (!attempt || (attempt.status === 'active' && attempt.lease_valid !== true)) throw error;
            break;
          }
        }
      }
      if (!attempt || scope !== scopeRef.current) return;
      const liveAttempt = attempt;

      if (liveAttempt.status === 'completed') {
        // A previous run already published this report; the history row exists.
        if (scope === scopeRef.current) {
          replaceMessage({
            ...message,
            ui_payload: {
              ...action,
              status: 'executed',
              result: {
                title: action.title,
                storage_path: liveAttempt.storage_path,
                ...(typeof liveAttempt.report_id === 'number'
                  ? { report_id: liveAttempt.report_id }
                  : {}),
              },
            },
          });
        }
        await discardSavedReportAttempt(ownerId, message.id, action.action_id);
        return;
      }

      const completionKey = `${ownerId}:${liveAttempt.attempt_id}`;
      let leaseLost = false;
      // Use the server's remaining lease, not the phone's wall-clock offset.
      const leaseDeadline = (value: CoachReportAttempt) => Date.now() + Math.max(0,
        Date.parse(value.lease_expires_at ?? '') - Date.parse(value.server_time ?? ''));
      let expiresAt = leaseDeadline(liveAttempt);
      const assertLease = () => {
        if (leaseLost || !Number.isFinite(expiresAt) || Date.now() >= expiresAt || scope !== scopeRef.current) {
          throw new CoachApiError(409, 'The report attempt is no longer active.', 'attempt_expired');
        }
      };
      if (liveAttempt.lease_valid !== true) {
        throw new CoachApiError(409, 'The report attempt lease expired.', 'attempt_expired');
      }
      heartbeat = startReportAttemptHeartbeat({
        renew: async () => {
          const renewed = parseReportAttempt(await renewReportAttempt(message.id, liveAttempt.attempt_id));
          if (!renewed || renewed.attempt_id !== liveAttempt.attempt_id || renewed.lease_valid !== true) {
            leaseLost = true;
          } else {
            expiresAt = leaseDeadline(renewed);
          }
        },
        onLost: () => { leaseLost = true; },
      });
      let report = pendingReportCompletions.get(completionKey);
      if (!report) {
        try {
          report = await generateCoachReport(ownerId, liveAttempt, undefined, assertLease);
          assertLease();
          pendingReportCompletions.set(completionKey, report);
        } catch (error) {
          assertLease();
          try {
            const failed = await completeCoachAction(message.id, action.action_id, false, {
              message: 'The PDF could not be generated.',
            }, liveAttempt.attempt_id);
            if (scope === scopeRef.current) replaceMessage(failed.message);
            await discardSavedReportAttempt(ownerId, message.id, action.action_id);
          } catch {
            // The determination could not be recorded; keep the persisted
            // attempt so the next press reconciles it before retrying.
          }
          throw error;
        }
      }
      // A lost completion response says nothing about whether the saved PDF
      // exists. Keep its ID for retry; never report a generation failure here.
      assertLease();
      const completed = await completeCoachAction(message.id, action.action_id, true, {
        title: report.title,
        file_name: report.fileName,
        generated_at: report.generatedAt,
      }, liveAttempt.attempt_id);
      pendingReportCompletions.delete(completionKey);
      await discardSavedReportAttempt(ownerId, message.id, action.action_id);
      if (scope === scopeRef.current) replaceMessage(completed.message);
    } catch (error) {
      if (scope === scopeRef.current) setSendError(coachErrorMessage(error));
    } finally {
      heartbeat?.stop();
      if (actionRequestRef.current === request) {
        actionRequestRef.current = null;
        setActiveActionMessageId(null);
      }
    }
  }, [reconcileStoredAttempt, replaceMessage, session]);

  const cancelAction = useCallback(async (message: CoachMessageType) => {
    if (actionRequestRef.current || sendStateRef.current.status === 'sending' || !isCoachAction(message.ui_payload)) return;
    const scope = scopeRef.current;
    const request = {};
    actionRequestRef.current = request;
    setActiveActionMessageId(message.id);
    setSendError(null);
    try {
      const result = await cancelCoachAction(message.id, message.ui_payload.action_id);
      if (message.ui_payload.action_type === 'generate_report' && userId) {
        // The same commit cancelled the live attempt, so the local reservation
        // can no longer start or resume a report.
        await discardSavedReportAttempt(userId, message.id, message.ui_payload.action_id);
      }
      if (scope === scopeRef.current) replaceMessage(result.message);
    } catch (error) {
      if (scope === scopeRef.current) setSendError(coachErrorMessage(error));
    } finally {
      if (actionRequestRef.current === request) {
        actionRequestRef.current = null;
        setActiveActionMessageId(null);
      }
    }
  }, [replaceMessage, userId]);

  const changeAction = useCallback(async (message: CoachMessageType) => {
    if (actionRequestRef.current || sendStateRef.current.status === 'sending' || !isCoachAction(message.ui_payload)) return;
    const scope = scopeRef.current;
    const request = {};
    actionRequestRef.current = request;
    setActiveActionMessageId(message.id);
    setSendError(null);
    try {
      const result = await cancelCoachAction(message.id, message.ui_payload.action_id);
      if (scope !== scopeRef.current) return;
      if (message.ui_payload.action_type === 'generate_report' && userId) {
        await discardSavedReportAttempt(userId, message.id, message.ui_payload.action_id);
      }
      replaceMessage(result.message);
    } catch (error) {
      if (scope === scopeRef.current) setSendError(coachErrorMessage(error));
      return;
    } finally {
      if (actionRequestRef.current === request) {
        actionRequestRef.current = null;
        setActiveActionMessageId(null);
      }
    }
    const currentDetails = message.ui_payload.fields
      .map((field) => `${field.label}: ${field.value}`)
      .join('; ');
    setInput(
      `Change this ${message.ui_payload.action_type === 'create_reminder' ? 'reminder' : 'report'}. `
      + `Current details: ${currentDetails}. New details: `,
    );
  }, [replaceMessage, userId]);

  const retryContent = sendState.status === 'failed' ? sendState.content : null;
  const retryMessageId = sendState.status === 'failed' ? sendState.messageId : null;
  const retryInteractionReply = sendState.status === 'failed' ? sendState.interactionReply : undefined;
  const showSuggestions = shouldShowCoachSuggestions(messages, loading || isSending);
  const title = conversation?.title === 'New conversation' || !conversation ? 'FinCoach' : conversation.title;
  const listData = useMemo(() => messages, [messages]);
  const lastAssistantMessageId = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant')?.id ?? null,
    [messages],
  );
  // Paced micro-coaching: after a completed answer, surface any intent the single
  // locked-format reply dropped (or the take-home figure it asked for) as a chip.
  const followUpChips = useMemo<CoachFollowUpChip[]>(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== 'assistant' || last.status !== 'completed') return [];
    const lastUser = [...messages].reverse().find((message) => message.role === 'user');
    return getCoachFollowUpChips(lastUser?.content ?? '', last.content);
  }, [messages]);
  const onFollowUpChip = useCallback((chip: CoachFollowUpChip) => {
    if (chip.kind === 'send') {
      void send(chip.query);
      return;
    }
    // Prefill only — the user types their own take-home figure; we never send a
    // financial amount they did not enter.
    setInput(chip.text);
    inputRef.current?.focus();
  }, [send]);
  const renderMessage = useCallback(
    ({ item }: { item: CoachMessageType }) => (
      <CoachMessage
        feedbackDisabled={feedbackDisabled}
        message={item}
        onActionCancel={cancelAction}
        onActionChange={changeAction}
        onActionConfirm={confirmAction}
        onFeedback={saveMessageFeedback}
        onFollowUp={handleFollowUp}
        showFollowUps={item.id === lastAssistantMessageId}
      />
    ),
    [
      cancelAction,
      changeAction,
      confirmAction,
      feedbackDisabled,
      handleFollowUp,
      lastAssistantMessageId,
      saveMessageFeedback,
    ],
  );

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: authColors.surface }}
      behavior={process.env.EXPO_OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={0}>
      <View style={[styles.header, { paddingTop: insets.top + 7 }]}>
        <View style={styles.headerAvatar}>
          <MaterialCommunityIcons name="creation" size={22} color={authColors.onPrimary} />
          <View style={styles.headerStatusDot} />
        </View>
        <View style={{ flex: 1 }}>
          <Text numberOfLines={1} style={styles.headerTitle}>{title}</Text>
          <Text style={styles.onlineText}>AI financial coach</Text>
        </View>
        <AnimatedPressable accessibilityRole="button" accessibilityLabel="New conversation" hitSlop={8} onPress={() => {
          scopeRef.current = { key: `${userId ?? ''}:new`, generation: scopeRef.current.generation + 1 };
          router.setParams({ sessionId: 'new' });
          setConversation(null);
          setMessages([]);
          setNextBefore(null);
          setSendError(null);
        }} style={styles.iconButton}>
          <MaterialCommunityIcons name="plus" size={25} color={authColors.onSurfaceVariant} />
        </AnimatedPressable>
        <AnimatedPressable accessibilityRole="button" accessibilityLabel="Conversation history" hitSlop={8} onPress={() => router.push('/coach/history' as Href)} style={styles.iconButton}>
          <MaterialCommunityIcons name="history" size={24} color={authColors.onSurfaceVariant} />
        </AnimatedPressable>
      </View>

      {loading ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeIn.duration(coachMotion.stateTransitionDuration)}
          exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
          style={styles.loadingState}>
          <CoachChatSkeleton />
        </Animated.View>
      ) : loadError ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeInDown.duration(coachMotion.stateTransitionDuration)}
          exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
          style={styles.center}>
          <View style={styles.errorIcon}>
            <MaterialCommunityIcons name="cloud-off-outline" size={29} color={authColors.error} />
          </View>
          <Text style={styles.errorTitle}>Coach unavailable</Text>
          <Text selectable style={styles.errorText}>{loadError}</Text>
          <AnimatedPressable accessibilityRole="button" onPress={() => void load()} style={styles.retryButton}><Text style={styles.retryButtonText}>Retry</Text></AnimatedPressable>
        </Animated.View>
      ) : (
        <FlatList
          ref={listRef}
          data={listData}
          keyExtractor={coachMessageKeyExtractor}
          maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
          renderItem={renderMessage}
          contentInsetAdjustmentBehavior="automatic"
          contentContainerStyle={coachListContentStyle}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          onScroll={({ nativeEvent }) => {
            if (nativeEvent.contentOffset.y <= 24) {
              void loadOlderMessages();
            }
          }}
          scrollEventThrottle={32}
          onContentSizeChange={() => {
            if (shouldScrollToLatest.current) {
              listRef.current?.scrollToEnd({ animated: true });
              shouldScrollToLatest.current = false;
            }
          }}
          ListHeaderComponent={loadingOlderMessages ? (
            <View style={styles.olderMessagesLoading}>
              <ActivityIndicator color={authColors.primary} size="small" />
              <Text style={styles.olderMessagesLoadingText}>Loading earlier messages…</Text>
            </View>
          ) : null}
          ListEmptyComponent={
            <View style={styles.emptyContent}>
              <Animated.View
                entering={reduceMotion ? undefined : FadeIn.duration(coachMotion.stateTransitionDuration)}
                style={styles.welcome}>
                <View style={styles.welcomeIcon}><MaterialCommunityIcons name="creation-outline" size={29} color={authColors.primary} /></View>
                <Text style={styles.welcomeTitle}>What should we improve today?</Text>
                <Text selectable style={styles.welcomeCopy}>
                  Get a direct answer using your recorded budgets, spending, savings goals, and trusted references.
                </Text>
                <View style={styles.trustPill}>
                  <MaterialCommunityIcons name="shield-check-outline" size={14} color={authColors.primary} />
                  <Text style={styles.trustPillText}>
                    {includeRecordedSpending
                      ? 'Recorded spending is included'
                      : 'Spending records stay excluded'}
                  </Text>
                </View>
              </Animated.View>
              <CoachInsightStrip
                cards={insights}
                loading={insightsLoading}
                onSelect={(prompt) => void send(prompt)}
              />
            </View>
          }
          ListFooterComponent={isSending ? (
            <View style={{ paddingTop: 12 }}>
              <CoachTypingIndicator />
              {longWait ? <Text accessibilityLiveRegion="polite" style={styles.pendingNotice}>
                Still working on your answer. This can take up to two minutes.
              </Text> : null}
            </View>
          ) : null}
        />
      )}

      {profile && !includeRecordedSpending && (
        profile.spending_records_consent === 'unset' || pendingConsentQuestion
      ) ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeInDown.duration(coachMotion.stateTransitionDuration)}
          exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
          style={[
            styles.consentCard,
            pendingConsentQuestion ? styles.consentCardRequired : null,
          ]}>
          {pendingConsentQuestion ? (
            <Text selectable style={styles.consentRequiredText}>
              To answer “{pendingConsentQuestion.content}”, FinCoach needs permission to use your
              recorded transactions.
            </Text>
          ) : null}
          <ConsentSelector
            disabled={consentSaving}
            requiredForQuestion={Boolean(pendingConsentQuestion)}
            value={profile.spending_records_consent}
            onChange={(value) => void saveSpendingConsent(value)}
          />
          {consentSaving ? (
            <Text style={styles.consentStatus}>Saving permission…</Text>
          ) : null}
          {consentError ? (
            <Text accessibilityRole="alert" selectable style={styles.consentError}>
              {consentError}
            </Text>
          ) : null}
        </Animated.View>
      ) : null}

      {sendError ? (
        <Animated.View
          accessibilityRole="alert"
          entering={reduceMotion ? undefined : FadeInDown.duration(coachMotion.stateTransitionDuration)}
          exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
          style={styles.errorBar}>
          <Text selectable style={styles.errorBarText}>{sendError}</Text>
          {retryContent && retryMessageId ? (
            <AnimatedPressable onPress={() => void send(retryContent, retryMessageId, false, retryInteractionReply)}>
              <Text style={styles.errorAction}>Retry</Text>
            </AnimatedPressable>
          ) : null}
        </Animated.View>
      ) : null}

      {showSuggestions ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeInDown.duration(coachMotion.stateTransitionDuration)}
          exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
          style={styles.suggestionSection}>
          <Text style={styles.suggestionLabel}>QUICK QUESTIONS</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.suggestions} keyboardShouldPersistTaps="handled">
            {SUGGESTIONS.map((suggestion) => (
              <AnimatedPressable key={suggestion} accessibilityRole="button" onPress={() => void send(suggestion)} style={styles.suggestionChip}>
                <Text style={styles.suggestionText}>{suggestion}</Text>
              </AnimatedPressable>
            ))}
          </ScrollView>
        </Animated.View>
      ) : null}

      {!showSuggestions && !isSending && followUpChips.length > 0 ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeInDown.duration(coachMotion.stateTransitionDuration)}
          exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
          style={styles.suggestionSection}>
          <Text style={styles.suggestionLabel}>CONTINUE</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.suggestions} keyboardShouldPersistTaps="handled">
            {followUpChips.map((chip) => (
              <AnimatedPressable key={chip.label} accessibilityRole="button" onPress={() => onFollowUpChip(chip)} style={styles.suggestionChip}>
                <Text style={styles.suggestionText}>{chip.label}</Text>
              </AnimatedPressable>
            ))}
          </ScrollView>
        </Animated.View>
      ) : null}

      <View style={[styles.composerBar, { paddingBottom: Math.max(insets.bottom, 10) }]}>
        <View style={styles.inputShell}>
          <TextInput
            ref={inputRef}
            accessibilityLabel="Message FinCoach"
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => void send()}
            placeholder="Ask me anything…"
            placeholderTextColor={authColors.outline}
            returnKeyType="send"
            multiline
            maxLength={1000}
            style={styles.input}
          />
        </View>
        <AnimatedPressable
          accessibilityRole="button"
          accessibilityLabel="Send message"
          disabled={!canSendCoachMessage(input, isSending || loading || activeActionMessageId !== null)}
          onPress={() => void send()}
          style={[styles.sendButton, { opacity: canSendCoachMessage(input, isSending) ? 1 : 0.4 }]}>
          <MaterialCommunityIcons name="arrow-up" size={25} color={authColors.onPrimary} />
        </AnimatedPressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function CoachChatSkeleton() {
  return (
    <View accessibilityLabel="Loading your conversations" style={styles.skeletonContainer}>
      <View style={styles.skeletonAssistantRow}>
        <View style={styles.skeletonAvatar} />
        <View style={[styles.skeletonBubble, { width: '68%' }]}>
          <View style={[styles.skeletonLine, { width: '76%' }]} />
          <View style={[styles.skeletonLine, { width: '92%' }]} />
          <View style={[styles.skeletonLine, { width: '55%' }]} />
        </View>
      </View>
      <View style={[styles.skeletonBubble, styles.skeletonUserBubble]}>
        <View style={[styles.skeletonLine, { width: '82%' }]} />
        <View style={[styles.skeletonLine, { width: '58%' }]} />
      </View>
      <View style={styles.skeletonAssistantRow}>
        <View style={styles.skeletonAvatar} />
        <View style={[styles.skeletonBubble, { width: '58%' }]}>
          <View style={[styles.skeletonLine, { width: '88%' }]} />
          <View style={[styles.skeletonLine, { width: '64%' }]} />
        </View>
      </View>
    </View>
  );
}

const styles = {
  header: { minHeight: 70, paddingHorizontal: 16, paddingBottom: 9, flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const,
  headerAvatar: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary } as const,
  headerStatusDot: { position: 'absolute', right: -1, bottom: -1, width: 13, height: 13, borderRadius: 7, borderWidth: 2, borderColor: authColors.surfaceContainerLowest, backgroundColor: '#06A96B' } as const,
  headerTitle: { color: authColors.onSurface, fontFamily: authFont.semibold, fontSize: 17, lineHeight: 21 } as const,
  onlineText: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 12, lineHeight: 16 } as const,
  iconButton: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const,
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 28 } as const,
  loadingState: { flex: 1, paddingHorizontal: 16, paddingTop: 24 } as const,
  olderMessagesLoading: { minHeight: 38, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingBottom: 8 } as const,
  olderMessagesLoadingText: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 12 } as const,
  skeletonContainer: { gap: 18 } as const,
  skeletonAssistantRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 } as const,
  skeletonAvatar: { width: 28, height: 28, borderRadius: 14, backgroundColor: authColors.surfaceContainerHigh } as const,
  skeletonBubble: { minHeight: 80, borderRadius: 20, padding: 15, justifyContent: 'center', gap: 9, backgroundColor: authColors.surfaceContainerLow } as const,
  skeletonUserBubble: { width: '48%', minHeight: 58, alignSelf: 'flex-end', backgroundColor: authColors.primaryFixed } as const,
  skeletonLine: { height: 10, borderRadius: 5, backgroundColor: authColors.surfaceContainerHigh } as const,
  errorIcon: { width: 58, height: 58, borderRadius: 29, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFF0F0' } as const,
  errorTitle: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 18, lineHeight: 23 } as const,
  errorText: { color: authColors.error, fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, textAlign: 'center' } as const,
  retryButton: { borderRadius: 18, paddingHorizontal: 18, paddingVertical: 9, backgroundColor: authColors.primary } as const,
  retryButtonText: { color: authColors.onPrimary, fontFamily: authFont.semibold, fontSize: 13 } as const,
  emptyContent: { flex: 1, gap: 20, paddingBottom: 8 } as const,
  consentCard: { marginHorizontal: 16, marginBottom: 8, borderRadius: 18, padding: 14, gap: 9, backgroundColor: authColors.surfaceContainerLow, borderWidth: 1, borderColor: authColors.outlineVariant } as const,
  consentCardRequired: { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed } as const,
  consentRequiredText: { color: authColors.onPrimaryFixed, fontFamily: authFont.semibold, fontSize: 12, lineHeight: 17 } as const,
  consentStatus: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 } as const,
  pendingNotice: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, marginTop: 8, marginLeft: 44, paddingRight: 12 } as const,
  consentError: { color: authColors.error, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 } as const,
  welcome: { minHeight: 242, alignItems: 'center', justifyContent: 'center', gap: 10, paddingHorizontal: 28 } as const,
  welcomeIcon: { width: 58, height: 58, borderRadius: 29, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed } as const,
  welcomeTitle: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 19 } as const,
  welcomeCopy: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, textAlign: 'center' } as const,
  trustPill: { minHeight: 30, flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 15, paddingHorizontal: 11, backgroundColor: authColors.primaryFixed } as const,
  trustPillText: { color: authColors.onPrimaryFixed, fontFamily: authFont.semibold, fontSize: 11, lineHeight: 15 } as const,
  errorBar: { marginHorizontal: 16, marginBottom: 8, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFF1F1' } as const,
  errorBarText: { flex: 1, color: authColors.error, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 } as const,
  errorAction: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 12 } as const,
  suggestionSection: { gap: 6 } as const,
  suggestionLabel: { paddingHorizontal: 16, color: authColors.onSurfaceVariant, fontFamily: authFont.bold, fontSize: 10, lineHeight: 14, letterSpacing: 0.8 } as const,
  suggestions: { paddingHorizontal: 16, paddingBottom: 8, gap: 8 } as const,
  suggestionChip: { height: 36, justifyContent: 'center', borderRadius: 18, borderWidth: 1, borderColor: authColors.primaryFixedDim, paddingHorizontal: 14, backgroundColor: authColors.surfaceContainerLowest } as const,
  suggestionText: { color: authColors.primary, fontFamily: authFont.semibold, fontSize: 13 } as const,
  composerBar: { paddingHorizontal: 16, paddingTop: 9, flexDirection: 'row', alignItems: 'flex-end', gap: 9, borderTopWidth: 1, borderTopColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const,
  inputShell: { flex: 1, minHeight: 48, maxHeight: 110, justifyContent: 'center', borderRadius: 24, paddingHorizontal: 16, backgroundColor: authColors.surfaceContainerHigh } as const,
  input: { maxHeight: 96, paddingVertical: 11, color: authColors.onSurface, fontFamily: authFont.regular, fontSize: 15, lineHeight: 20 } as const,
  sendButton: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary } as const,
} as const;
