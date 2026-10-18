import { MaterialIcons } from '@expo/vector-icons';
import { View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authFont } from '@/constants/auth-theme';
import type { LimitStatus } from '@/lib/budget-domain';

const tones = {
  success: { background: '#D7F8E8', foreground: '#006C49', icon: 'check-circle' as const },
  warning: { background: '#FFF0C7', foreground: '#7A5700', icon: 'warning' as const },
  danger: { background: '#FFDAD6', foreground: '#93000A', icon: 'error' as const },
};

export function StatusBadge({ status }: { status: LimitStatus }) {
  const tone = tones[status.tone];
  return (
    <View accessibilityLabel={status.label} style={{ alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, backgroundColor: tone.background }}>
      <MaterialIcons name={tone.icon} size={14} color={tone.foreground} />
      <Text style={{ fontFamily: authFont.semibold, fontSize: 11, color: tone.foreground }}>{status.label}</Text>
    </View>
  );
}
