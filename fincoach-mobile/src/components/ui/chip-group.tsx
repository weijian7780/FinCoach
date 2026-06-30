import { Pressable, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

// Single-select pill group used across the financial-profile screens.
export function ChipGroup({
  options,
  value,
  onSelect,
}: {
  options: readonly string[];
  value: string | null;
  onSelect: (value: string) => void;
}) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {options.map((option) => {
        const selected = value === option;
        return (
          <Pressable
            key={option}
            onPress={() => onSelect(option)}
            style={{
              paddingHorizontal: 14,
              paddingVertical: 9,
              borderRadius: 999,
              borderWidth: 1.5,
              borderColor: selected ? authColors.primary : 'transparent',
              backgroundColor: selected ? authColors.primaryFixed : authColors.surfaceContainer,
            }}>
            <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: selected ? authColors.primary : authColors.onSurfaceVariant }}>
              {option}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
