import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { createCoachConversation, deleteCoachConversation, listCoachConversations, renameCoachConversation } from '@/lib/coach-api';
import { coachErrorMessage, sortConversations } from '@/lib/coach-domain';
import { coachDeleteConfirmation, validateCoachTitle } from '@/lib/coach-ui';
import type { CoachConversation } from '@/lib/types';

export default function ConversationHistoryScreen() {
  const insets = useSafeAreaInsets();
  const [conversations, setConversations] = useState<CoachConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [titleError, setTitleError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setConversations(sortConversations(await listCoachConversations()));
    } catch (caught) {
      setError(coachErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);
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
  }, [title]);

  const confirmDelete = useCallback((conversation: CoachConversation) => {
    Alert.alert('Delete conversation?', coachDeleteConfirmation(conversation.title), [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          void deleteCoachConversation(conversation.id)
            .then(() => setConversations((current) => current.filter((item) => item.id !== conversation.id)))
            .catch((caught) => setError(coachErrorMessage(caught)));
        },
      },
    ]);
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 7 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => router.back()} style={styles.iconButton}>
          <MaterialIcons name="arrow-back" size={23} color={authColors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}><Text style={styles.title}>Conversations</Text><Text style={styles.subtitle}>Your saved coaching history</Text></View>
        <Pressable accessibilityRole="button" accessibilityLabel="New conversation" onPress={() => void create()} style={styles.newButton}>
          <MaterialIcons name="add" size={19} color={authColors.onPrimary} /><Text style={styles.newButtonText}>New</Text>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={authColors.primary} /><Text style={styles.copy}>Loading conversations…</Text></View>
      ) : (
        <ScrollView contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 28, gap: 10 }} keyboardShouldPersistTaps="handled">
          {error ? <View accessibilityRole="alert" style={styles.errorCard}><Text selectable style={styles.errorText}>{error}</Text><Pressable onPress={() => void load()}><Text style={styles.actionText}>Retry</Text></Pressable></View> : null}
          {conversations.length === 0 && !error ? (
            <View style={styles.empty}><MaterialIcons name="forum" size={36} color={authColors.primary} /><Text style={styles.emptyTitle}>No saved conversations</Text><Text style={styles.copy}>Start a new chat and it will appear here.</Text></View>
          ) : null}
          {conversations.map((conversation) => (
            <View key={conversation.id} style={styles.card}>
              {renamingId === conversation.id ? (
                <View style={{ flex: 1, gap: 6 }}>
                  <TextInput autoFocus value={title} maxLength={80} onChangeText={(value) => { setTitle(value); setTitleError(null); }} onSubmitEditing={() => void saveRename(conversation)} style={styles.renameInput} />
                  {titleError ? <Text selectable style={styles.validation}>{titleError}</Text> : null}
                  <View style={{ flexDirection: 'row', gap: 14 }}><Pressable onPress={() => void saveRename(conversation)}><Text style={styles.actionText}>Save</Text></Pressable><Pressable onPress={() => setRenamingId(null)}><Text style={styles.cancelText}>Cancel</Text></Pressable></View>
                </View>
              ) : (
                <Pressable accessibilityRole="button" onPress={() => open(conversation.id)} style={{ flex: 1, gap: 3 }}>
                  <Text numberOfLines={1} style={styles.cardTitle}>{conversation.title}</Text>
                  <Text style={[styles.dateText, { fontVariant: ['tabular-nums'] }]}>{new Date(conversation.last_message_at).toLocaleDateString('en-MY', { day: 'numeric', month: 'short', year: 'numeric' })}</Text>
                </Pressable>
              )}
              {renamingId !== conversation.id ? (
                <View style={{ flexDirection: 'row' }}>
                  <Pressable accessibilityRole="button" accessibilityLabel={`Rename ${conversation.title}`} hitSlop={7} onPress={() => { setRenamingId(conversation.id); setTitle(conversation.title); setTitleError(null); }} style={styles.smallIcon}><MaterialIcons name="edit" size={19} color={authColors.onSurfaceVariant} /></Pressable>
                  <Pressable accessibilityRole="button" accessibilityLabel={`Delete ${conversation.title}`} hitSlop={7} onPress={() => confirmDelete(conversation)} style={styles.smallIcon}><MaterialIcons name="delete-outline" size={20} color={authColors.error} /></Pressable>
                </View>
              ) : null}
            </View>
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
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 } as const,
  copy: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, textAlign: 'center' } as const,
  errorCard: { borderRadius: 15, padding: 13, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFF1F1' } as const,
  errorText: { flex: 1, color: authColors.error, fontFamily: authFont.regular, fontSize: 13, lineHeight: 18 } as const,
  actionText: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 13 } as const,
  cancelText: { color: authColors.onSurfaceVariant, fontFamily: authFont.semibold, fontSize: 13 } as const,
  empty: { minHeight: 260, alignItems: 'center', justifyContent: 'center', gap: 9, padding: 24 } as const,
  emptyTitle: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 17 } as const,
  card: { minHeight: 76, borderRadius: 18, padding: 15, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 1px 3px rgba(30, 25, 60, 0.08)', borderCurve: 'continuous' } as const,
  cardTitle: { color: authColors.onSurface, fontFamily: authFont.semibold, fontSize: 15 } as const,
  dateText: { color: authColors.outline, fontFamily: authFont.regular, fontSize: 12 } as const,
  smallIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' } as const,
  renameInput: { height: 40, borderRadius: 12, borderWidth: 1, borderColor: authColors.primary, paddingHorizontal: 11, color: authColors.onSurface, fontFamily: authFont.regular, fontSize: 14, backgroundColor: authColors.surfaceContainerLowest } as const,
  validation: { color: authColors.error, fontFamily: authFont.regular, fontSize: 11 } as const,
} as const;
