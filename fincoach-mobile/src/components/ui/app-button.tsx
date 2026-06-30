import { ActivityIndicator, Pressable, Text } from 'react-native';

import { colors, radius, spacing, typography } from '@/constants/design';

type AppButtonProps = {
  label: string;
  loading?: boolean;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost';
};

export function AppButton({ label, loading = false, onPress, variant = 'primary' }: AppButtonProps) {
  const isPrimary = variant === 'primary';
  const isGhost = variant === 'ghost';

  return (
    <Pressable
      accessibilityRole="button"
      disabled={loading}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 52,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: radius.md,
        paddingHorizontal: spacing.lg,
        backgroundColor: isPrimary ? colors.primary : isGhost ? 'transparent' : colors.surfaceAlt,
        borderWidth: isPrimary || isGhost ? 0 : 1,
        borderColor: colors.border,
        opacity: pressed || loading ? 0.72 : 1,
      })}>
      {loading ? (
        <ActivityIndicator color={isPrimary ? colors.onPrimary : colors.primary} />
      ) : (
        <Text
          style={[
            typography.button,
            {
              color: isPrimary ? colors.onPrimary : isGhost ? colors.danger : colors.text,
            },
          ]}>
          {label}
        </Text>
      )}
    </Pressable>
  );
}
