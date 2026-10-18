import { MaterialIcons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';
import { useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { AppText as Text, AppTextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

export const BUDGET_CATEGORY_ICONS: IconName[] = [
  'restaurant',
  'directions-car',
  'home',
  'movie',
  'school',
  'shopping-cart',
  'local-cafe',
  'fitness-center',
  'medical-services',
  'payments',
  'receipt-long',
  'flight',
  'pets',
  'sports-esports',
  'phone-android',
  'local-grocery-store',
  'child-care',
  'card-giftcard',
  'volunteer-activism',
  'more-horiz',
];
export const BUDGET_CATEGORY_COLORS = ['#E45C3A', '#3C78D8', '#7E57C2', '#D64C7F', '#00897B', '#6B7280'];
const ALL_MATERIAL_ICONS = Object.keys(MaterialIcons.glyphMap).sort() as IconName[];
const RESULT_LIMIT = 60;

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
  const [query, setQuery] = useState('');
  const normalizedQuery = query.trim().toLowerCase();
  const visibleIcons = useMemo(() => {
    if (!normalizedQuery) return BUDGET_CATEGORY_ICONS;
    return ALL_MATERIAL_ICONS
      .filter((name) => name.toLowerCase().includes(normalizedQuery))
      .slice(0, RESULT_LIMIT);
  }, [normalizedQuery]);

  return (
    <View style={{ gap: 14 }}>
      <View style={{ gap: 8 }}>
        <Text style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>Material icon</Text>
        <AppTextInput
          accessibilityLabel="Search all Material icons"
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={setQuery}
          placeholder="Search all Material icons"
          placeholderTextColor={authColors.outline}
          value={query}
          style={{
            minHeight: 46,
            borderWidth: 1,
            borderColor: authColors.outlineVariant,
            borderRadius: 12,
            backgroundColor: authColors.surfaceContainerLowest,
            paddingHorizontal: 13,
            fontFamily: authFont.regular,
            fontSize: 15,
            color: authColors.onSurface,
          }}
        />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {visibleIcons.map((name) => {
            const selected = icon === name;
            return <Pressable key={name} accessibilityLabel={`${name} icon`} accessibilityRole="radio" accessibilityState={{ checked: selected }} onPress={() => onIconChange(name)} style={{ width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: selected ? authColors.primary : authColors.outlineVariant, backgroundColor: selected ? authColors.primaryFixed : authColors.surfaceContainerLowest }}><MaterialIcons name={name} size={22} color={selected ? authColors.primary : authColors.onSurfaceVariant} /></Pressable>;
          })}
        </View>
        {visibleIcons.length === 0 ? <Text style={{ fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant }}>No matching Material icons.</Text> : null}
        {normalizedQuery && visibleIcons.length === RESULT_LIMIT ? <Text style={{ fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant }}>Showing the first {RESULT_LIMIT} matches. Refine the search to narrow the list.</Text> : null}
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
