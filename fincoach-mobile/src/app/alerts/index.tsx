import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SectionList, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AlertCard } from '@/components/notifications/alert-card';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { dismissAlert, fetchAlerts, markAlertRead, markAllAlertsRead } from '@/lib/alerts';
import { filterAlerts, groupAlertsByDate, routeForAlert } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import { loadNotificationSdk, openNotificationSettings } from '@/lib/notification-platform';
import { supabase } from '@/lib/supabase';
import type { AlertFilter, AlertRecord } from '@/lib/types';

const filters: { value: AlertFilter; label: 'All' | 'Insights' | 'Alerts' }[] = [
  { value: 'all', label: 'All' },
  { value: 'insights', label: 'Insights' },
  { value: 'alerts', label: 'Alerts' },
];

function loadErrorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('alerts') || message.includes('schema cache')) {
    return 'Alert database setup is not installed yet. Run the Alert and Reminder migration in Supabase, then retry.';
  }
  return 'Could not load alerts. Check your connection and try again.';
}

export default function AlertsScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [items, setItems] = useState<AlertRecord[]>([]);
  const [filter, setFilter] = useState<AlertFilter>('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async (refresh = false) => {
    if (!userId) return;
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [alerts, sdk] = await Promise.all([fetchAlerts(userId), loadNotificationSdk().catch(() => null)]);
      setItems(alerts);
      if (sdk) {
        const permission = await sdk.getPermissionsAsync();
        setPermissionDenied(permission.status === 'denied');
      }
    } catch (cause) {
      setError(loadErrorMessage(cause));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  useFocusEffect(useCallback(() => {
    if (!userId) return;
    const channel = supabase
      .channel(`alerts-inbox-${userId}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'alerts', filter: `user_id=eq.${userId}` }, () => {
        void load(true);
      })
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [load, userId]));

  const visible = useMemo(() => filterAlerts(items, filter), [filter, items]);
  const grouped = useMemo(() => groupAlertsByDate(visible), [visible]);
  const sections = useMemo(() => [
    { title: 'Today', data: grouped.today },
    { title: 'Yesterday', data: grouped.yesterday },
    { title: 'Earlier', data: grouped.earlier },
  ].filter((section) => section.data.length > 0), [grouped]);
  const unreadCount = items.filter((item) => !item.read_at).length;

  const openAlert = useCallback(async (item: AlertRecord) => {
    if (!userId) return;
    if (!item.read_at) {
      setItems((current) => current.map((value) => value.id === item.id ? { ...value, read_at: new Date().toISOString() } : value));
      try { await markAlertRead(item.id, userId); } catch { void load(true); }
    }
    router.push(routeForAlert(item) as never);
  }, [load, userId]);

  const dismiss = useCallback(async (item: AlertRecord) => {
    if (!userId) return;
    setItems((current) => current.filter((value) => value.id !== item.id));
    try { await dismissAlert(item.id, userId); } catch { void load(true); }
  }, [load, userId]);

  const markAll = useCallback(async () => {
    if (!userId || unreadCount === 0) return;
    const timestamp = new Date().toISOString();
    setItems((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? timestamp })));
    try { await markAllAlertsRead(userId); } catch { void load(true); }
  }, [load, unreadCount, userId]);

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" hitSlop={8} onPress={() => router.back()} style={styles.roundButton}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={styles.heading}>Alerts</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="Notification settings" hitSlop={8} onPress={() => router.push('/alerts/settings' as never)} style={styles.roundButton}>
          <MaterialIcons name="settings" size={22} color={authColors.onSurfaceVariant} />
        </Pressable>
      </View>

      <View style={styles.filtersRow}>
        <View style={styles.filters}>
          {filters.map((item) => (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ selected: filter === item.value }}
              key={item.value}
              onPress={() => setFilter(item.value)}
              style={[styles.chip, filter === item.value && styles.chipActive]}>
              <Text style={[styles.chipText, filter === item.value && styles.chipTextActive]}>{item.label}</Text>
            </Pressable>
          ))}
        </View>
        {unreadCount > 0 ? <Pressable onPress={() => void markAll()} hitSlop={8}><Text style={styles.markAll}>Mark all read</Text></Pressable> : null}
      </View>

      {permissionDenied ? (
        <Pressable onPress={() => void openNotificationSettings()} style={styles.permissionCard}>
          <MaterialIcons name="notifications-off" size={20} color={authColors.error} />
          <View style={{ flex: 1 }}>
            <Text style={styles.permissionTitle}>Phone notifications are off</Text>
            <Text style={styles.permissionBody}>Alerts still appear here. Tap to enable phone notifications.</Text>
          </View>
          <MaterialIcons name="chevron-right" size={22} color={authColors.onSurfaceVariant} />
        </Pressable>
      ) : null}

      {loading ? (
        <View style={styles.centerState}><ActivityIndicator color={authColors.primary} /><Text style={styles.stateBody}>Loading alerts…</Text></View>
      ) : error ? (
        <View style={styles.centerState}>
          <View style={styles.stateIcon}><MaterialIcons name="cloud-off" size={27} color={authColors.error} /></View>
          <Text accessibilityRole="alert" style={styles.stateTitle}>Could not load alerts</Text>
          <Text style={styles.stateBody}>{error}</Text>
          <Pressable onPress={() => void load()} style={styles.retryButton}><Text style={styles.retryText}>Retry</Text></Pressable>
        </View>
      ) : sections.length === 0 ? (
        <View style={styles.centerState}>
          <View style={styles.emptyIcon}><MaterialIcons name="notifications-none" size={28} color={authColors.primary} /></View>
          <Text style={styles.stateTitle}>{filter === 'all' ? 'You are all caught up' : `No ${filter} yet`}</Text>
          <Text style={styles.stateBody}>Budget warnings, savings updates and reminders will appear here.</Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => item.id}
          renderSectionHeader={({ section }) => <Text style={styles.sectionTitle}>{section.title}</Text>}
          renderItem={({ item }) => <AlertCard alert={item} onOpen={() => void openAlert(item)} onDismiss={() => void dismiss(item)} />}
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          SectionSeparatorComponent={() => <View style={{ height: 8 }} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={authColors.primary} />}
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 6, paddingBottom: insets.bottom + 28 }}
          stickySectionHeadersEnabled={false}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, lineHeight: 24, color: authColors.onSurface },
  filtersRow: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 14, gap: 10 },
  filters: { flexDirection: 'row', gap: 8 },
  chip: { height: 36, paddingHorizontal: 16, borderRadius: 18, justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  chipActive: { backgroundColor: authColors.primary, borderColor: authColors.primary },
  chipText: { fontFamily: authFont.semibold, fontSize: 13, color: authColors.onSurfaceVariant },
  chipTextActive: { color: authColors.onPrimary },
  markAll: { alignSelf: 'flex-end', fontFamily: authFont.semibold, fontSize: 12, color: authColors.primary },
  permissionCard: { marginHorizontal: 20, marginBottom: 12, padding: 13, borderRadius: 16, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFF1F0', borderWidth: StyleSheet.hairlineWidth, borderColor: '#F2B8B5' },
  permissionTitle: { fontFamily: authFont.semibold, fontSize: 13, color: authColors.onSurface },
  permissionBody: { marginTop: 2, fontFamily: authFont.regular, fontSize: 12, lineHeight: 16, color: authColors.onSurfaceVariant },
  sectionTitle: { paddingTop: 10, paddingBottom: 9, fontFamily: authFont.bold, fontSize: 11, lineHeight: 16, letterSpacing: 0.7, textTransform: 'uppercase', color: authColors.onSurfaceVariant },
  centerState: { margin: 20, padding: 28, borderRadius: 22, alignItems: 'center', gap: 10, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  stateIcon: { width: 50, height: 50, borderRadius: 25, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFF1F0' },
  emptyIcon: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  stateTitle: { fontFamily: authFont.semibold, fontSize: 17, color: authColors.onSurface, textAlign: 'center' },
  stateBody: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, color: authColors.onSurfaceVariant, textAlign: 'center' },
  retryButton: { minHeight: 40, paddingHorizontal: 22, borderRadius: 20, justifyContent: 'center', backgroundColor: authColors.primary },
  retryText: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary },
});
