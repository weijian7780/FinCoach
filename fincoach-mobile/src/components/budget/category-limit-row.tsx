import { MaterialIcons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { CategoryIcon } from '@/components/categories/category-icon';
import { AppText as Text, AppTextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import type { Category } from '@/lib/types';

export function CategoryLimitRow({
  category,
  error,
  isLast = false,
  onChangeText,
  onRemove,
  value,
}: {
  category: Category;
  error?: string | null;
  isLast?: boolean;
  onChangeText: (value: string) => void;
  onRemove: () => void;
  value: string;
}) {
  const color = category.color ?? authColors.primary;

  return (
    <View>
      <View style={{ minHeight: 66, flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 7 }}>
        <CategoryIcon category={category} size={40} glyphSize={21} tintColor={color} />

        <Text
          numberOfLines={2}
          selectable
          style={{
            flex: 1,
            fontFamily: authFont.semibold,
            fontSize: 15,
            lineHeight: 19,
            color: authColors.onSurface,
          }}>
          {category.name}
        </Text>

        <View
          style={{
            width: 108,
            flexShrink: 0,
            minHeight: 46,
            flexDirection: 'row',
            alignItems: 'center',
            borderWidth: 1,
            borderColor: error ? authColors.error : authColors.outlineVariant,
            borderRadius: 12,
            backgroundColor: authColors.surfaceContainerLowest,
            paddingHorizontal: 10,
          }}>
          <Text style={{ fontFamily: authFont.regular, fontSize: 14, color: authColors.onSurfaceVariant }}>RM</Text>
          <AppTextInput
            accessibilityLabel={`${category.name} limit`}
            keyboardType="decimal-pad"
            onChangeText={onChangeText}
            placeholder="0"
            placeholderTextColor={authColors.outline}
            selectTextOnFocus
            value={value}
            style={{
              width: 62,
              minWidth: 0,
              flexGrow: 0,
              flexShrink: 1,
              paddingVertical: 11,
              paddingLeft: 6,
              textAlign: 'right',
              fontFamily: authFont.semibold,
              fontSize: 15,
              color: authColors.onSurface,
              fontVariant: ['tabular-nums'],
            }}
          />
        </View>

        <Pressable
          accessibilityLabel={`Remove ${category.name} limit`}
          accessibilityRole="button"
          hitSlop={8}
          onPress={onRemove}
          style={({ pressed }) => ({
            width: 40,
            height: 40,
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 12,
            opacity: pressed ? 0.55 : 1,
          })}>
          <MaterialIcons name="delete-outline" size={22} color={authColors.error} />
        </Pressable>
      </View>

      {error ? <Text selectable accessibilityRole="alert" style={{ paddingBottom: 8, fontFamily: authFont.regular, fontSize: 12, lineHeight: 16, color: authColors.error }}>{error}</Text> : null}
      {!isLast ? <View style={{ height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.55 }} /> : null}
    </View>
  );
}
