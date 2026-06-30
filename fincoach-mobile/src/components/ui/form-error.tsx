import { Text } from 'react-native';

import { colors, typography } from '@/constants/design';

export function FormError({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }

  return (
    <Text style={[typography.body, { color: colors.danger }]} selectable>
      {message}
    </Text>
  );
}
