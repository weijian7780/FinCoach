import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { RemindersListScreen } from '@/components/notifications/reminders-list-screen';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { fetchReminders, setReminderEnabled } from '@/lib/alerts';
import { useAuth } from '@/lib/auth-context';
import type { BillReminder } from '@/lib/types';

function formatMoney(amount: number | null) {
  return amount == null ? 'Amount not set' : `RM ${amount.toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDue(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Invalid date';
  return new Intl.DateTimeFormat('en-MY', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
}

export default function BillRemindersScreen() {
  return <RemindersListScreen />;
}

// Kept temporarily as the pre-redesign implementation reference while the
// dedicated reminder list component is adopted by this route.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function LegacyBillRemindersScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [items, setItems] = useState<BillReminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    if (!userId) return;
    if (refresh) setRefreshing(true); else setLoading(true);
    setError(null);
    try { setItems(await fetchReminders(userId)); }
    catch { setError('Could not load bill reminders. Check your connection and try again.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  async function toggle(item: BillReminder, enabled: boolean) {
    if (!userId) return;
    setItems((current) => current.map((value) => value.id === item.id ? { ...value, enabled } : value));
    try { await setReminderEnabled(item.id, userId, enabled); }
    catch { void load(true); }
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={styles.roundButton}><MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} /></Pressable>
        <Text style={styles.heading}>Bill reminders</Text>
        <Pressable accessibilityLabel="Add bill reminder" onPress={() => router.push('/alerts/reminders/manage' as never)} style={styles.addButton}><MaterialIcons name="add" size={22} color={authColors.onPrimary} /></Pressable>
      </View>

      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={authColors.primary} />} contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 10, paddingBottom: insets.bottom + 30, gap: 12 }}>
        <View style={styles.introRow}><View><Text style={styles.title}>Upcoming bill reminders</Text><Text style={styles.subtitle}>Manage due dates and recurring payments.</Text></View></View>
        {loading ? <View style={styles.state}><ActivityIndicator color={authColors.primary} /><Text style={styles.subtitle}>Loading reminders…</Text></View> : error ? <View style={styles.state}><MaterialIcons name="cloud-off" size={29} color={authColors.error} /><Text style={styles.error}>{error}</Text><Pressable onPress={() => void load()} style={styles.retry}><Text style={styles.retryText}>Retry</Text></Pressable></View> : items.length === 0 ? <View style={styles.state}><View style={styles.emptyIcon}><MaterialIcons name="receipt-long" size={28} color={authColors.primary} /></View><Text style={styles.emptyTitle}>No bill reminders yet</Text><Text style={styles.stateBody}>Add rent, subscriptions, utilities or any payment you do not want to miss.</Text><Pressable onPress={() => router.push('/alerts/reminders/manage' as never)} style={styles.primaryButton}><MaterialIcons name="add" size={19} color="#FFFFFF" /><Text style={styles.primaryText}>Add reminder</Text></Pressable></View> : items.map((item) => (
          <Pressable key={item.id} onPress={() => router.push({ pathname: '/alerts/reminders/manage', params: { id: item.id } } as never)} style={({ pressed }) => [styles.card, pressed && { opacity: 0.82 }]}>
            <View style={styles.cardIcon}><MaterialIcons name="schedule" size={21} color="#F59E0B" /></View>
            <View style={{ flex: 1, gap: 3 }}><Text numberOfLines={1} style={styles.cardTitle}>{item.title}</Text><Text style={styles.cardMeta}>{formatMoney(item.amount)} · {item.recurrence === 'none' ? 'One time' : item.recurrence}</Text><Text style={styles.cardDue}>Due {formatDue(item.due_at)}</Text></View>
            <Switch accessibilityLabel={`${item.enabled ? 'Disable' : 'Enable'} ${item.title}`} value={item.enabled} onValueChange={(value) => void toggle(item, value)} trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }} thumbColor="#FFFFFF" />
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  addButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary },
  introRow: { marginBottom: 4 },
  title: { fontFamily: authFont.bold, fontSize: 22, color: authColors.onSurface },
  subtitle: { marginTop: 2, fontFamily: authFont.regular, fontSize: 13, lineHeight: 18, color: authColors.onSurfaceVariant },
  card: { minHeight: 94, padding: 16, borderRadius: 22, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant, elevation: 2, shadowColor: '#1B1B23', shadowOpacity: 0.05, shadowOffset: { width: 0, height: 4 }, shadowRadius: 12 },
  cardIcon: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F59E0B1C' },
  cardTitle: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  cardMeta: { fontFamily: authFont.regular, fontSize: 12, textTransform: 'capitalize', color: authColors.onSurfaceVariant },
  cardDue: { fontFamily: authFont.semibold, fontSize: 11, color: authColors.primary },
  state: { marginTop: 10, padding: 28, borderRadius: 22, alignItems: 'center', gap: 10, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  emptyIcon: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  emptyTitle: { fontFamily: authFont.semibold, fontSize: 17, color: authColors.onSurface },
  stateBody: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, textAlign: 'center', color: authColors.onSurfaceVariant },
  error: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, textAlign: 'center', color: authColors.error },
  retry: { height: 40, paddingHorizontal: 22, borderRadius: 20, justifyContent: 'center', backgroundColor: authColors.primary },
  retryText: { fontFamily: authFont.semibold, color: authColors.onPrimary },
  primaryButton: { height: 44, paddingHorizontal: 18, borderRadius: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: authColors.primary },
  primaryText: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary },
});
