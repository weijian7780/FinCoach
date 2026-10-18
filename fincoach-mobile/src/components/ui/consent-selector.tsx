import { Pressable, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { declinedSpendingConsentStatus } from '@/lib/spending-consent';
import type { ConsentStatus } from '@/lib/types';

type ConsentSelectorProps = {
  disabled?: boolean;
  onChange: (value: ConsentStatus) => void;
  requiredForQuestion?: boolean;
  value: ConsentStatus;
};

export function ConsentSelector({
  disabled = false,
  onChange,
  requiredForQuestion = false,
  value,
}: ConsentSelectorProps) {
  const allowLabel = requiredForQuestion ? 'Allow and continue' : 'Allow access';
  const declineLabel = requiredForQuestion ? 'Continue without data' : 'Not now';

  return (
    <View style={{ gap: 10 }}>
      <Text selectable style={{ color: authColors.onSurface, fontFamily: authFont.semibold, fontSize: 15 }}>
        Use your recorded spending?
      </Text>
      <Text selectable style={{ color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 13, lineHeight: 19 }}>
        Allow FinCoach to use transactions you record for personalised answers. It cannot
        access your bank account.
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        <Pressable
          accessibilityLabel={allowLabel}
          accessibilityRole="button"
          accessibilityState={{ disabled }}
          disabled={disabled}
          onPress={() => onChange('granted')}
          style={({ pressed }) => ({
            minWidth: 136,
            minHeight: 44,
            flexGrow: 1,
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 14,
            paddingHorizontal: 14,
            backgroundColor: authColors.primary,
            opacity: disabled ? 0.55 : pressed ? 0.82 : 1,
          })}>
          <Text style={{ color: authColors.onPrimary, fontFamily: authFont.semibold, fontSize: 13 }}>
            {allowLabel}
          </Text>
        </Pressable>
        <Pressable
          accessibilityLabel={declineLabel}
          accessibilityRole="button"
          accessibilityState={{ disabled }}
          disabled={disabled}
          onPress={() => onChange(declinedSpendingConsentStatus(value))}
          style={({ pressed }) => ({
            minWidth: 136,
            minHeight: 44,
            flexGrow: 1,
            alignItems: 'center',
            justifyContent: 'center',
            borderWidth: 1,
            borderColor: authColors.primary,
            borderRadius: 14,
            paddingHorizontal: 14,
            backgroundColor: authColors.surfaceContainerLowest,
            opacity: disabled ? 0.55 : pressed ? 0.7 : 1,
          })}>
          <Text style={{ color: authColors.primary, fontFamily: authFont.semibold, fontSize: 13 }}>
            {declineLabel}
          </Text>
        </Pressable>
      </View>
      <Text selectable style={{ color: authColors.outline, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 }}>
        {requiredForQuestion
          ? 'Without access, FinCoach can give general guidance but cannot calculate your exact transaction totals.'
          : 'You can allow access later when a question needs your transaction records.'}
      </Text>
    </View>
  );
}
