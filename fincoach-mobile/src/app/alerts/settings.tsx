import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TimePickerField } from '@/components/notifications/time-picker-field';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { ensureNotificationPreferences, saveNotificationPreferences } from '@/lib/alerts';
import { normalizeReminderTime } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import type { NotificationPreferences, SpendingFrequency } from '@/lib/types';

const weekdayOptions = [
  { value: 1, label: 'Mon' }, { value: 2, label: 'Tue' }, { value: 3, label: 'Wed' },
  { value: 4, label: 'Thu' }, { value: 5, label: 'Fri' }, { value: 6, label: 'Sat' },
  { value: 0, label: 'Sun' },
];

function normalizePreferenceTimes(preferences: NotificationPreferences): NotificationPreferences {
  return {
    ...preferences,
    savings_reminder_time: normalizeReminderTime(preferences.savings_reminder_time) ?? preferences.savings_reminder_time,
    spending_reminder_time: normalizeReminderTime(preferences.spending_reminder_time) ?? preferences.spending_reminder_time,
    default_bill_reminder_time: normalizeReminderTime(preferences.default_bill_reminder_time) ?? preferences.default_bill_reminder_time,
  };
}

export default function NotificationSettingsScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try { setPreferences(normalizePreferenceTimes(await ensureNotificationPreferences(userId))); }
    catch { setError('Could not load notification settings. Check your connection and try again.'); }
    finally { setLoading(false); }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  function update<K extends keyof NotificationPreferences>(key: K, value: NotificationPreferences[K]) {
    setPreferences((current) => current ? { ...current, [key]: value } : current);
  }

  async function save() {
    if (!userId || !preferences) return;
    const savingsTime = normalizeReminderTime(preferences.savings_reminder_time);
    const spendingTime = normalizeReminderTime(preferences.spending_reminder_time);
    const billTime = normalizeReminderTime(preferences.default_bill_reminder_time);
    if (!savingsTime || !spendingTime || !billTime) {
      Alert.alert('Check reminder times', 'Use 24-hour HH:MM format, for example 20:00.');
      return;
    }
    setSaving(true);
    try {
      const saved = await saveNotificationPreferences(userId, {
        budget_enabled: preferences.budget_enabled,
        savings_enabled: preferences.savings_enabled,
        savings_lead_days: preferences.savings_lead_days,
        savings_reminder_time: savingsTime,
        savings_milestones_enabled: preferences.savings_milestones_enabled,
        spending_enabled: preferences.spending_enabled,
        spending_frequency: preferences.spending_frequency,
        spending_weekday: preferences.spending_frequency === 'weekly' ? (preferences.spending_weekday ?? 1) : null,
        spending_reminder_time: spendingTime,
        bills_enabled: preferences.bills_enabled,
        default_bill_lead_days: preferences.default_bill_lead_days,
        default_bill_reminder_time: billTime,
        timezone: preferences.timezone,
      });
      setPreferences(normalizePreferenceTimes(saved));
      Alert.alert('Saved', 'Notification settings are synchronized across your devices.');
    } catch {
      Alert.alert('Could not save', 'Check your connection and try again.');
    } finally { setSaving(false); }
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={styles.roundButton}><MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} /></Pressable>
        <Text style={styles.heading}>Notification settings</Text>
        <View style={styles.roundButton} />
      </View>

      {loading ? <View style={styles.center}><ActivityIndicator color={authColors.primary} /><Text style={styles.helper}>Loading settings…</Text></View> : error || !preferences ? (
        <View style={styles.center}><MaterialIcons name="cloud-off" size={30} color={authColors.error} /><Text style={styles.error}>{error ?? 'Settings are unavailable.'}</Text><Pressable onPress={() => void load()} style={styles.primaryButton}><Text style={styles.primaryText}>Retry</Text></Pressable></View>
      ) : (
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: insets.bottom + 32, gap: 14 }}>
          <Text style={styles.intro}>Choose each notification type separately. These preferences sync through your FinCoach account.</Text>

          <SettingsCard icon="account-balance-wallet" color="#BA1A1A" title="Budget alerts" description="Warn at 80% and when a budget or category limit is exceeded." enabled={preferences.budget_enabled} onEnabled={(value) => update('budget_enabled', value)} />

          <SettingsCard icon="savings" color="#06A96B" title="Savings reminders" description="Deadline reminders and progress milestones." enabled={preferences.savings_enabled} onEnabled={(value) => update('savings_enabled', value)}>
            <SettingLine label="Remind before deadline"><DayStepper value={preferences.savings_lead_days} onChange={(value) => update('savings_lead_days', value)} /></SettingLine>
            <SettingLine label="Reminder time"><TimePickerField compact value={preferences.savings_reminder_time} onChange={(value) => update('savings_reminder_time', value)} /></SettingLine>
            <SettingLine label="Progress milestones" helper="25%, 50%, 75% and 100%"><Switch value={preferences.savings_milestones_enabled} onValueChange={(value) => update('savings_milestones_enabled', value)} trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }} thumbColor="#FFFFFF" /></SettingLine>
          </SettingsCard>

          <SettingsCard icon="insights" color="#8B5CF6" title="Spending check-ins" description="A short reminder to review and record spending." enabled={preferences.spending_enabled} onEnabled={(value) => update('spending_enabled', value)}>
            <Text style={styles.fieldLabel}>Frequency</Text>
            <View style={styles.segmentRow}>{(['daily', 'weekly'] as SpendingFrequency[]).map((value) => <Choice key={value} selected={preferences.spending_frequency === value} label={value === 'daily' ? 'Daily' : 'Weekly'} onPress={() => update('spending_frequency', value)} />)}</View>
            {preferences.spending_frequency === 'weekly' ? <><Text style={styles.fieldLabel}>Day</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7 }}>{weekdayOptions.map((day) => <Choice key={day.value} compact selected={preferences.spending_weekday === day.value} label={day.label} onPress={() => update('spending_weekday', day.value)} />)}</ScrollView></> : null}
            <SettingLine label="Reminder time"><TimePickerField compact value={preferences.spending_reminder_time} onChange={(value) => update('spending_reminder_time', value)} /></SettingLine>
          </SettingsCard>

          <SettingsCard icon="receipt-long" color="#F59E0B" title="Bill reminders" description="Default timing for bills you add to FinCoach." enabled={preferences.bills_enabled} onEnabled={(value) => update('bills_enabled', value)}>
            <SettingLine label="Default lead time"><DayStepper value={preferences.default_bill_lead_days} onChange={(value) => update('default_bill_lead_days', value)} /></SettingLine>
            <SettingLine label="Default reminder time"><TimePickerField compact value={preferences.default_bill_reminder_time} onChange={(value) => update('default_bill_reminder_time', value)} /></SettingLine>
            <Pressable onPress={() => router.push('/alerts/reminders' as never)} style={styles.manageButton}><Text style={styles.manageText}>Manage bill reminders</Text><MaterialIcons name="chevron-right" size={21} color={authColors.primary} /></Pressable>
          </SettingsCard>

          <Pressable disabled={saving} onPress={() => void save()} style={[styles.saveButton, saving && { opacity: 0.6 }]}>{saving ? <ActivityIndicator color="#FFFFFF" /> : <><MaterialIcons name="check" size={20} color="#FFFFFF" /><Text style={styles.saveText}>Save settings</Text></>}</Pressable>
        </ScrollView>
      )}
    </View>
  );
}

function SettingsCard({ icon, color, title, description, enabled, onEnabled, children }: { icon: keyof typeof MaterialIcons.glyphMap; color: string; title: string; description: string; enabled: boolean; onEnabled: (value: boolean) => void; children?: React.ReactNode }) {
  return <View style={styles.card}><View style={styles.cardHeader}><View style={[styles.cardIcon, { backgroundColor: `${color}1C` }]}><MaterialIcons name={icon} size={21} color={color} /></View><View style={{ flex: 1 }}><Text style={styles.cardTitle}>{title}</Text><Text style={styles.cardDescription}>{description}</Text></View><Switch value={enabled} onValueChange={onEnabled} trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }} thumbColor="#FFFFFF" /></View>{enabled && children ? <View style={styles.cardBody}>{children}</View> : null}</View>;
}

function SettingLine({ label, helper, children }: { label: string; helper?: string; children: React.ReactNode }) {
  return <View style={styles.settingLine}><View style={{ flex: 1 }}><Text style={styles.settingLabel}>{label}</Text>{helper ? <Text style={styles.settingHelper}>{helper}</Text> : null}</View>{children}</View>;
}

function DayStepper({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <View style={styles.stepper}><Pressable accessibilityLabel="Decrease days" onPress={() => onChange(Math.max(0, value - 1))} style={styles.stepButton}><MaterialIcons name="remove" size={18} color={authColors.primary} /></Pressable><Text style={styles.stepValue}>{value} day{value === 1 ? '' : 's'}</Text><Pressable accessibilityLabel="Increase days" onPress={() => onChange(Math.min(30, value + 1))} style={styles.stepButton}><MaterialIcons name="add" size={18} color={authColors.primary} /></Pressable></View>;
}

function Choice({ label, selected, onPress, compact = false }: { label: string; selected: boolean; onPress: () => void; compact?: boolean }) {
  return <Pressable onPress={onPress} style={[styles.choice, compact && { paddingHorizontal: 11 }, selected && styles.choiceActive]}><Text style={[styles.choiceText, selected && styles.choiceTextActive]}>{label}</Text></Pressable>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  intro: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, color: authColors.onSurfaceVariant, marginBottom: 2 },
  center: { margin: 20, padding: 28, borderRadius: 22, alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest },
  helper: { fontFamily: authFont.regular, color: authColors.onSurfaceVariant },
  error: { fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, color: authColors.error, textAlign: 'center' },
  card: { backgroundColor: authColors.surfaceContainerLowest, borderRadius: 22, padding: 16, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant, elevation: 2, shadowColor: '#1B1B23', shadowOpacity: 0.05, shadowOffset: { width: 0, height: 4 }, shadowRadius: 12 },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  cardIcon: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  cardTitle: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  cardDescription: { marginTop: 2, fontFamily: authFont.regular, fontSize: 12, lineHeight: 16, color: authColors.onSurfaceVariant },
  cardBody: { marginTop: 15, paddingTop: 14, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: authColors.outlineVariant, gap: 12 },
  settingLine: { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 12 },
  settingLabel: { fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurface },
  settingHelper: { marginTop: 1, fontFamily: authFont.regular, fontSize: 11, color: authColors.onSurfaceVariant },
  fieldLabel: { fontFamily: authFont.semibold, fontSize: 12, color: authColors.onSurfaceVariant },
  segmentRow: { flexDirection: 'row', gap: 8 },
  choice: { minHeight: 34, flex: 1, paddingHorizontal: 15, borderRadius: 17, alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest },
  choiceActive: { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed },
  choiceText: { fontFamily: authFont.semibold, fontSize: 12, textTransform: 'capitalize', color: authColors.onSurfaceVariant },
  choiceTextActive: { color: authColors.primary },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  stepButton: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  stepValue: { minWidth: 48, fontFamily: authFont.semibold, fontSize: 12, textAlign: 'center', color: authColors.onSurface },
  manageButton: { minHeight: 44, paddingHorizontal: 13, borderRadius: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: authColors.primaryFixed },
  manageText: { fontFamily: authFont.semibold, fontSize: 13, color: authColors.primary },
  primaryButton: { minHeight: 40, paddingHorizontal: 22, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary },
  primaryText: { fontFamily: authFont.semibold, color: authColors.onPrimary },
  saveButton: { height: 54, marginTop: 3, borderRadius: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: authColors.primary },
  saveText: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onPrimary },
});
