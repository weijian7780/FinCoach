import type { TextInputProps } from 'react-native';
import { Text, TextInput, View } from 'react-native';

import { colors, radius, spacing, typography } from '@/constants/design';

type TextFieldProps = TextInputProps & {
  label: string;
};

export function TextField({ label, style, ...props }: TextFieldProps) {
  return (
    <View style={{ gap: spacing.xs }}>
      <Text style={typography.label} selectable>
        {label}
      </Text>
      <TextInput
        placeholderTextColor={colors.placeholder}
        style={[
          {
            minHeight: 52,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.surfaceAlt,
            paddingHorizontal: spacing.md,
            color: colors.text,
            fontSize: 16,
          },
          style,
        ]}
        {...props}
      />
    </View>
  );
}
