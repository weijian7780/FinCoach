import { MaterialIcons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { Pressable, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

export const BUDGET_CATEGORY_ICONS: IconName[] = ['restaurant', 'directions-car', 'home', 'movie', 'school', 'shopping-cart', 'local-cafe', 'fitness-center', 'medical-services', 'more-horiz'];
export const BUDGET_CATEGORY_COLORS = ['#E45C3A', '#3C78D8', '#7E57C2', '#D64C7F', '#00897B', '#6B7280'];

export function IconColorPicker({
  color,
  icon,
  onColorChange,
  onIconChange,
}: {
  color: string;
  icon: string;
  onColorChange: (color: string) => void;
  onIconChange: (icon: string) => void;
}) {
  return (
    <View style={{ gap: 14 }}>
      <View style={{ gap: 8 }}>
        <Text style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>Icon</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {BUDGET_CATEGORY_ICONS.map((name) => {
            const selected = icon === name;
            return <Pressable key={name} accessibilityLabel={`${name} icon`} accessibilityRole="radio" accessibilityState={{ checked: selected }} onPress={() => onIconChange(name)} style={{ width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: selected ? authColors.primary : authColors.outlineVariant, backgroundColor: selected ? authColors.primaryFixed : authColors.surfaceContainerLowest }}><MaterialIcons name={name} size={22} color={selected ? authColors.primary : authColors.onSurfaceVariant} /></Pressable>;
          })}
        </View>
      </View>
      <View style={{ gap: 8 }}>
        <Text style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>Colour</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {BUDGET_CATEGORY_COLORS.map((value) => {
            const selected = color === value;
            return <Pressable key={value} accessibilityLabel={`${value} colour`} accessibilityRole="radio" accessibilityState={{ checked: selected }} onPress={() => onColorChange(value)} style={{ width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: value, borderWidth: selected ? 3 : 0, borderColor: authColors.onSurface }}>{selected ? <MaterialIcons name="check" size={20} color="#FFFFFF" /> : null}</Pressable>;
          })}
        </View>
      </View>
    </View>
  );
}
