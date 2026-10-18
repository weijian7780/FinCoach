import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState, type ReactNode } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TimePickerField } from '@/components/notifications/time-picker-field';
import { DateField } from '@/components/savings/date-field';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { createReminder, deleteReminder, ensureNotificationPreferences, fetchReminder, updateReminder } from '@/lib/alerts';
import { validateBillReminderInput } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import { todayIsoDate } from '@/lib/savings-domain';
import type { ReminderRecurrence } from '@/lib/types';

const recurrenceOptions: { value: ReminderRecurrence; label: string }[] = [
  { value: 'none', label: 'Once' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
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
  const date = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue);
  const time = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(timeValue);
  if (!date || !time) return '';
  return new Date(Number(date[1]), Number(date[2]) - 1, Number(date[3]), Number(time[1]), Number(time[2]), 0, 0).toISOString();
}

export function ReminderFormScreen() {
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
  const [showMore, setShowMore] = useState(false);
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
        setShowMore(existing.amount != null || existing.lead_days !== preferences.default_bill_lead_days || existing.recurrence !== 'none' || !existing.enabled);
      } else {
        setLeadDays(preferences.default_bill_lead_days);
        setDueTime(preferences.default_bill_reminder_time.slice(0, 5));
      }
    } catch {
      appDialog.open('Could not load reminder', 'Check your connection and try again.');
    } finally {
      setLoading(false);
    }
  }, [reminderId, userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  async function save() {
    if (!userId) return;
    const dueAt = toIso(dueDate, dueTime);
    const validation = validateBillReminderInput({ title, amount, dueAt, leadDays, recurrence });
    setErrors(validation);
    if (Object.keys(validation).length > 0) return;

    const input = {
      title,
      amount: amount.trim() ? Number(amount) : null,
      due_at: dueAt,
      lead_days: leadDays,
      recurrence,
      recurrence_anchor_day: Number(dueDate.slice(8, 10)),
      enabled,
    };
    setSaving(true);
    try {
      if (reminderId) await updateReminder(reminderId, userId, input);
      else await createReminder(userId, input);
      router.back();
    } catch {
      appDialog.open('Could not save reminder', 'Check the fields and your connection, then try again.');
    } finally {
      setSaving(false);
    }
  }

  function remove() {
    if (!reminderId || !userId) return;
    appDialog.open('Delete reminder?', 'This permanently removes the reminder.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => void (async () => {
          try {
            await deleteReminder(reminderId, userId);
            router.back();
          } catch {
            appDialog.open('Could not delete', 'Check your connection and try again.');
          }
        })(),
      },
    ]);
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => router.back()} style={styles.roundButton}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={styles.heading}>{reminderId ? 'Edit reminder' : 'New reminder'}</Text>
        <View style={styles.roundButton} />
      </View>

      {loading ? <View style={styles.center}><ActivityIndicator color={authColors.primary} /><Text style={styles.helper}>Loading reminder…</Text></View> : (
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 16, paddingBottom: insets.bottom + 32, gap: 16 }}>
          <View style={styles.intro}>
            <View style={styles.introIcon}><MaterialIcons name="notifications-active" size={21} color={authColors.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.introTitle}>Set the essentials</Text>
              <Text style={styles.introBody}>Name it, then choose when FinCoach should remind you.</Text>
            </View>
          </View>

          <Field label="Reminder name" error={errors.title}>
            <TextInput value={title} onChangeText={setTitle} placeholder="e.g. Wi-Fi bill" placeholderTextColor={authColors.outline} maxLength={100} style={[styles.input, errors.title && styles.inputError]} />
          </Field>
          <DateField label="Date" value={dueDate} onChange={setDueDate} minimumDate={todayIsoDate()} placeholder="Choose a date" error={errors.dueAt} />
          <Field label="Time" error={!dueDate && errors.dueAt ? undefined : errors.dueAt}>
            <TimePickerField value={dueTime} onChange={setDueTime} hasError={Boolean(errors.dueAt)} />
          </Field>

          <Pressable accessibilityRole="button" accessibilityState={{ expanded: showMore }} onPress={() => setShowMore((value) => !value)} style={styles.moreButton}>
            <View style={styles.moreLeading}><MaterialIcons name="tune" size={20} color={authColors.primary} /><Text style={styles.moreText}>More options</Text></View>
            <MaterialIcons name={showMore ? 'expand-less' : 'expand-more'} size={23} color={authColors.primary} />
          </Pressable>

          {showMore ? <View style={styles.advancedGroup}>
            <Field label="Amount (optional)" error={errors.amount}>
              <View style={[styles.input, styles.amountField, errors.amount && styles.inputError]}>
                <Text style={styles.prefix}>RM</Text>
                <TextInput value={amount} onChangeText={(value) => setAmount(value.replace(/[^0-9.]/g, ''))} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={authColors.outline} style={styles.amountInput} />
              </View>
            </Field>

            <View style={[styles.card, styles.settingRow]}>
              <View style={{ flex: 1 }}><Text style={styles.settingTitle}>Notify me early</Text><Text style={styles.helper}>0 days means on the due date.</Text></View>
              <DayStepper value={leadDays} onChange={setLeadDays} />
            </View>
            {errors.leadDays ? <Text style={styles.error}>{errors.leadDays}</Text> : null}

            <View style={styles.card}>
              <Text style={styles.settingTitle}>Repeat</Text>
              <View style={styles.recurrenceRow}>{recurrenceOptions.map((option) => <Pressable key={option.value} onPress={() => setRecurrence(option.value)} style={[styles.choice, recurrence === option.value && styles.choiceActive]}><Text style={[styles.choiceText, recurrence === option.value && styles.choiceTextActive]}>{option.label}</Text></Pressable>)}</View>
              {errors.recurrence ? <Text style={styles.error}>{errors.recurrence}</Text> : null}
            </View>

            {reminderId ? <View style={[styles.card, styles.settingRow]}>
              <View style={{ flex: 1 }}><Text style={styles.settingTitle}>Reminder enabled</Text><Text style={styles.helper}>Pause it without deleting it.</Text></View>
              <Switch value={enabled} onValueChange={setEnabled} trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }} thumbColor="#FFFFFF" />
            </View> : null}
          </View> : null}

          <Pressable disabled={saving} onPress={() => void save()} style={[styles.saveButton, saving && { opacity: 0.6 }]}>
            {saving ? <ActivityIndicator color={authColors.onPrimary} /> : <><MaterialIcons name="check" size={20} color={authColors.onPrimary} /><Text style={styles.saveText}>{reminderId ? 'Save changes' : 'Create reminder'}</Text></>}
          </Pressable>
          {reminderId ? <Pressable onPress={remove} style={styles.deleteButton}><MaterialIcons name="delete-outline" size={20} color={authColors.error} /><Text style={styles.deleteText}>Delete reminder</Text></Pressable> : null}
        </ScrollView>
      )}
    </View>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return <View style={{ gap: 6 }}><Text style={styles.label}>{label}</Text>{children}{error ? <Text style={styles.error}>{error}</Text> : null}</View>;
}

function DayStepper({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <View style={styles.stepper}>
    <Pressable accessibilityRole="button" accessibilityLabel="Reduce early reminder days" onPress={() => onChange(Math.max(0, value - 1))} style={styles.stepButton}><MaterialIcons name="remove" size={18} color={authColors.primary} /></Pressable>
    <Text style={styles.stepValue}>{value} day{value === 1 ? '' : 's'}</Text>
    <Pressable accessibilityRole="button" accessibilityLabel="Increase early reminder days" onPress={() => onChange(Math.min(365, value + 1))} style={styles.stepButton}><MaterialIcons name="add" size={18} color={authColors.primary} /></Pressable>
  </View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  center: { margin: 20, padding: 28, borderRadius: 22, alignItems: 'center', gap: 10, backgroundColor: authColors.surfaceContainerLowest },
  intro: { padding: 14, borderRadius: 18, flexDirection: 'row', alignItems: 'center', gap: 11, backgroundColor: authColors.primaryFixed },
  introIcon: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest },
  introTitle: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface },
  introBody: { marginTop: 2, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, color: authColors.onSurfaceVariant },
  label: { marginLeft: 2, fontFamily: authFont.semibold, fontSize: 13, color: authColors.onSurfaceVariant },
  input: { minHeight: 52, paddingHorizontal: 15, borderRadius: 14, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest, fontFamily: authFont.regular, fontSize: 15, color: authColors.onSurface },
  inputError: { borderColor: authColors.error },
  amountField: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  prefix: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  amountInput: { flex: 1, padding: 0, fontFamily: authFont.regular, fontSize: 15, color: authColors.onSurface },
  moreButton: { minHeight: 54, paddingHorizontal: 15, borderRadius: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest },
  moreLeading: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  moreText: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary },
  advancedGroup: { gap: 12 },
  card: { padding: 16, borderRadius: 18, gap: 10, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
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
