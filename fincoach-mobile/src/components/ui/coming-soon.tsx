import { MaterialIcons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

// Placeholder for tabs whose modules aren't built yet.
export function ComingSoon({ icon, title }: { icon: ComponentProps<typeof MaterialIcons>['name']; title: string }) {
  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 }}>
      <View
        style={{ width: 64, height: 64, borderRadius: 999, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center' }}>
        <MaterialIcons name={icon} size={32} color={authColors.primary} />
      </View>
      <Text style={{ fontSize: 20, fontFamily: authFont.bold, color: authColors.onSurface }}>{title}</Text>
      <Text style={{ fontSize: 14, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Coming soon</Text>
    </View>
  );
}
