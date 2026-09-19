import { MaterialCommunityIcons } from '@expo/vector-icons';
import NetInfo from '@react-native-community/netinfo';
import { randomUUID } from 'expo-crypto';
import { router, useFocusEffect, useLocalSearchParams, type Href } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  cancelCoachAction,
  completeCoachAction,
  confirmCoachAction,
  createCoachConversation,
  listCoachConversations,
  listCoachMessages,
  sendCoachMessage,
  setCoachMessageFeedback,
} from '@/lib/coach-api';
import { generateCoachReport } from '@/lib/coach-actions';
import { isCoachAction } from '@/lib/coach-agent';
import {
  canSendCoachMessage,
  coachErrorMessage,
  mergeTurn,
  shouldRequestSpendingConsent,
  shouldShowCoachSuggestions,
  sortConversations,
} from '@/lib/coach-domain';
import { buildCoachInsightCards, type CoachInsightCard } from '@/lib/coach-insights';
import { coachMotion } from '@/lib/coach-motion';
import { PROVIDER_CONSENT_VERSION } from '@/lib/coach-provider-consent';
import {
  nextCoachSendState,
  type CoachFeedback,
  type CoachSendState,
} from '@/lib/coach-ui';
import { createPresetSelection } from '@/lib/report-domain';
import { fetchReportSourceData } from '@/lib/reports';
import { fetchSavingsGoals } from '@/lib/savings';
import type {
  CoachConversation,
  CoachInteractionReply,
  CoachMessage as CoachMessageType,
  CoachMessagePage,
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
  const [pendingConsentQuestion, setPendingConsentQuestion] = useState<string | null>(null);
  const [activeActionMessageId, setActiveActionMessageId] = useState<string | null>(null);
  const isSending = sendState.status === 'sending';
  const userId = session?.user.id;
  const loadSequence = useRef(0);
  const shouldScrollToLatest = useRef(true);
  const sendStateRef = useRef<CoachSendState>({ status: 'idle' });
  const networkWasOfflineRef = useRef(false);
  const includeRecordedSpending = profile?.spending_records_consent === 'granted';
  // The composer keeps the draft in state so the input stays controlled, but
  // reading it back through a ref keeps `send` (and therefore every row's props)
  // stable while typing. Without this, each keystroke rebuilt the callbacks and
  // forced the whole message list to re-render.
  const draftRef = useRef(input);
  useEffect(() => {
    draftRef.current = input;
  }, [input]);
  useEffect(() => {
    sendStateRef.current = sendState;
  }, [sendState]);

  const load = useCallback(async () => {
    if (!session) {
      setLoading(false);
      setLoadError('Sign in to use your financial coach.');
      return;
    }
    const requestId = ++loadSequence.current;
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
      if (requestId !== loadSequence.current) return;
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
        if (requestId !== loadSequence.current) return;
        writeCachedMessagePage(ownerId, selected.id, page);
        shouldScrollToLatest.current = true;
        setMessages(page.messages);
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
          setSendState({ status: 'idle' });
        }
        setNextBefore(page.next_before);
      }
    } catch (error) {
      if (requestId === loadSequence.current && !hasCachedPage) {
        setLoadError(coachErrorMessage(error));
      }
    } finally {
      if (requestId === loadSequence.current) {
        setLoading(false);
      }
    }
  }, [params.sessionId, session]);

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
        setInsights(buildCoachInsightCards({
          includeRecordedSpending,
          monthlyBudget: source.monthlyBudgets[0] ?? null,
          transactions: source.transactions,
          savingsGoals: source.savingsGoals,
        }));
      } else {
        const savingsGoals = await fetchSavingsGoals(userId);
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
      setInsights([]);
    } finally {
      setInsightsLoading(false);
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
    const created = await createCoachConversation();
    setConversation(created);
    if (userId) {
      const cached = readCachedConversations(userId) ?? [];
      writeCachedConversations(userId, sortConversations([created, ...cached]));
    }
    return created;
  }, [conversation, userId]);

  const loadOlderMessages = useCallback(async () => {
    if (!conversation || !nextBefore || loadingOlderMessages || isSending) return;
    setLoadingOlderMessages(true);
    shouldScrollToLatest.current = false;
    try {
      const page = await listCoachMessages(conversation.id, {
        limit: COACH_MESSAGE_PAGE_SIZE,
        before: nextBefore,
      });
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
      setSendError(coachErrorMessage(error));
    } finally {
      setLoadingOlderMessages(false);
    }
  }, [conversation, isSending, loadingOlderMessages, nextBefore, userId]);

  const send = useCallback(async (
    rawContent?: string,
    retryMessageId?: string,
    consentDecisionHandled = false,
    interactionReply?: CoachInteractionReply,
  ) => {
    const content = (rawContent ?? draftRef.current).trim();
    if (!canSendCoachMessage(content, isSending) || !session) return;
    if (
      !consentDecisionHandled
      && profile
      && shouldRequestSpendingConsent(content, profile.spending_records_consent)
    ) {
      setPendingConsentQuestion(content);
      setConsentError(null);
      setInput(content);
      return;
    }
    const messageId = retryMessageId ?? randomUUID();

    if (!isOnline) {
      setSendError('No internet connection. Your message has not been sent.');
      setSendState({ status: 'failed', content, messageId });
      return;
    }

    shouldScrollToLatest.current = true;
    setInput('');
    setSendError(null);
    setSendState((current) => nextCoachSendState(current, {
      type: 'send',
      content,
      messageId,
    }));
    try {
      const active = await ensureConversation();
      // The server may finish a reply after the device loses its connection.
      // Preserve this route before sending so reconnecting can recover that reply
      // without creating a duplicate conversation or user message.
      if (params.sessionId === 'new') {
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
      setSendState((current) => nextCoachSendState(current, { type: 'success' }));
    } catch (error) {
      setSendError(coachErrorMessage(error));
      setSendState((current) => nextCoachSendState(current, { type: 'failure' }));
    }
  }, [ensureConversation, isOnline, isSending, nextBefore, params.sessionId, profile, session, userId]);

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
    if (consentSaving) return;
    setConsentSaving(true);
    setConsentError(null);
    const result = await updateProfile({ spending_records_consent: value });
    if (!result.ok) {
      setConsentError(result.message);
    } else {
      const queuedQuestion = pendingConsentQuestion;
      setPendingConsentQuestion(null);
      if (queuedQuestion) {
        setInput('');
        // The backend reads the saved consent status before building context.
        // Granted access includes recorded transactions; declining continues with
        // general guidance while transaction rows remain unavailable.
        void send(queuedQuestion, undefined, true);
      }
    }
    setConsentSaving(false);
  }, [consentSaving, pendingConsentQuestion, send, updateProfile]);

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

  const confirmAction = useCallback(async (message: CoachMessageType) => {
    if (!session || activeActionMessageId || !isCoachAction(message.ui_payload)) return;
    const action = message.ui_payload;
    setActiveActionMessageId(message.id);
    setSendError(null);
    try {
      const approved = await confirmCoachAction(message.id, action.action_id);
      replaceMessage(approved.message);
      if (approved.effect?.type === 'generate_report') {
        try {
          const report = await generateCoachReport(session.user.id, approved.effect.arguments);
          const completed = await completeCoachAction(
            message.id,
            action.action_id,
            true,
            {
              report_id: report.reportId,
              title: report.title,
              storage_path: report.storagePath,
            },
          );
          replaceMessage(completed.message);
        } catch (error) {
          try {
            const failed = await completeCoachAction(
              message.id,
              action.action_id,
              false,
              { message: 'The PDF could not be generated.' },
            );
            replaceMessage(failed.message);
          } catch {
            // Preserve the original local generation error below.
          }
          throw error;
        }
      }
    } catch (error) {
      setSendError(coachErrorMessage(error));
    } finally {
      setActiveActionMessageId(null);
    }
  }, [activeActionMessageId, replaceMessage, session]);

  const cancelAction = useCallback(async (message: CoachMessageType) => {
    if (activeActionMessageId || !isCoachAction(message.ui_payload)) return;
    setActiveActionMessageId(message.id);
    setSendError(null);
    try {
      const result = await cancelCoachAction(message.id, message.ui_payload.action_id);
      replaceMessage(result.message);
    } catch (error) {
      setSendError(coachErrorMessage(error));
    } finally {
      setActiveActionMessageId(null);
    }
  }, [activeActionMessageId, replaceMessage]);

  const changeAction = useCallback(async (message: CoachMessageType) => {
    if (activeActionMessageId || !isCoachAction(message.ui_payload)) return;
    setActiveActionMessageId(message.id);
    setSendError(null);
    try {
      const result = await cancelCoachAction(message.id, message.ui_payload.action_id);
      replaceMessage(result.message);
    } catch (error) {
      setSendError(coachErrorMessage(error));
      setActiveActionMessageId(null);
      return;
    }
    const currentDetails = message.ui_payload.fields
      .map((field) => `${field.label}: ${field.value}`)
      .join('; ');
    setInput(
      `Change this ${message.ui_payload.action_type === 'create_reminder' ? 'reminder' : 'report'}. `
      + `Current details: ${currentDetails}. New details: `,
    );
    setActiveActionMessageId(null);
  }, [activeActionMessageId, replaceMessage]);

  const retryContent = sendState.status === 'failed' ? sendState.content : null;
  const retryMessageId = sendState.status === 'failed' ? sendState.messageId : null;
  const showSuggestions = shouldShowCoachSuggestions(messages, loading || isSending);
  const title = conversation?.title === 'New conversation' || !conversation ? 'FinCoach' : conversation.title;
  const listData = useMemo(() => messages, [messages]);
  const lastAssistantMessageId = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant')?.id ?? null,
    [messages],
  );
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
        <AnimatedPressable accessibilityRole="button" accessibilityLabel="New conversation" hitSlop={8} onPress={() => { router.setParams({ sessionId: 'new' }); setConversation(null); setMessages([]); setSendError(null); }} style={styles.iconButton}>
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
          ListFooterComponent={isSending ? <View style={{ paddingTop: 12 }}><CoachTypingIndicator /></View> : null}
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
              To answer “{pendingConsentQuestion}”, FinCoach needs permission to use your
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
            <AnimatedPressable onPress={() => void send(retryContent, retryMessageId)}>
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

      <View style={[styles.composerBar, { paddingBottom: Math.max(insets.bottom, 10) }]}>
        <View style={styles.inputShell}>
          <TextInput
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
          disabled={!canSendCoachMessage(input, isSending)}
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
