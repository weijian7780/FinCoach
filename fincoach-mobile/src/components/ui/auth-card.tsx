import { Text, View } from 'react-native';

import { colors, radius, spacing, typography } from '@/constants/design';

type AuthCardProps = {
  children: React.ReactNode;
  subtitle: string;
  title: string;
};

export function AuthCard({ children, subtitle, title }: AuthCardProps) {
  return (
    <View
      style={{
        width: '100%',
        maxWidth: 520,
        alignSelf: 'center',
        borderRadius: radius.xl,
        backgroundColor: colors.surface,
        padding: spacing.lg,
        gap: spacing.lg,
        borderWidth: 1,
        borderColor: colors.border,
        boxShadow: '0 10px 26px rgba(15, 23, 42, 0.10)',
      }}>
      <View style={{ gap: spacing.xs }}>
        <Text style={typography.title} selectable>
          {title}
        </Text>
        <Text style={typography.body} selectable>
          {subtitle}
        </Text>
      </View>
      <View style={{ gap: spacing.md }}>{children}</View>
    </View>
  );
}
