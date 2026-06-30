import { Text, View } from 'react-native';

import { colors, radius, spacing, typography } from '@/constants/design';

export function BrandMark() {
  return (
    <View style={{ alignItems: 'center', gap: spacing.sm }}>
      <View
        style={{
          width: 58,
          height: 58,
          borderRadius: radius.lg,
          backgroundColor: colors.primary,
          alignItems: 'center',
          justifyContent: 'center',
        }}>
        <Text style={[typography.title, { color: colors.onPrimary }]}>FC</Text>
      </View>
      <Text style={[typography.bodyStrong, { color: colors.text }]} selectable>
        FinCoach
      </Text>
    </View>
  );
}
