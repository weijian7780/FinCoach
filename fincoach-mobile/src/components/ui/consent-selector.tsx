import { Pressable, Text, View } from 'react-native';

import { colors, radius, spacing, typography } from '@/constants/design';
import type { ConsentStatus } from '@/lib/types';

type ConsentSelectorProps = {
  onChange: (value: ConsentStatus) => void;
  value: ConsentStatus;
};

const options: Array<{ label: string; value: ConsentStatus }> = [
  { label: 'Unset', value: 'unset' },
  { label: 'Granted', value: 'granted' },
  { label: 'Denied', value: 'denied' },
  { label: 'Withdrawn', value: 'withdrawn' },
];

export function ConsentSelector({ onChange, value }: ConsentSelectorProps) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Text style={typography.label} selectable>
        Spending records consent
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              onPress={() => onChange(option.value)}
              style={{
                minHeight: 42,
                justifyContent: 'center',
                borderRadius: radius.full,
                paddingHorizontal: spacing.md,
                backgroundColor: selected ? colors.primary : colors.surfaceAlt,
                borderWidth: 1,
                borderColor: selected ? colors.primary : colors.border,
              }}>
              <Text style={[typography.captionStrong, { color: selected ? colors.onPrimary : colors.text }]}>
                {option.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={typography.caption} selectable>
        Consent controls whether spending records can be used for personalized advice in later
        modules.
      </Text>
    </View>
  );
}
