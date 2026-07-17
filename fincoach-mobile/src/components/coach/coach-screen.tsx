import { MaterialIcons } from '@expo/vector-icons';
import { randomUUID } from 'expo-crypto';
import { router, useFocusEffect, useLocalSearchParams, type Href } from 'expo-router';
import { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CoachMessage, CoachTypingIndicator } from '@/components/coach/coach-message';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import {
  createCoachConversation,
  listCoachConversations,
  listCoachMessages,
  sendCoachMessage,
} from '@/lib/coach-api';
import { canSendCoachMessage, coachErrorMessage, mergeTurn, shouldShowCoachSuggestions, sortConversations } from '@/lib/coach-domain';
import { nextCoachSendState, type CoachSendState } from '@/lib/coach-ui';
import type { CoachConversation, CoachMessage as CoachMessageType } from '@/lib/types';

const SUGGESTIONS = [
  'How am I doing?',
  'Where can I cut spending?',
  'Am I on track for my goal?',
  'Help me save RM50',
] as const;

export default function CoachScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const params = useLocalSearchParams<{ sessionId?: string }>();
  const listRef = useRef<FlatList<CoachMessageType>>(null);
  const [conversation, setConversation] = useState<CoachConversation | null>(null);
  const [messages, setMessages] = useState<CoachMessageType[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendState, setSendState] = useState<CoachSendState>({ status: 'idle' });
  const isSending = sendState.status === 'sending';

  const load = useCallback(async () => {
    if (!session) {
      setLoading(false);
      setLoadError('Sign in to use your financial coach.');
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const saved = sortConversations(await listCoachConversations());
      const selected = params.sessionId
        ? saved.find((item) => item.id === params.sessionId) ?? null
        : saved[0] ?? null;
      if (!selected) {
        setConversation(null);
        setMessages([]);
      } else {
        setConversation(selected);
        setMessages(await listCoachMessages(selected.id));
      }
    } catch (error) {
      setLoadError(coachErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [params.sessionId, session]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const ensureConversation = useCallback(async () => {
    if (conversation) return conversation;
    const created = await createCoachConversation();
    setConversation(created);
    return created;
  }, [conversation]);

  const send = useCallback(async (rawContent?: string) => {
    const content = (rawContent ?? input).trim();
    if (!canSendCoachMessage(content, isSending) || !session) return;
    setInput('');
    setSendError(null);
    setSendState((current) => nextCoachSendState(current, { type: 'send', content }));
    const messageId = randomUUID();
    try {
      const active = await ensureConversation();
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
        created_at: new Date().toISOString(),
        sources: [],
      };
      setMessages((current) => [...current, optimistic]);
      const turn = await sendCoachMessage(active.id, messageId, content);
      setMessages((current) => mergeTurn(current, turn));
      setConversation((current) => current ? { ...current, title: current.title === 'New conversation' ? content.slice(0, 60) : current.title, last_message_at: turn.assistant_message.created_at } : current);
      setSendState((current) => nextCoachSendState(current, { type: 'success' }));
    } catch (error) {
      setSendError(coachErrorMessage(error));
      setSendState((current) => nextCoachSendState(current, { type: 'failure' }));
    }
  }, [ensureConversation, input, isSending, session]);

  const retryContent = sendState.status === 'failed' ? sendState.content : null;
  const showSuggestions = shouldShowCoachSuggestions(messages, loading || isSending);
  const title = conversation?.title === 'New conversation' || !conversation ? 'FinCoach' : conversation.title;
  const listData = useMemo(() => messages, [messages]);

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: authColors.surface }}
      behavior={process.env.EXPO_OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}>
      <View style={[styles.header, { paddingTop: insets.top + 7 }]}>
        <View style={styles.headerAvatar}>
          <MaterialIcons name="auto-awesome" size={21} color={authColors.onPrimary} />
          <View style={styles.onlineDot} />
        </View>
        <View style={{ flex: 1 }}>
          <Text numberOfLines={1} style={styles.headerTitle}>{title}</Text>
          <Text style={styles.onlineText}>online · AI coach</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="New conversation" hitSlop={8} onPress={() => { router.setParams({ sessionId: 'new' }); setConversation(null); setMessages([]); setSendError(null); }} style={styles.iconButton}>
          <MaterialIcons name="add-comment" size={21} color={authColors.onSurfaceVariant} />
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Conversation history" hitSlop={8} onPress={() => router.push('/coach/history' as Href)} style={styles.iconButton}>
          <MaterialIcons name="history" size={23} color={authColors.onSurfaceVariant} />
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={authColors.primary} /><Text style={styles.stateCopy}>Loading your conversations…</Text></View>
      ) : loadError ? (
        <View style={styles.center}>
          <MaterialIcons name="cloud-off" size={34} color={authColors.error} />
          <Text selectable style={styles.errorText}>{loadError}</Text>
          <Pressable accessibilityRole="button" onPress={() => void load()} style={styles.retryButton}><Text style={styles.retryButtonText}>Retry</Text></Pressable>
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={listData}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => <CoachMessage message={item} />}
          contentInsetAdjustmentBehavior="automatic"
          contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 16, paddingBottom: 18, gap: 12, flexGrow: 1 }}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          ListEmptyComponent={
            <View style={styles.welcome}>
              <View style={styles.welcomeIcon}><MaterialIcons name="auto-awesome" size={26} color={authColors.primary} /></View>
              <Text style={styles.welcomeTitle}>Your personal money coach</Text>
              <Text selectable style={styles.welcomeCopy}>Ask about your recorded spending, budgets, or savings goals. FinCoach uses your app data and trusted finance references.</Text>
            </View>
          }
          ListFooterComponent={isSending ? <View style={{ paddingTop: 12 }}><CoachTypingIndicator /></View> : null}
        />
      )}

      {sendError ? (
        <View accessibilityRole="alert" style={styles.errorBar}>
          <Text selectable style={styles.errorBarText}>{sendError}</Text>
          {retryContent ? <Pressable onPress={() => void send(retryContent)}><Text style={styles.errorAction}>Retry</Text></Pressable> : null}
        </View>
      ) : null}

      {showSuggestions ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.suggestions} keyboardShouldPersistTaps="handled">
          {SUGGESTIONS.map((suggestion) => (
            <Pressable key={suggestion} accessibilityRole="button" onPress={() => void send(suggestion)} style={styles.suggestionChip}>
              <Text style={styles.suggestionText}>{suggestion}</Text>
            </Pressable>
          ))}
        </ScrollView>
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
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Send message"
          disabled={!canSendCoachMessage(input, isSending)}
          onPress={() => void send()}
          style={({ pressed }) => [styles.sendButton, { opacity: canSendCoachMessage(input, isSending) ? (pressed ? 0.8 : 1) : 0.4 }]}>
          <MaterialIcons name="arrow-upward" size={23} color={authColors.onPrimary} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = {
  header: { minHeight: 70, paddingHorizontal: 16, paddingBottom: 9, flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const,
  headerAvatar: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary } as const,
  onlineDot: { position: 'absolute', right: 0, bottom: 0, width: 13, height: 13, borderRadius: 7, borderWidth: 2, borderColor: authColors.surfaceContainerLowest, backgroundColor: '#2E9B63' } as const,
  headerTitle: { color: authColors.onSurface, fontFamily: authFont.semibold, fontSize: 17, lineHeight: 21 } as const,
  onlineText: { color: '#2E8559', fontFamily: authFont.regular, fontSize: 12, lineHeight: 16 } as const,
  iconButton: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' } as const,
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 28 } as const,
  stateCopy: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 14 } as const,
  errorText: { color: authColors.error, fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, textAlign: 'center' } as const,
  retryButton: { borderRadius: 18, paddingHorizontal: 18, paddingVertical: 9, backgroundColor: authColors.primary } as const,
  retryButtonText: { color: authColors.onPrimary, fontFamily: authFont.semibold, fontSize: 13 } as const,
  welcome: { flex: 1, minHeight: 260, alignItems: 'center', justifyContent: 'center', gap: 10, paddingHorizontal: 28 } as const,
  welcomeIcon: { width: 58, height: 58, borderRadius: 29, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed } as const,
  welcomeTitle: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 19 } as const,
  welcomeCopy: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, textAlign: 'center' } as const,
  errorBar: { marginHorizontal: 16, marginBottom: 8, borderRadius: 14, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFF1F1' } as const,
  errorBarText: { flex: 1, color: authColors.error, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 } as const,
  errorAction: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 12 } as const,
  suggestions: { paddingHorizontal: 16, paddingBottom: 8, gap: 8 } as const,
  suggestionChip: { height: 36, justifyContent: 'center', borderRadius: 18, borderWidth: 1, borderColor: authColors.primaryFixedDim, paddingHorizontal: 14, backgroundColor: authColors.surfaceContainerLowest } as const,
  suggestionText: { color: authColors.primary, fontFamily: authFont.semibold, fontSize: 13 } as const,
  composerBar: { paddingHorizontal: 16, paddingTop: 9, flexDirection: 'row', alignItems: 'flex-end', gap: 9, borderTopWidth: 1, borderTopColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const,
  inputShell: { flex: 1, minHeight: 48, maxHeight: 110, justifyContent: 'center', borderRadius: 24, paddingHorizontal: 16, backgroundColor: authColors.surfaceContainerHigh } as const,
  input: { maxHeight: 96, paddingVertical: 11, color: authColors.onSurface, fontFamily: authFont.regular, fontSize: 15, lineHeight: 20 } as const,
  sendButton: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary } as const,
} as const;
