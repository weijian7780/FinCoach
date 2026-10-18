import { MaterialIcons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { useState } from 'react';
import { Modal, Platform, Pressable, View } from 'react-native';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { formatGoalDate, isoDateToLocalDate, todayIsoDate } from '@/lib/savings-domain';

type DateFieldProps = {
  error?: string;
  helperText?: string;
  label: string;
  leadingIcon?: ComponentProps<typeof MaterialIcons>['name'];
  maximumDate?: string;
  minimumDate?: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
  variant?: 'outlined' | 'tonal';
};

export function DateField({ error, helperText, label, leadingIcon, maximumDate, minimumDate, onChange, placeholder = 'Select date', value, variant = 'outlined' }: DateFieldProps) {
  const [showPicker, setShowPicker] = useState(false);
  const selectedDate = isoDateToLocalDate(value) ?? isoDateToLocalDate(minimumDate ?? '') ?? new Date();
  const minDate = minimumDate ? isoDateToLocalDate(minimumDate) ?? undefined : undefined;
  const maxDate = maximumDate ? isoDateToLocalDate(maximumDate) ?? undefined : undefined;
  const [visibleMonth, setVisibleMonth] = useState(
    () => new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1),
  );

  const year = visibleMonth.getFullYear();
  const month = visibleMonth.getMonth();
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const days = Array.from({ length: 42 }, (_, index) => {
    const day = index - firstWeekday + 1;
    return day >= 1 && day <= daysInMonth ? day : null;
  });

  function monthCanBeShown(candidate: Date) {
    const start = new Date(candidate.getFullYear(), candidate.getMonth(), 1);
    const end = new Date(candidate.getFullYear(), candidate.getMonth() + 1, 0);
    return (!minDate || end >= minDate) && (!maxDate || start <= maxDate);
  }

  function moveMonth(offset: number) {
    const candidate = new Date(year, month + offset, 1);
    if (monthCanBeShown(candidate)) setVisibleMonth(candidate);
  }

  function openPicker() {
    setVisibleMonth(new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1));
    setShowPicker(true);
  }

  function selectDay(day: number) {
    const date = new Date(year, month, day);
    if ((minDate && date < minDate) || (maxDate && date > maxDate)) return;
    onChange(todayIsoDate(date));
    setShowPicker(false);
  }

  return (
    <View style={{ gap: 6 }}>
      <Text style={variant === 'tonal' ? tonalLabelStyle : labelStyle}>{label}</Text>
      {Platform.OS === 'web' ? (
        <TextInput
          accessibilityLabel={label}
          onChangeText={onChange}
          placeholder={placeholder}
          placeholderTextColor={authColors.outline}
          style={[variant === 'tonal' ? tonalFieldStyle : fieldStyle, error && errorFieldStyle]}
          value={value}
        />
      ) : (
        <Pressable
          accessibilityLabel={label}
          accessibilityRole="button"
          onPress={openPicker}
          style={[variant === 'tonal' ? tonalFieldStyle : fieldStyle, dateButtonStyle, error && errorFieldStyle]}>
          <View style={dateValueStyle}>
            {leadingIcon ? <MaterialIcons name={leadingIcon} size={24} color={authColors.primary} /> : null}
            <Text style={{ flex: 1, fontSize: variant === 'tonal' ? 16 : 15, fontFamily: authFont.regular, color: value ? authColors.onSurface : authColors.outline }}>
              {value ? formatGoalDate(value) : placeholder}
            </Text>
          </View>
          {!leadingIcon ? <MaterialIcons name="calendar-today" size={19} color={authColors.primary} /> : null}
        </Pressable>
      )}
      <Modal
        animationType="fade"
        onRequestClose={() => setShowPicker(false)}
        statusBarTranslucent
        transparent
        visible={Platform.OS !== 'web' && showPicker}>
        <View style={modalBackdropStyle}>
          <Pressable
            accessibilityLabel="Close date picker"
            accessibilityRole="button"
            onPress={() => setShowPicker(false)}
            style={modalDismissStyle}
          />
          <View accessibilityViewIsModal style={calendarCardStyle}>
            <View style={calendarHeaderStyle}>
              <Pressable
                accessibilityLabel="Previous month"
                accessibilityRole="button"
                disabled={!monthCanBeShown(new Date(year, month - 1, 1))}
                hitSlop={8}
                onPress={() => moveMonth(-1)}>
                <MaterialIcons name="chevron-left" size={28} color={authColors.primary} />
              </Pressable>
              <Text style={calendarTitleStyle}>
                {visibleMonth.toLocaleDateString('en-MY', { month: 'long', year: 'numeric' })}
              </Text>
              <Pressable
                accessibilityLabel="Next month"
                accessibilityRole="button"
                disabled={!monthCanBeShown(new Date(year, month + 1, 1))}
                hitSlop={8}
                onPress={() => moveMonth(1)}>
                <MaterialIcons name="chevron-right" size={28} color={authColors.primary} />
              </Pressable>
            </View>

            <View style={weekRowStyle}>
              {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((weekday, index) => (
                <Text key={`${weekday}-${index}`} style={weekdayStyle}>{weekday}</Text>
              ))}
            </View>

            <View style={daysGridStyle}>
              {days.map((day, index) => {
                if (day == null) return <View key={`empty-${index}`} style={dayCellStyle} />;
                const date = new Date(year, month, day);
                const isoDate = todayIsoDate(date);
                const disabled = Boolean((minDate && date < minDate) || (maxDate && date > maxDate));
                const selected = isoDate === value;
                return (
                  <View key={isoDate} style={dayCellStyle}>
                    <Pressable
                      accessibilityLabel={formatGoalDate(isoDate)}
                      accessibilityRole="button"
                      accessibilityState={{ disabled, selected }}
                      disabled={disabled}
                      onPress={() => selectDay(day)}
                      style={({ pressed }) => [
                        dayButtonStyle,
                        selected && selectedDayStyle,
                        disabled && { opacity: 0.28 },
                        pressed && !disabled && { opacity: 0.72 },
                      ]}>
                      <Text style={[dayTextStyle, selected && { color: authColors.onPrimary }]}>{day}</Text>
                    </Pressable>
                  </View>
                );
              })}
            </View>

            <View style={calendarActionsStyle}>
              {value ? <Pressable accessibilityRole="button" onPress={() => { onChange(''); setShowPicker(false); }} style={cancelButtonStyle}><Text style={removeTextStyle}>Remove deadline</Text></Pressable> : <View />}
              <Pressable accessibilityRole="button" onPress={() => setShowPicker(false)} style={cancelButtonStyle}><Text style={cancelTextStyle}>Cancel</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
      {error ? <Text style={errorTextStyle}>{error}</Text> : null}
      {!error && helperText ? <Text style={helperTextStyle}>{helperText}</Text> : null}
    </View>
  );
}

const labelStyle = { marginLeft: 2, fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const tonalLabelStyle = { marginLeft: 3, fontSize: 16, lineHeight: 22, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const fieldStyle = {
  minHeight: 50,
  justifyContent: 'center',
  paddingHorizontal: 15,
  paddingVertical: 12,
  borderRadius: 12,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  backgroundColor: authColors.surfaceContainerLowest,
  fontSize: 15,
  fontFamily: authFont.regular,
  color: authColors.onSurface,
} as const;
const tonalFieldStyle = {
  minHeight: 64,
  justifyContent: 'center',
  paddingHorizontal: 17,
  paddingVertical: 12,
  borderRadius: 16,
  borderWidth: 1,
  borderColor: 'transparent',
  backgroundColor: authColors.surfaceContainer,
  fontSize: 16,
  fontFamily: authFont.regular,
  color: authColors.onSurface,
} as const;
const dateButtonStyle = { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const;
const dateValueStyle = { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 13 } as const;
const errorFieldStyle = { borderColor: authColors.error } as const;
const errorTextStyle = { marginLeft: 2, fontSize: 12, fontFamily: authFont.regular, color: authColors.error } as const;
const helperTextStyle = { marginLeft: 3, fontSize: 13, lineHeight: 18, fontFamily: authFont.regular, color: authColors.outline } as const;
const modalBackdropStyle = { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 20, backgroundColor: 'rgba(22, 20, 31, 0.42)' } as const;
const modalDismissStyle = { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 } as const;
const calendarCardStyle = { width: '100%', maxWidth: 380, padding: 18, borderRadius: 20, backgroundColor: authColors.surfaceContainerLowest, shadowColor: '#000000', shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.2, shadowRadius: 24, elevation: 12 } as const;
const calendarHeaderStyle = { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 } as const;
const calendarTitleStyle = { fontSize: 18, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const weekRowStyle = { flexDirection: 'row', marginBottom: 6 } as const;
const weekdayStyle = { width: '14.2857%', textAlign: 'center', fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const daysGridStyle = { flexDirection: 'row', flexWrap: 'wrap' } as const;
const dayCellStyle = { width: '14.2857%', height: 44, alignItems: 'center', justifyContent: 'center' } as const;
const dayButtonStyle = { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' } as const;
const selectedDayStyle = { backgroundColor: authColors.primary } as const;
const dayTextStyle = { fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const cancelButtonStyle = { alignSelf: 'flex-end', marginTop: 10, paddingHorizontal: 14, paddingVertical: 9 } as const;
const cancelTextStyle = { fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary } as const;
const calendarActionsStyle = { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const;
const removeTextStyle = { fontSize: 14, fontFamily: authFont.semibold, color: authColors.error } as const;
