import { View } from 'react-native';

import { authColors } from '@/constants/auth-theme';

export function BudgetProgress({
  color = authColors.primary,
  height = 8,
  ratio,
}: {
  color?: string;
  height?: number;
  ratio: number;
}) {
  const width = `${Math.round(Math.min(1, Math.max(0, ratio)) * 100)}%` as const;
  return (
    <View accessibilityLabel={`${Math.round(Math.max(0, ratio) * 100)}% used`} accessibilityRole="progressbar" style={{ height, borderRadius: 999, overflow: 'hidden', backgroundColor: authColors.surfaceContainerHigh }}>
      <View style={{ width, height: '100%', borderRadius: 999, backgroundColor: color }} />
    </View>
  );
}
