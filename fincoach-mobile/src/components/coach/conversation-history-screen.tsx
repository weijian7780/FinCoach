import { MaterialCommunityIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, View } from 'react-native';
import Animated, {
  FadeIn,
  FadeInUp,
  LinearTransition,
  useReducedMotion,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AnimatedPressable } from '@/components/ui/animated-pressable';
import { appDialog } from '@/components/ui/app-dialog';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { createCoachConversation, deleteCoachConversation, listCoachConversations, renameCoachConversation } from '@/lib/coach-api';
import { forgetCachedConversation, readCachedConversations, writeCachedConversations } from '@/lib/coach-cache';
import { coachErrorMessage, sortConversations } from '@/lib/coach-domain';
import { coachMotion } from '@/lib/coach-motion';
import { coachDeleteConfirmation, validateCoachTitle } from '@/lib/coach-ui';
import type { CoachConversation } from '@/lib/types';

export default function ConversationHistoryScreen() {
  const insets = useSafeAreaInsets();
  const reduceMotion = useReducedMotion();
  const userId = useAuth().session?.user.id ?? null;
  const [conversations, setConversationState] = useState<CoachConversation[]>(
    () => (userId ? readCachedConversations(userId) : null) ?? [],
  );
  const [loading, setLoading] = useState(() => !userId || !readCachedConversations(userId));
  const [error, setError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [titleError, setTitleError] = useState<string | null>(null);

  // The coach screen reads this cache to open a chat without waiting for the list.
  const setConversations = useCallback((update: (current: CoachConversation[]) => CoachConversation[]) => {
    setConversationState((current) => {
      const next = update(current);
      if (userId) writeCachedConversations(userId, next);
      return next;
    });
  }, [userId]);

  const load = useCallback(async () => {
    const cached = userId ? readCachedConversations(userId) : null;
    // Cached rows stay visible while the list refreshes.
    if (cached) setConversationState(cached);
    setLoading(!cached);
    setError(null);
    try {
      const saved = sortConversations(await listCoachConversations());
      setConversations(() => saved);
    } catch (caught) {
      setError(coachErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [setConversations, userId]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const open = useCallback((sessionId: string) => {
    router.replace({ pathname: '/coach', params: { sessionId } });
  }, []);

  const create = useCallback(async () => {
    try {
      open((await createCoachConversation()).id);
    } catch (caught) {
      setError(coachErrorMessage(caught));
    }
  }, [open]);

  const saveRename = useCallback(async (conversation: CoachConversation) => {
    const validation = validateCoachTitle(title);
    setTitleError(validation);
    if (validation) return;
    try {
      const updated = await renameCoachConversation(conversation.id, title);
      setConversations((current) => sortConversations(current.map((item) => item.id === updated.id ? updated : item)));
      setRenamingId(null);
    } catch (caught) {
      setTitleError(coachErrorMessage(caught));
    }
  }, [setConversations, title]);

  const confirmDelete = useCallback((conversation: CoachConversation) => {
    appDialog.open('Delete conversation?', coachDeleteConfirmation(conversation.title), [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          void deleteCoachConversation(conversation.id)
            .then(() => {
              if (userId) forgetCachedConversation(userId, conversation.id);
              setConversations((current) => current.filter((item) => item.id !== conversation.id));
            })
            .catch((caught) => setError(coachErrorMessage(caught)));
        },
      },
    ]);
  }, [setConversations, userId]);

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 7 }]}>
        <AnimatedPressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => router.back()} style={styles.iconButton}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={authColors.onSurface} />
        </AnimatedPressable>
        <View style={{ flex: 1 }}><Text style={styles.title}>Conversations</Text><Text style={styles.subtitle}>Your saved coaching history</Text></View>
        <AnimatedPressable accessibilityRole="button" accessibilityLabel="New conversation" onPress={() => void create()} style={styles.newButton}>
          <MaterialCommunityIcons name="plus" size={20} color={authColors.onPrimary} /><Text style={styles.newButtonText}>New</Text>
        </AnimatedPressable>
      </View>

      {loading ? (
        <View accessibilityLabel="Loading saved conversations" style={styles.loadingList}>
          {[0, 1, 2, 3].map((item) => (
            <View key={item} style={styles.skeletonCard}>
              <View style={{ flex: 1, gap: 10 }}>
                <View style={[styles.skeletonLine, { width: item % 2 === 0 ? '72%' : '58%' }]} />
                <View style={[styles.skeletonLine, styles.skeletonDate]} />
              </View>
              <View style={styles.skeletonAction} />
            </View>
          ))}
        </View>
      ) : (
        <ScrollView contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 28, gap: 10 }} keyboardShouldPersistTaps="handled">
          {error ? (
            <Animated.View
              accessibilityRole="alert"
              entering={reduceMotion ? undefined : FadeIn.duration(coachMotion.stateTransitionDuration)}
              style={styles.errorCard}>
              <View style={styles.errorIcon}>
                <MaterialCommunityIcons name="cloud-off-outline" size={22} color={authColors.error} />
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.errorTitle}>Couldn&apos;t load history</Text>
                <Text selectable style={styles.errorText}>{error}</Text>
              </View>
              <AnimatedPressable onPress={() => void load()} style={styles.retryAction}>
                <Text style={styles.actionText}>Retry</Text>
              </AnimatedPressable>
            </Animated.View>
          ) : null}
          {conversations.length === 0 && !error ? (
            <Animated.View
              entering={reduceMotion ? undefined : FadeIn.duration(coachMotion.stateTransitionDuration)}
              style={styles.empty}>
              <View style={styles.emptyIcon}>
                <MaterialCommunityIcons name="forum-outline" size={31} color={authColors.primary} />
              </View>
              <Text style={styles.emptyTitle}>No saved conversations</Text>
              <Text style={styles.copy}>Ask FinCoach a question and your conversation will be saved here automatically.</Text>
              <AnimatedPressable accessibilityRole="button" onPress={() => void create()} style={styles.emptyButton}>
                <MaterialCommunityIcons name="plus" size={18} color={authColors.onPrimary} />
                <Text style={styles.emptyButtonText}>Start a conversation</Text>
              </AnimatedPressable>
            </Animated.View>
          ) : null}
          {conversations.map((conversation, index) => (
            <Animated.View
              entering={reduceMotion ? undefined : FadeInUp
                .duration(coachMotion.messageEnterDuration)
                .delay(Math.min(index, 5) * coachMotion.sourceStagger)}
              key={conversation.id}
              layout={reduceMotion ? undefined : LinearTransition.duration(coachMotion.stateTransitionDuration)}
              style={styles.card}>
              {renamingId === conversation.id ? (
                <View style={{ flex: 1, gap: 6 }}>
                  <TextInput autoFocus value={title} maxLength={80} onChangeText={(value) => { setTitle(value); setTitleError(null); }} onSubmitEditing={() => void saveRename(conversation)} style={styles.renameInput} />
                  {titleError ? <Text selectable style={styles.validation}>{titleError}</Text> : null}
                  <View style={{ flexDirection: 'row', gap: 14 }}><AnimatedPressable onPress={() => void saveRename(conversation)}><Text style={styles.actionText}>Save</Text></AnimatedPressable><AnimatedPressable onPress={() => setRenamingId(null)}><Text style={styles.cancelText}>Cancel</Text></AnimatedPressable></View>
                </View>
              ) : (
                <AnimatedPressable accessibilityRole="button" onPress={() => open(conversation.id)} style={{ flex: 1, gap: 3 }}>
                  <Text numberOfLines={1} style={styles.cardTitle}>{conversation.title}</Text>
                  <Text style={[styles.dateText, { fontVariant: ['tabular-nums'] }]}>{new Date(conversation.last_message_at).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' })}</Text>
                </AnimatedPressable>
              )}
              {renamingId !== conversation.id ? (
                <View style={{ flexDirection: 'row' }}>
                  <AnimatedPressable accessibilityRole="button" accessibilityLabel={`Rename ${conversation.title}`} hitSlop={7} onPress={() => { setRenamingId(conversation.id); setTitle(conversation.title); setTitleError(null); }} style={styles.smallIcon}><MaterialCommunityIcons name="pencil-outline" size={20} color={authColors.onSurfaceVariant} /></AnimatedPressable>
                  <AnimatedPressable accessibilityRole="button" accessibilityLabel={`Delete ${conversation.title}`} hitSlop={7} onPress={() => confirmDelete(conversation)} style={styles.smallIcon}><MaterialCommunityIcons name="trash-can-outline" size={21} color={authColors.error} /></AnimatedPressable>
                </View>
              ) : null}
            </Animated.View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = {
  header: { minHeight: 72, paddingHorizontal: 14, paddingBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const,
  iconButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' } as const,
  title: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 19 } as const,
  subtitle: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 12 } as const,
  newButton: { height: 38, borderRadius: 19, paddingHorizontal: 13, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: authColors.primary } as const,
  newButtonText: { color: authColors.onPrimary, fontFamily: authFont.semibold, fontSize: 13 } as const,
  loadingList: { padding: 16, gap: 10 } as const,
  skeletonCard: { minHeight: 76, borderRadius: 18, padding: 15, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest } as const,
  skeletonLine: { height: 12, borderRadius: 6, backgroundColor: authColors.surfaceContainerHigh } as const,
  skeletonDate: { width: '36%', height: 9 } as const,
  skeletonAction: { width: 32, height: 32, borderRadius: 16, backgroundColor: authColors.surfaceContainerHigh } as const,
  copy: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, textAlign: 'center' } as const,
  errorCard: { borderRadius: 18, padding: 13, flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderColor: '#F6C5C5', backgroundColor: '#FFF1F1' } as const,
  errorIcon: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest } as const,
  errorTitle: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 13, lineHeight: 17 } as const,
  errorText: { color: authColors.error, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 } as const,
  retryAction: { minHeight: 34, justifyContent: 'center', borderRadius: 17, paddingHorizontal: 11, backgroundColor: authColors.surfaceContainerLowest } as const,
  actionText: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 13 } as const,
  cancelText: { color: authColors.onSurfaceVariant, fontFamily: authFont.semibold, fontSize: 13 } as const,
  empty: { minHeight: 260, alignItems: 'center', justifyContent: 'center', gap: 9, padding: 24 } as const,
  emptyIcon: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed } as const,
  emptyTitle: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 17 } as const,
  emptyButton: { minHeight: 42, marginTop: 6, borderRadius: 21, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: authColors.primary } as const,
  emptyButtonText: { color: authColors.onPrimary, fontFamily: authFont.semibold, fontSize: 13 } as const,
  card: { minHeight: 76, borderRadius: 18, padding: 15, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 1px 3px rgba(30, 25, 60, 0.08)', borderCurve: 'continuous' } as const,
  cardTitle: { color: authColors.onSurface, fontFamily: authFont.semibold, fontSize: 15 } as const,
  dateText: { color: authColors.outline, fontFamily: authFont.regular, fontSize: 12 } as const,
  smallIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' } as const,
  renameInput: { height: 40, borderRadius: 12, borderWidth: 1, borderColor: authColors.primary, paddingHorizontal: 11, color: authColors.onSurface, fontFamily: authFont.regular, fontSize: 14, backgroundColor: authColors.surfaceContainerLowest } as const,
  validation: { color: authColors.error, fontFamily: authFont.regular, fontSize: 11 } as const,
} as const;
