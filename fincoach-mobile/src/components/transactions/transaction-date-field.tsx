import { DateTimePicker } from '@expo/ui/community/datetime-picker';
import { MaterialIcons } from '@expo/vector-icons';
import { useState } from 'react';
import { Keyboard, Platform, Pressable, StyleSheet, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { isTransactionDate, malaysiaToday, transactionDateForPicker, transactionDateFromPicker } from '@/lib/transaction-date';

type Props = { value: string; onChange: (value: string) => void; error?: string };

export function TransactionDateField({ value, onChange, error }: Props) {
  const [showPicker, setShowPicker] = useState(false);
  const today = malaysiaToday();
  const android = Platform.OS === 'android';

  return (
    <View style={styles.container}>
      <Text style={styles.label}>Date</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Choose transaction date"
        accessibilityValue={{ text: value || 'No date selected' }}
        onPress={() => {
          // Blur the active text field before presenting the native calendar.
          Keyboard.dismiss();
          setShowPicker(true);
        }}
        style={[styles.field, error ? styles.invalid : undefined]}>
        <Text style={[styles.value, !isTransactionDate(value) && styles.placeholder]}>
          {isTransactionDate(value) ? value : 'Choose date'}
        </Text>
        <MaterialIcons name="calendar-today" size={22} color={authColors.primary} />
      </Pressable>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {showPicker ? (
        <DateTimePicker
          value={transactionDateForPicker(value, today, android)}
          maximumDate={transactionDateForPicker(today, today, android)}
          mode="date"
          display={android ? 'default' : 'inline'}
          presentation="dialog"
          accentColor={authColors.primary}
          positiveButton={{ label: 'OK' }}
          negativeButton={{ label: 'Cancel' }}
          onValueChange={(_, selectedDate) => {
            setShowPicker(false);
            const selected = transactionDateFromPicker(selectedDate, android);
            if (isTransactionDate(selected) && selected <= malaysiaToday()) onChange(selected);
          }}
          onDismiss={() => setShowPicker(false)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 7 },
  label: { marginLeft: 2, fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface },
  field: { minHeight: 56, paddingHorizontal: 16, borderRadius: 15, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest, flexDirection: 'row', alignItems: 'center', gap: 12 },
  value: { flex: 1, fontSize: 15, fontFamily: authFont.regular, color: authColors.onSurface },
  placeholder: { color: authColors.outline },
  invalid: { borderColor: authColors.error },
  error: { fontSize: 12, fontFamily: authFont.regular, color: authColors.error },
});
