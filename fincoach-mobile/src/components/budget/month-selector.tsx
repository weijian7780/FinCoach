import { MaterialIcons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { formatBudgetMonth } from '@/lib/budget-domain';

export function MonthSelector({
  month,
  onNext,
  onPrevious,
}: {
  month: string;
  onNext: () => void;
  onPrevious: () => void;
}) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <Pressable accessibilityLabel="Previous month" accessibilityRole="button" onPress={onPrevious} hitSlop={8} style={({ pressed }) => ({ width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? authColors.primaryFixed : authColors.surfaceContainerLow })}>
        <MaterialIcons name="chevron-left" size={23} color={authColors.primary} />
      </Pressable>
      <Text selectable style={{ minWidth: 116, textAlign: 'center', fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface }}>
        {formatBudgetMonth(month)}
      </Text>
      <Pressable accessibilityLabel="Next month" accessibilityRole="button" onPress={onNext} hitSlop={8} style={({ pressed }) => ({ width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? authColors.primaryFixed : authColors.surfaceContainerLow })}>
        <MaterialIcons name="chevron-right" size={23} color={authColors.primary} />
      </Pressable>
    </View>
  );
}
