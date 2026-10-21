import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { fetchReminders, setReminderEnabled } from '@/lib/alerts';
import { formatReminderDue, groupUpcomingReminders } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import type { BillReminder, ReminderRecurrence } from '@/lib/types';

function formatMoney(amount: number | null) {
  if (amount == null) return null;
  return `RM ${amount.toLocaleString('en-MY', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function recurrenceLabel(value: ReminderRecurrence) {
  if (value === 'none') return null;
  return value[0].toUpperCase() + value.slice(1);
}

export function RemindersListScreen() {
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
    try {
      setItems(await fetchReminders(userId));
    } catch {
      setError('Could not load reminders. Check your connection and try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const grouped = useMemo(() => groupUpcomingReminders(items), [items]);
  const upcomingCount = items.filter((item) => item.enabled).length;

  const toggle = useCallback(async (item: BillReminder, enabled: boolean) => {
    if (!userId) return;
    setItems((current) => current.map((value) => value.id === item.id ? { ...value, enabled } : value));
    try {
      await setReminderEnabled(item.id, userId, enabled);
    } catch {
      void load(true);
    }
  }, [load, userId]);

  const openReminder = useCallback((item?: BillReminder) => {
    if (item) {
      router.push({ pathname: '/alerts/reminders/manage', params: { id: item.id } } as never);
      return;
    }
    router.push('/alerts/reminders/manage' as never);
  }, []);

  const renderGroup = (title: string, data: BillReminder[], highlightFirst = false) => {
    if (data.length === 0) return null;
    return (
      <View style={styles.group}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {data.map((item, index) => (
          <ReminderRow
            key={item.id}
            item={item}
            highlighted={highlightFirst && index === 0}
            onOpen={() => openReminder(item)}
            onToggle={(value) => void toggle(item, value)}
          />
        ))}
      </View>
    );
  };

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" hitSlop={8} onPress={() => router.back()} style={styles.roundButton}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={styles.heading}>Reminders</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="Add reminder" onPress={() => openReminder()} style={styles.addAction}>
          <MaterialIcons name="add" size={20} color={authColors.onPrimary} />
          <Text style={styles.addActionText}>Add</Text>
        </Pressable>
      </View>

      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={authColors.primary} />}
        contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 22, paddingBottom: insets.bottom + 30, gap: 18 }}
        showsVerticalScrollIndicator={false}>
        <View style={styles.summaryRow}>
          <MaterialIcons name="calendar-today" size={20} color={authColors.primary} />
          <Text style={styles.summaryText}>{upcomingCount} upcoming</Text>
        </View>

        {loading ? (
          <View style={styles.state}><ActivityIndicator color={authColors.primary} /><Text style={styles.stateBody}>Loading reminders…</Text></View>
        ) : error ? (
          <View style={styles.state}>
            <MaterialIcons name="cloud-off" size={29} color={authColors.error} />
            <Text accessibilityRole="alert" style={styles.error}>{error}</Text>
            <Pressable onPress={() => void load()} style={styles.retry}><Text style={styles.retryText}>Retry</Text></Pressable>
          </View>
        ) : items.length === 0 ? (
          <View style={styles.state}>
            <View style={styles.emptyIcon}><MaterialIcons name="notifications-none" size={28} color={authColors.primary} /></View>
            <Text style={styles.emptyTitle}>No reminders yet</Text>
            <Text style={styles.stateBody}>Add a payment, deadline, or anything you do not want to forget.</Text>
            <Pressable onPress={() => openReminder()} style={styles.primaryButton}>
              <MaterialIcons name="add" size={19} color={authColors.onPrimary} />
              <Text style={styles.primaryText}>Add reminder</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {renderGroup('Next up', grouped.nextUp, true)}
            {renderGroup('This week', grouped.thisWeek)}
            {renderGroup('Later', grouped.later)}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function ReminderRow({
  item,
  highlighted,
  onOpen,
  onToggle,
}: {
  item: BillReminder;
  highlighted: boolean;
  onOpen: () => void;
  onToggle: (enabled: boolean) => void;
}) {
  const amount = formatMoney(item.amount);
  const repeat = recurrenceLabel(item.recurrence);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Edit ${item.title}`}
      onPress={onOpen}
      style={({ pressed }) => [styles.card, highlighted && styles.nextCard, pressed && styles.pressed]}>
      <View style={[styles.cardIcon, highlighted && styles.nextCardIcon]}>
        <MaterialIcons name={highlighted ? 'event-available' : 'schedule'} size={22} color={authColors.primary} />
      </View>
      <View style={styles.cardContent}>
        <Text numberOfLines={1} style={styles.cardTitle}>{item.title}</Text>
        <Text style={styles.cardDue}>{formatReminderDue(item.due_at)}</Text>
        {amount || repeat ? <View style={styles.detailRow}>
          {amount ? <Text style={styles.cardDetail}>{amount}</Text> : null}
          {amount && repeat ? <View style={styles.dot} /> : null}
          {repeat ? <><MaterialIcons name="repeat" size={14} color={authColors.onSurfaceVariant} /><Text style={styles.cardDetail}>{repeat}</Text></> : null}
        </View> : null}
      </View>
      <View style={styles.cardActions}>
        <Switch
          accessibilityLabel={`${item.enabled ? 'Disable' : 'Enable'} ${item.title}`}
          value={item.enabled}
          onValueChange={onToggle}
          trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }}
          thumbColor="#FFFFFF"
        />
        <MaterialIcons name="chevron-right" size={20} color={authColors.outline} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 19, color: authColors.onSurface },
  addAction: { minHeight: 40, paddingHorizontal: 12, borderRadius: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, backgroundColor: authColors.primary },
  addActionText: { fontFamily: authFont.semibold, fontSize: 13, color: authColors.onPrimary },
  summaryRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  summaryText: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  group: { gap: 10 },
  sectionTitle: { fontFamily: authFont.bold, fontSize: 11, lineHeight: 16, letterSpacing: 0.8, textTransform: 'uppercase', color: authColors.primary },
  card: { minHeight: 94, padding: 15, borderRadius: 22, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  nextCard: { borderColor: '#B8B6FF', backgroundColor: '#FBFAFF' },
  pressed: { opacity: 0.82 },
  cardIcon: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  nextCardIcon: { backgroundColor: '#ECEBFF' },
  cardContent: { flex: 1, gap: 3 },
  cardTitle: { fontFamily: authFont.semibold, fontSize: 16, lineHeight: 21, color: authColors.onSurface },
  cardDue: { fontFamily: authFont.semibold, fontSize: 13, color: authColors.primary },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  dot: { width: 3, height: 3, borderRadius: 2, backgroundColor: authColors.outline },
  cardDetail: { fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant },
  cardActions: { alignItems: 'flex-end', gap: 2 },
  state: { padding: 28, borderRadius: 22, alignItems: 'center', gap: 10, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  emptyIcon: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  emptyTitle: { fontFamily: authFont.semibold, fontSize: 17, color: authColors.onSurface },
  stateBody: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, textAlign: 'center', color: authColors.onSurfaceVariant },
  error: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, textAlign: 'center', color: authColors.error },
  retry: { height: 40, paddingHorizontal: 22, borderRadius: 20, justifyContent: 'center', backgroundColor: authColors.primary },
  retryText: { fontFamily: authFont.semibold, color: authColors.onPrimary },
  primaryButton: { minHeight: 44, paddingHorizontal: 18, borderRadius: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: authColors.primary },
  primaryText: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary },
});
