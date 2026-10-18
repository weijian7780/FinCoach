import { DateTimePicker as ExpoDateTimePicker } from '@expo/ui/community/datetime-picker';
import { MaterialIcons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import { Pressable, StyleSheet } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { normalizeReminderTime } from '@/lib/alerts-domain';

type TimePickerFieldProps = {
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
  hasError?: boolean;
  accessibilityLabel?: string;
};

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

export function TimePickerField({
  value,
  onChange,
  compact = false,
  hasError = false,
  accessibilityLabel = 'Choose reminder time',
}: TimePickerFieldProps) {
  const [showPicker, setShowPicker] = useState(false);
  const selectedDate = useMemo(() => dateForTime(value), [value]);
  const displayValue = normalizeReminderTime(value) ?? '09:00';

  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      accessibilityValue={{ text: displayValue }}
      onPress={() => setShowPicker(true)}
      style={({ pressed }) => [
        styles.field,
        compact ? styles.compactField : styles.fullField,
        hasError && styles.errorField,
        pressed && styles.pressed,
      ]}>
      <MaterialIcons name="schedule" size={compact ? 17 : 20} color={authColors.primary} />
      <Text style={[styles.value, compact ? styles.compactValue : styles.fullValue]}>{displayValue}</Text>
      <MaterialIcons name="arrow-drop-down" size={compact ? 18 : 22} color={authColors.onSurfaceVariant} />

      {showPicker ? (
        <ExpoDateTimePicker
          value={selectedDate}
          mode="time"
          presentation="dialog"
          is24Hour
          accentColor={authColors.primary}
          positiveButton={{ label: 'OK' }}
          negativeButton={{ label: 'Cancel' }}
          onValueChange={(_, selectedTime) => {
            setShowPicker(false);
            onChange(timeForDate(selectedTime));
          }}
          onDismiss={() => setShowPicker(false)}
        />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: authColors.outlineVariant,
    backgroundColor: authColors.surfaceContainerLow,
  },
  compactField: {
    width: 108,
    height: 38,
    paddingHorizontal: 9,
    borderRadius: 12,
    gap: 5,
  },
  fullField: {
    minHeight: 52,
    paddingHorizontal: 15,
    borderRadius: 14,
    gap: 10,
    backgroundColor: authColors.surfaceContainerLowest,
  },
  value: {
    flex: 1,
    color: authColors.onSurface,
  },
  compactValue: {
    fontFamily: authFont.semibold,
    fontSize: 13,
  },
  fullValue: {
    fontFamily: authFont.regular,
    fontSize: 15,
  },
  errorField: {
    borderWidth: 1,
    borderColor: authColors.error,
  },
  pressed: {
    opacity: 0.72,
  },
});
