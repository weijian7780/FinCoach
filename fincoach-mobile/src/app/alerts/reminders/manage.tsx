import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TimePickerField } from '@/components/notifications/time-picker-field';
import { DateField } from '@/components/savings/date-field';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { createReminder, deleteReminder, ensureNotificationPreferences, fetchReminder, updateReminder } from '@/lib/alerts';
import { validateBillReminderInput } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import { todayIsoDate } from '@/lib/savings-domain';
import type { ReminderRecurrence } from '@/lib/types';

const recurrenceOptions: { value: ReminderRecurrence; label: 'Once' | 'Weekly' | 'Monthly' | 'Yearly' }[] = [
  { value: 'none', label: 'Once' }, { value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' }, { value: 'yearly', label: 'Yearly' },
];

function localParts(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { date: '', time: '09:00' };
  return {
    date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
    time: `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`,
  };
}

function toIso(dateValue: string, timeValue: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue);
  const time = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(timeValue);
  if (!match || !time) return '';
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(time[1]), Number(time[2]), 0, 0).toISOString();
}

export default function ManageBillReminderScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ id?: string }>();
  const reminderId = typeof params.id === 'string' ? params.id : undefined;
  const { session } = useAuth();
  const userId = session?.user.id;
  const [title, setTitle] = useState('');
  const [amount, setAmount] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [dueTime, setDueTime] = useState('09:00');
  const [leadDays, setLeadDays] = useState(3);
  const [recurrence, setRecurrence] = useState<ReminderRecurrence>('none');
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(Boolean(reminderId));
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const [existing, preferences] = await Promise.all([
        reminderId ? fetchReminder(reminderId, userId) : Promise.resolve(null),
        ensureNotificationPreferences(userId),
      ]);
      if (existing) {
        const parts = localParts(existing.due_at);
        setTitle(existing.title);
        setAmount(existing.amount == null ? '' : String(existing.amount));
        setDueDate(parts.date);
        setDueTime(parts.time);
        setLeadDays(existing.lead_days);
        setRecurrence(existing.recurrence);
        setEnabled(existing.enabled);
      } else {
        setLeadDays(preferences.default_bill_lead_days);
        setDueTime(preferences.default_bill_reminder_time.slice(0, 5));
      }
    } catch {
      Alert.alert('Could not load reminder', 'Check your connection and try again.');
    } finally { setLoading(false); }
  }, [reminderId, userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  async function save() {
    if (!userId) return;
    const dueAt = toIso(dueDate, dueTime);
    const validation = validateBillReminderInput({ title, amount, dueAt, leadDays, recurrence });
    setErrors(validation);
    if (Object.keys(validation).length > 0) return;
    const day = Number(dueDate.slice(8, 10));
    const input = { title, amount: amount.trim() ? Number(amount) : null, due_at: dueAt, lead_days: leadDays, recurrence, recurrence_anchor_day: day, enabled };
    setSaving(true);
    try {
      if (reminderId) await updateReminder(reminderId, userId, input);
      else await createReminder(userId, input);
      router.back();
    } catch {
      Alert.alert('Could not save reminder', 'Check the fields and your connection, then try again.');
    } finally { setSaving(false); }
  }

  function remove() {
    if (!reminderId || !userId) return;
    Alert.alert('Delete reminder?', 'This permanently removes the bill reminder.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => void (async () => { try { await deleteReminder(reminderId, userId); router.back(); } catch { Alert.alert('Could not delete', 'Check your connection and try again.'); } })() },
    ]);
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={styles.roundButton}><MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} /></Pressable>
        <Text style={styles.heading}>{reminderId ? 'Edit bill reminder' : 'New bill reminder'}</Text>
        <View style={styles.roundButton} />
      </View>
      {loading ? <View style={styles.center}><ActivityIndicator color={authColors.primary} /><Text style={styles.helper}>Loading reminder…</Text></View> : (
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: insets.bottom + 32, gap: 16 }}>
          <View style={styles.tip}><View style={styles.tipIcon}><MaterialIcons name="schedule" size={23} color={authColors.primary} /></View><View style={{ flex: 1 }}><Text style={styles.tipTitle}>Never miss a payment</Text><Text style={styles.tipBody}>FinCoach will alert you before the bill is due on each signed-in device.</Text></View></View>

          <Field label="Bill name" error={errors.title}><TextInput value={title} onChangeText={setTitle} placeholder="e.g. Room rental" placeholderTextColor={authColors.outline} maxLength={100} style={[styles.input, errors.title && styles.inputError]} /></Field>
          <Field label="Amount (optional)" error={errors.amount}><View style={[styles.input, styles.amountField, errors.amount && styles.inputError]}><Text style={styles.prefix}>RM</Text><TextInput value={amount} onChangeText={(value) => setAmount(value.replace(/[^0-9.]/g, ''))} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={authColors.outline} style={styles.amountInput} /></View></Field>
          <DateField label="Due date" value={dueDate} onChange={setDueDate} minimumDate={todayIsoDate()} placeholder="Choose due date" error={errors.dueAt} />
          <Field label="Reminder time" error={!dueDate && errors.dueAt ? undefined : errors.dueAt}><TimePickerField value={dueTime} onChange={setDueTime} hasError={Boolean(errors.dueAt)} /></Field>

          <View style={styles.card}><View style={styles.settingRow}><View><Text style={styles.settingTitle}>Remind me before</Text><Text style={styles.helper}>0 means on the due date</Text></View><View style={styles.stepper}><Pressable onPress={() => setLeadDays((value) => Math.max(0, value - 1))} style={styles.stepButton}><MaterialIcons name="remove" size={18} color={authColors.primary} /></Pressable><Text style={styles.stepValue}>{leadDays} day{leadDays === 1 ? '' : 's'}</Text><Pressable onPress={() => setLeadDays((value) => Math.min(365, value + 1))} style={styles.stepButton}><MaterialIcons name="add" size={18} color={authColors.primary} /></Pressable></View></View>{errors.leadDays ? <Text style={styles.error}>{errors.leadDays}</Text> : null}</View>

          <View style={styles.card}><Text style={styles.settingTitle}>Repeat</Text><Text style={styles.helper}>Monthly reminders keep the original day where possible.</Text><View style={styles.recurrenceRow}>{recurrenceOptions.map((option) => <Pressable key={option.value} onPress={() => setRecurrence(option.value)} style={[styles.choice, recurrence === option.value && styles.choiceActive]}><Text style={[styles.choiceText, recurrence === option.value && styles.choiceTextActive]}>{option.label}</Text></Pressable>)}</View>{errors.recurrence ? <Text style={styles.error}>{errors.recurrence}</Text> : null}</View>

          <View style={[styles.card, styles.settingRow]}><View><Text style={styles.settingTitle}>Reminder enabled</Text><Text style={styles.helper}>You can pause it later without deleting it.</Text></View><Switch value={enabled} onValueChange={setEnabled} trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }} thumbColor="#FFFFFF" /></View>

          <Pressable disabled={saving} onPress={() => void save()} style={[styles.saveButton, saving && { opacity: 0.6 }]}>{saving ? <ActivityIndicator color="#FFFFFF" /> : <><MaterialIcons name="check" size={20} color="#FFFFFF" /><Text style={styles.saveText}>{reminderId ? 'Save changes' : 'Create reminder'}</Text></>}</Pressable>
          {reminderId ? <Pressable onPress={remove} style={styles.deleteButton}><MaterialIcons name="delete-outline" size={20} color={authColors.error} /><Text style={styles.deleteText}>Delete reminder</Text></Pressable> : null}
        </ScrollView>
      )}
    </View>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <View style={{ gap: 6 }}><Text style={styles.label}>{label}</Text>{children}{error ? <Text style={styles.error}>{error}</Text> : null}</View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  center: { margin: 20, padding: 28, borderRadius: 22, alignItems: 'center', gap: 10, backgroundColor: authColors.surfaceContainerLowest },
  tip: { padding: 16, borderRadius: 22, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.primaryFixed },
  tipIcon: { width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest },
  tipTitle: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  tipBody: { marginTop: 2, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, color: authColors.onSurfaceVariant },
  label: { marginLeft: 2, fontFamily: authFont.semibold, fontSize: 13, color: authColors.onSurfaceVariant },
  input: { minHeight: 52, paddingHorizontal: 15, borderRadius: 14, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest, fontFamily: authFont.regular, fontSize: 15, color: authColors.onSurface },
  inputError: { borderColor: authColors.error },
  amountField: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  prefix: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  amountInput: { flex: 1, padding: 0, fontFamily: authFont.regular, fontSize: 15, color: authColors.onSurface },
  card: { padding: 16, borderRadius: 22, gap: 10, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  settingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  settingTitle: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface },
  helper: { marginTop: 2, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, color: authColors.onSurfaceVariant },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  stepButton: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  stepValue: { minWidth: 52, fontFamily: authFont.semibold, fontSize: 12, textAlign: 'center', color: authColors.onSurface },
  recurrenceRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: { minHeight: 36, paddingHorizontal: 14, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  choiceActive: { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed },
  choiceText: { fontFamily: authFont.semibold, fontSize: 12, color: authColors.onSurfaceVariant },
  choiceTextActive: { color: authColors.primary },
  error: { marginLeft: 2, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, color: authColors.error },
  saveButton: { height: 54, borderRadius: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: authColors.primary },
  saveText: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onPrimary },
  deleteButton: { height: 48, borderRadius: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, borderWidth: 1, borderColor: '#F2B8B5', backgroundColor: '#FFF1F0' },
  deleteText: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.error },
});
