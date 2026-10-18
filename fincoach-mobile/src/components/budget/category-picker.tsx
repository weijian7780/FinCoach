import { MaterialIcons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { CategoryIcon } from '@/components/categories/category-icon';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import type { Category } from '@/lib/types';

export function CategoryPicker({
  categories,
  onToggle,
  selectedIds,
}: {
  categories: Category[];
  onToggle: (category: Category) => void;
  selectedIds: number[];
}) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
      {categories.map((category) => {
        const selected = selectedIds.includes(category.id);
        return (
          <Pressable key={category.id} accessibilityLabel={`${category.name} category`} accessibilityRole="checkbox" accessibilityState={{ checked: selected }} onPress={() => onToggle(category)} style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 7, minHeight: 42, paddingHorizontal: 13, borderRadius: 999, borderWidth: selected ? 1.5 : 0, borderColor: selected ? authColors.primary : 'transparent', backgroundColor: selected ? authColors.primaryFixed : authColors.surfaceContainerHigh, opacity: pressed ? 0.75 : 1 })}>
            <CategoryIcon category={category} size={25} glyphSize={15} />
            <Text style={{ fontFamily: authFont.semibold, fontSize: 14, color: selected ? authColors.primary : authColors.onSurface }}>{category.name}</Text>
            {selected ? <MaterialIcons name="check" size={16} color={authColors.primary} /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}
