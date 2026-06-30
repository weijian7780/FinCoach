import { View } from 'react-native';

import { colors } from '@/constants/design';

export function Screen({ children }: { children: React.ReactNode }) {
  return <View style={{ flex: 1, backgroundColor: colors.background }}>{children}</View>;
}
