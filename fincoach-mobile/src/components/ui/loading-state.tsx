import { ActivityIndicator, Text, View } from 'react-native';

import { colors, spacing, typography } from '@/constants/design';

export function LoadingState({ label }: { label: string }) {
  return (
    <View
      style={{
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.md,
        backgroundColor: colors.background,
        padding: spacing.lg,
      }}>
      <ActivityIndicator color={colors.primary} />
      <Text style={typography.body} selectable>
        {label}
      </Text>
    </View>
  );
}
