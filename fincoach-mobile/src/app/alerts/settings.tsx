import { DateTimePicker as ExpoDateTimePicker } from '@expo/ui/community/datetime-picker';
import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { ensureNotificationPreferences, saveNotificationPreferences } from '@/lib/alerts';
import {
  formatLeadDays,
  formatNotificationTime,
  formatSpendingSchedule,
  normalizeReminderTime,
} from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import { loadNotificationSdk, openNotificationSettings } from '@/lib/notification-platform';
import type {
  NotificationPreferences,
  NotificationPreferencesUpdate,
  SpendingFrequency,
} from '@/lib/types';

const weekdayOptions = [
  { value: 1, label: 'Monday' }, { value: 2, label: 'Tuesday' },
  { value: 3, label: 'Wednesday' }, { value: 4, label: 'Thursday' },
  { value: 5, label: 'Friday' }, { value: 6, label: 'Saturday' },
  { value: 0, label: 'Sunday' },
];

const leadDayOptions = [0, 1, 3, 7, 14, 30];

type SheetKind = 'savings' | 'spending';
type SheetPage = 'main' | 'repeat' | 'weekday' | 'leadDays';

function normalizePreferenceTimes(preferences: NotificationPreferences): NotificationPreferences {
  return {
    ...preferences,
    savings_reminder_time: normalizeReminderTime(preferences.savings_reminder_time) ?? preferences.savings_reminder_time,
    spending_reminder_time: normalizeReminderTime(preferences.spending_reminder_time) ?? preferences.spending_reminder_time,
    default_bill_reminder_time: normalizeReminderTime(preferences.default_bill_reminder_time) ?? preferences.default_bill_reminder_time,
  };
}

function dateForTime(value: string) {
  const normalized = normalizeReminderTime(value) ?? '09:00';
  const [hour, minute] = normalized.split(':').map(Number);
  const date = new Date();
  date.setHours(hour, minute, 0, 0);
  return date;
}

function timeForDate(value: Date) {
  return `${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`;
}

export default function NotificationSettingsScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneEnabled, setPhoneEnabled] = useState<boolean | null>(null);
  const [sheetKind, setSheetKind] = useState<SheetKind | null>(null);
  const [sheetPage, setSheetPage] = useState<SheetPage>('main');
  const [draft, setDraft] = useState<NotificationPreferences | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const [savedPreferences, permission] = await Promise.all([
        ensureNotificationPreferences(userId),
        loadNotificationSdk()
          .then(async (sdk) => {
            const status = await sdk.getPermissionsAsync();
            return status.status === 'granted';
          })
          .catch(() => null),
      ]);
      setPreferences(normalizePreferenceTimes(savedPreferences));
      setPhoneEnabled(permission);
    }
    catch { setError('Could not load notification settings. Check your connection and try again.'); }
    finally { setLoading(false); }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  function updateDraft<K extends keyof NotificationPreferences>(
    key: K,
    value: NotificationPreferences[K],
  ) {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  }

  async function persistPatch(patch: NotificationPreferencesUpdate) {
    if (!userId || !preferences || saving) return false;
    const previous = preferences;
    setPreferences(normalizePreferenceTimes({ ...preferences, ...patch }));
    setSaving(true);
    try {
      const saved = await saveNotificationPreferences(userId, patch);
      setPreferences(normalizePreferenceTimes(saved));
      return true;
    } catch {
      setPreferences(previous);
      appDialog.open('Could not save', 'Check your connection and try again.');
      return false;
    } finally {
      setSaving(false);
    }
  }

  function openSheet(kind: SheetKind) {
    if (!preferences) return;
    setDraft({ ...preferences });
    setSheetPage('main');
    setSheetKind(kind);
  }

  function closeSheet() {
    if (saving) return;
    setSheetKind(null);
    setSheetPage('main');
    setDraft(null);
  }

  async function saveSheet() {
    if (!draft || !sheetKind) return;
    const reminderTime = normalizeReminderTime(
      sheetKind === 'savings'
        ? draft.savings_reminder_time
        : draft.spending_reminder_time,
    );
    if (!reminderTime) {
      appDialog.open('Check reminder time', 'Choose a valid reminder time.');
      return;
    }

    const patch: NotificationPreferencesUpdate = sheetKind === 'savings'
      ? {
        savings_enabled: draft.savings_enabled,
        savings_lead_days: draft.savings_lead_days,
        savings_reminder_time: reminderTime,
      }
      : {
        spending_enabled: draft.spending_enabled,
        spending_frequency: draft.spending_frequency,
        spending_weekday: draft.spending_frequency === 'weekly'
          ? (draft.spending_weekday ?? 1)
          : null,
        spending_reminder_time: reminderTime,
      };

    if (await persistPatch(patch)) closeSheet();
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
        <ScrollView
          contentInsetAdjustmentBehavior="automatic"
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{
            paddingHorizontal: 20,
            paddingTop: 8,
            paddingBottom: insets.bottom + 32,
            gap: 14,
          }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Manage phone notification permission"
            onPress={() => void openNotificationSettings()}
            style={({ pressed }) => [styles.phoneCard, pressed && styles.pressed]}>
            <View style={[styles.iconCircle, { backgroundColor: '#E7F7EE' }]}>
              <MaterialIcons name="notifications-none" size={23} color="#2EAD6B" />
            </View>
            <View style={styles.rowText}>
              <Text style={styles.rowTitle}>Phone notifications</Text>
              <Text style={styles.rowDescription}>
                {phoneEnabled === null ? 'Check device settings' : phoneEnabled ? 'Enabled' : 'Off'}
              </Text>
            </View>
            <Text style={styles.manageLink}>Manage</Text>
          </Pressable>

          <Text style={styles.sectionTitle}>Alerts</Text>
          <View style={styles.groupCard}>
            <PreferenceRow
              icon="account-balance-wallet"
              iconColor="#BA1A1A"
              iconBackground="#FCE8E8"
              title="Budget alerts"
              description="80% warning and limit exceeded"
              enabled={preferences.budget_enabled}
              disabled={saving}
              onToggle={(value) => void persistPatch({ budget_enabled: value })}
            />
            <View style={styles.divider} />
            <PreferenceRow
              icon="savings"
              iconColor="#06A96B"
              iconBackground="#E5F8EF"
              title="Savings reminders"
              description={`${preferences.savings_lead_days === 0 ? 'On deadline day' : `${formatLeadDays(preferences.savings_lead_days)} before`} · ${formatNotificationTime(preferences.savings_reminder_time)}`}
              enabled={preferences.savings_enabled}
              disabled={saving}
              onToggle={(value) => void persistPatch({ savings_enabled: value })}
              onOpen={() => openSheet('savings')}
            />
          </View>

          <Text style={styles.sectionTitle}>Reminders</Text>
          <View style={styles.groupCard}>
            <PreferenceRow
              icon="insights"
              iconColor="#7C4DFF"
              iconBackground="#EEE9FF"
              title="Spending check-in"
              description={formatSpendingSchedule(
                preferences.spending_frequency,
                preferences.spending_weekday,
                preferences.spending_reminder_time,
              )}
              enabled={preferences.spending_enabled}
              disabled={saving}
              onToggle={(value) => void persistPatch({ spending_enabled: value })}
              onOpen={() => openSheet('spending')}
            />
            <View style={styles.divider} />
            <PreferenceRow
              icon="format-list-bulleted"
              iconColor={authColors.primary}
              iconBackground={authColors.primaryFixed}
              title="Manage reminders"
              description="Bills, payments and other due dates"
              onOpen={() => router.push('/alerts/reminders' as never)}
            />
          </View>

          <View style={styles.autoSave}>
            {saving
              ? <ActivityIndicator size="small" color={authColors.primary} />
              : <View style={styles.savedIcon}><MaterialIcons name="check" size={15} color={authColors.primary} /></View>}
            <Text style={styles.autoSaveText}>{saving ? 'Saving changes…' : 'Changes save automatically'}</Text>
          </View>
        </ScrollView>
      )}

      <PreferenceSheet
        visible={sheetKind !== null}
        kind={sheetKind}
        page={sheetPage}
        draft={draft}
        saving={saving}
        bottomInset={insets.bottom}
        onClose={closeSheet}
        onPageChange={setSheetPage}
        onUpdate={updateDraft}
        onDone={() => void saveSheet()}
      />
    </View>
  );
}

type PreferenceRowProps = {
  icon: keyof typeof MaterialIcons.glyphMap;
  iconColor: string;
  iconBackground: string;
  title: string;
  description: string;
  enabled?: boolean;
  disabled?: boolean;
  onToggle?: (value: boolean) => void;
  onOpen?: () => void;
};

function PreferenceRow({
  icon,
  iconColor,
  iconBackground,
  title,
  description,
  enabled,
  disabled = false,
  onToggle,
  onOpen,
}: PreferenceRowProps) {
  const identity = (
    <>
      <View style={[styles.iconCircle, { backgroundColor: iconBackground }]}>
        <MaterialIcons name={icon} size={22} color={iconColor} />
      </View>
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowDescription}>{description}</Text>
      </View>
    </>
  );

  return (
    <View style={styles.preferenceRow}>
      {onOpen ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open ${title} settings`}
          onPress={onOpen}
          style={({ pressed }) => [styles.preferenceMain, pressed && styles.pressed]}>
          {identity}
        </Pressable>
      ) : (
        <View style={styles.preferenceMain}>{identity}</View>
      )}
      {enabled !== undefined && onToggle ? (
        <Switch
          accessibilityLabel={`${title} ${enabled ? 'enabled' : 'disabled'}`}
          disabled={disabled}
          value={enabled}
          onValueChange={onToggle}
          trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }}
          thumbColor="#FFFFFF"
        />
      ) : null}
      {onOpen ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open ${title} settings`}
          hitSlop={8}
          onPress={onOpen}
          style={styles.chevronButton}>
          <MaterialIcons name="chevron-right" size={26} color={authColors.outline} />
        </Pressable>
      ) : null}
    </View>
  );
}

type PreferenceSheetProps = {
  visible: boolean;
  kind: SheetKind | null;
  page: SheetPage;
  draft: NotificationPreferences | null;
  saving: boolean;
  bottomInset: number;
  onClose: () => void;
  onPageChange: (page: SheetPage) => void;
  onUpdate: <K extends keyof NotificationPreferences>(
    key: K,
    value: NotificationPreferences[K],
  ) => void;
  onDone: () => void;
};

function PreferenceSheet({
  visible,
  kind,
  page,
  draft,
  saving,
  bottomInset,
  onClose,
  onPageChange,
  onUpdate,
  onDone,
}: PreferenceSheetProps) {
  const [showTimePicker, setShowTimePicker] = useState(false);
  const isSavings = kind === 'savings';
  const currentTime = isSavings
    ? draft?.savings_reminder_time ?? '09:00'
    : draft?.spending_reminder_time ?? '20:00';

  function selectAndReturn<K extends keyof NotificationPreferences>(
    key: K,
    value: NotificationPreferences[K],
  ) {
    onUpdate(key, value);
    onPageChange('main');
  }

  function renderSelectionPage() {
    if (!draft || page === 'main') return null;

    const title = page === 'repeat'
      ? 'Repeat'
      : page === 'weekday'
        ? 'Day'
        : 'Remind before deadline';

    return (
      <>
        <View style={styles.sheetSubHeader}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back to reminder settings"
            onPress={() => onPageChange('main')}
            style={styles.sheetBackButton}>
            <MaterialIcons name="arrow-back" size={22} color={authColors.onSurface} />
          </Pressable>
          <Text style={styles.sheetSubTitle}>{title}</Text>
          <View style={styles.sheetBackButton} />
        </View>
        <ScrollView
          contentInsetAdjustmentBehavior="automatic"
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.optionList}>
          {page === 'repeat'
            ? (['daily', 'weekly'] as SpendingFrequency[]).map((value) => (
              <SelectionOption
                key={value}
                label={value === 'daily' ? 'Daily' : 'Weekly'}
                selected={draft.spending_frequency === value}
                onPress={() => selectAndReturn('spending_frequency', value)}
              />
            ))
            : null}
          {page === 'weekday'
            ? weekdayOptions.map((day) => (
              <SelectionOption
                key={day.value}
                label={day.label}
                selected={draft.spending_weekday === day.value}
                onPress={() => selectAndReturn('spending_weekday', day.value)}
              />
            ))
            : null}
          {page === 'leadDays'
            ? leadDayOptions.map((days) => (
              <SelectionOption
                key={days}
                label={formatLeadDays(days)}
                selected={draft.savings_lead_days === days}
                onPress={() => selectAndReturn('savings_lead_days', days)}
              />
            ))
            : null}
        </ScrollView>
      </>
    );
  }

  return (
    <Modal
      animationType="slide"
      hardwareAccelerated
      onRequestClose={onClose}
      presentationStyle="overFullScreen"
      statusBarTranslucent
      transparent
      visible={visible && Boolean(kind && draft)}>
      <View style={styles.modalRoot}>
        <Pressable
          accessibilityLabel="Close reminder settings"
          onPress={onClose}
          style={styles.backdrop}
        />
        <View style={[styles.sheet, { paddingBottom: Math.max(bottomInset, 14) }]}>
          <View style={styles.grabber} />
          {page !== 'main' ? renderSelectionPage() : draft && kind ? (
            <>
              <ScrollView
                contentInsetAdjustmentBehavior="automatic"
                showsVerticalScrollIndicator={false}
                contentContainerStyle={styles.sheetContent}>
                <View style={styles.sheetHeader}>
                  <View style={styles.sheetTitleBlock}>
                    <Text style={styles.sheetTitle}>
                      {isSavings ? 'Savings reminders' : 'Spending check-in'}
                    </Text>
                    <Text style={styles.sheetDescription}>
                      {isSavings
                        ? 'Get notified before a savings goal is due.'
                        : 'A short reminder to review and record spending.'}
                    </Text>
                  </View>
                  <Switch
                    accessibilityLabel={`${isSavings ? 'Savings reminders' : 'Spending check-in'} enabled`}
                    value={isSavings ? draft.savings_enabled : draft.spending_enabled}
                    onValueChange={(value) => onUpdate(
                      isSavings ? 'savings_enabled' : 'spending_enabled',
                      value,
                    )}
                    trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }}
                    thumbColor="#FFFFFF"
                  />
                </View>

                <View style={styles.sheetRows}>
                  {isSavings ? (
                    <SheetRow
                      label="Remind before deadline"
                      value={formatLeadDays(draft.savings_lead_days)}
                      onPress={() => onPageChange('leadDays')}
                    />
                  ) : (
                    <>
                      <SheetRow
                        label="Repeat"
                        value={draft.spending_frequency === 'daily' ? 'Daily' : 'Weekly'}
                        onPress={() => onPageChange('repeat')}
                      />
                      {draft.spending_frequency === 'weekly' ? (
                        <SheetRow
                          label="Day"
                          value={weekdayOptions.find((day) => day.value === draft.spending_weekday)?.label ?? 'Monday'}
                          onPress={() => onPageChange('weekday')}
                        />
                      ) : null}
                    </>
                  )}
                  <SheetRow
                    label="Time"
                    value={formatNotificationTime(currentTime)}
                    onPress={() => setShowTimePicker(true)}
                  />
                </View>
              </ScrollView>

              <Pressable
                accessibilityRole="button"
                disabled={saving}
                onPress={onDone}
                style={({ pressed }) => [
                  styles.doneButton,
                  (pressed || saving) && { opacity: 0.72 },
                ]}>
                {saving
                  ? <ActivityIndicator color={authColors.onPrimary} />
                  : <Text style={styles.doneText}>Done</Text>}
              </Pressable>
            </>
          ) : null}

          {showTimePicker ? (
            <ExpoDateTimePicker
              value={dateForTime(currentTime)}
              mode="time"
              presentation="dialog"
              is24Hour={false}
              accentColor={authColors.primary}
              positiveButton={{ label: 'OK' }}
              negativeButton={{ label: 'Cancel' }}
              onValueChange={(_, selectedTime) => {
                setShowTimePicker(false);
                onUpdate(
                  isSavings ? 'savings_reminder_time' : 'spending_reminder_time',
                  timeForDate(selectedTime),
                );
              }}
              onDismiss={() => setShowTimePicker(false)}
            />
          ) : null}
        </View>
      </View>
    </Modal>
  );
}

function SheetRow({ label, value, onPress }: { label: string; value: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label}, ${value}`}
      onPress={onPress}
      style={({ pressed }) => [styles.sheetRow, pressed && styles.pressed]}>
      <Text style={styles.sheetRowLabel}>{label}</Text>
      <View style={styles.sheetRowValue}>
        <Text style={styles.sheetRowValueText}>{value}</Text>
        <MaterialIcons name="chevron-right" size={24} color={authColors.outline} />
      </View>
    </Pressable>
  );
}

function SelectionOption({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [
        styles.selectionOption,
        selected && styles.selectionOptionSelected,
        pressed && styles.pressed,
      ]}>
      <Text style={[styles.selectionLabel, selected && styles.selectionLabelSelected]}>
        {label}
      </Text>
      {selected ? <MaterialIcons name="check" size={21} color={authColors.primary} /> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  center: { margin: 20, padding: 28, borderRadius: 22, alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest },
  helper: { fontFamily: authFont.regular, color: authColors.onSurfaceVariant },
  error: { fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, color: authColors.error, textAlign: 'center' },
  primaryButton: { minHeight: 40, paddingHorizontal: 22, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary },
  primaryText: { fontFamily: authFont.semibold, color: authColors.onPrimary },
  phoneCard: {
    minHeight: 78,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 22,
    borderCurve: 'continuous',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: authColors.surfaceContainerLowest,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: authColors.outlineVariant,
    boxShadow: '0 3px 12px rgba(27, 27, 35, 0.06)',
  },
  sectionTitle: {
    paddingTop: 8,
    paddingHorizontal: 4,
    fontFamily: authFont.bold,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: authColors.onSurfaceVariant,
  },
  groupCard: {
    borderRadius: 22,
    borderCurve: 'continuous',
    overflow: 'hidden',
    backgroundColor: authColors.surfaceContainerLowest,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: authColors.outlineVariant,
    boxShadow: '0 3px 12px rgba(27, 27, 35, 0.06)',
  },
  preferenceRow: {
    minHeight: 88,
    paddingLeft: 16,
    paddingRight: 10,
    flexDirection: 'row',
    alignItems: 'center',
  },
  preferenceMain: {
    minHeight: 88,
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowText: { flex: 1, gap: 2 },
  rowTitle: {
    fontFamily: authFont.semibold,
    fontSize: 16,
    lineHeight: 21,
    color: authColors.onSurface,
  },
  rowDescription: {
    fontFamily: authFont.regular,
    fontSize: 13,
    lineHeight: 18,
    color: authColors.onSurfaceVariant,
  },
  manageLink: {
    paddingHorizontal: 4,
    fontFamily: authFont.semibold,
    fontSize: 14,
    color: authColors.primary,
  },
  chevronButton: {
    width: 32,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 72,
    marginRight: 16,
    backgroundColor: authColors.outlineVariant,
  },
  pressed: { opacity: 0.68 },
  autoSave: {
    minHeight: 42,
    paddingTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  savedIcon: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: authColors.primaryFixed,
  },
  autoSaveText: {
    fontFamily: authFont.regular,
    fontSize: 13,
    color: authColors.onSurfaceVariant,
  },
  modalRoot: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  backdrop: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(28, 29, 43, 0.48)',
  },
  sheet: {
    maxHeight: '92%',
    minHeight: 420,
    paddingTop: 10,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    borderCurve: 'continuous',
    backgroundColor: authColors.surfaceContainerLowest,
    boxShadow: '0 -8px 30px rgba(27, 27, 35, 0.16)',
  },
  grabber: {
    width: 42,
    height: 5,
    borderRadius: 3,
    alignSelf: 'center',
    backgroundColor: authColors.outlineVariant,
  },
  sheetContent: {
    paddingHorizontal: 20,
    paddingTop: 24,
    paddingBottom: 8,
    gap: 22,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  sheetTitleBlock: { flex: 1, gap: 4 },
  sheetTitle: {
    fontFamily: authFont.semibold,
    fontSize: 22,
    lineHeight: 28,
    color: authColors.onSurface,
  },
  sheetDescription: {
    fontFamily: authFont.regular,
    fontSize: 14,
    lineHeight: 20,
    color: authColors.onSurfaceVariant,
  },
  sheetRows: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: authColors.outlineVariant,
  },
  sheetRow: {
    minHeight: 66,
    paddingHorizontal: 4,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: authColors.outlineVariant,
  },
  sheetRowLabel: {
    flex: 1,
    fontFamily: authFont.regular,
    fontSize: 16,
    color: authColors.onSurface,
  },
  sheetRowValue: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  sheetRowValueText: {
    fontFamily: authFont.semibold,
    fontSize: 15,
    color: authColors.onSurfaceVariant,
  },
  doneButton: {
    height: 54,
    marginHorizontal: 20,
    marginTop: 16,
    borderRadius: 18,
    borderCurve: 'continuous',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: authColors.primary,
  },
  doneText: {
    fontFamily: authFont.semibold,
    fontSize: 16,
    color: authColors.onPrimary,
  },
  sheetSubHeader: {
    minHeight: 60,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sheetBackButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sheetSubTitle: {
    fontFamily: authFont.semibold,
    fontSize: 18,
    color: authColors.onSurface,
  },
  optionList: {
    paddingHorizontal: 20,
    paddingBottom: 18,
    gap: 8,
  },
  selectionOption: {
    minHeight: 52,
    paddingHorizontal: 16,
    borderRadius: 16,
    borderCurve: 'continuous',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: authColors.outlineVariant,
    backgroundColor: authColors.surfaceContainerLowest,
  },
  selectionOptionSelected: {
    borderColor: authColors.primary,
    backgroundColor: authColors.primaryFixed,
  },
  selectionLabel: {
    fontFamily: authFont.regular,
    fontSize: 15,
    color: authColors.onSurface,
  },
  selectionLabelSelected: {
    fontFamily: authFont.semibold,
    color: authColors.primary,
  },
});
