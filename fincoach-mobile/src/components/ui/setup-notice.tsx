import { Text, View } from 'react-native';

import { colors, radius, spacing, typography } from '@/constants/design';

export function SetupNotice() {
  return (
    <View
      style={{
        borderRadius: radius.md,
        backgroundColor: '#FFF7ED',
        borderWidth: 1,
        borderColor: '#FED7AA',
        padding: spacing.md,
      }}>
      <Text style={[typography.captionStrong, { color: colors.warningText }]} selectable>
        Supabase env values are missing. Add `.env` before live auth testing.
      </Text>
    </View>
  );
}
