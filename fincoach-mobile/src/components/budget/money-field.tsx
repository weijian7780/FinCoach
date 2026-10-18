import { View } from 'react-native';

import { AppText as Text, AppTextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

export function MoneyField({
  error,
  label,
  onChangeText,
  placeholder = '0.00',
  value,
}: {
  error?: string | null;
  label: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>{label}</Text>
      <View style={{ minHeight: 50, flexDirection: 'row', alignItems: 'center', borderWidth: error ? 1 : 0, borderColor: error ? authColors.error : 'transparent', borderRadius: 12, backgroundColor: authColors.surfaceContainerLow, paddingHorizontal: 14 }}>
        <Text style={{ fontFamily: authFont.semibold, fontSize: 16, color: authColors.onSurfaceVariant }}>RM</Text>
        <AppTextInput accessibilityLabel={label} keyboardType="decimal-pad" onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={authColors.outline} value={value} style={{ flex: 1, paddingVertical: 13, paddingHorizontal: 10, fontFamily: authFont.regular, fontSize: 16, color: authColors.onSurface }} />
      </View>
      {error ? <Text selectable accessibilityRole="alert" style={{ fontFamily: authFont.regular, fontSize: 12, color: authColors.error }}>{error}</Text> : null}
    </View>
  );
}
