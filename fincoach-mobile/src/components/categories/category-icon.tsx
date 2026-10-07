import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { View } from 'react-native';

import { authColors } from '@/constants/auth-theme';
import { categoryIconPublicUrl } from '@/lib/category-icons';
import type { Category } from '@/lib/types';

type CategoryVisual = Pick<Category, 'color' | 'icon' | 'icon_image_path'>;

export function CategoryIcon({
  backgroundColor,
  category,
  glyphSize,
  imageUri,
  size,
  tintColor,
}: {
  backgroundColor?: string;
  category: CategoryVisual;
  glyphSize?: number;
  imageUri?: string | null;
  size: number;
  tintColor?: string;
}) {
  const color = tintColor ?? category.color ?? authColors.primary;
  const uri = imageUri === undefined
    ? categoryIconPublicUrl(category.icon_image_path)
    : imageUri;

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        backgroundColor: backgroundColor ?? `${color}1F`,
      }}>
      {uri ? (
        <Image
          source={{ uri }}
          contentFit="cover"
          transition={120}
          style={{ width: size, height: size }}
        />
      ) : (
        <MaterialIcons
          name={(category.icon ?? 'category') as never}
          size={glyphSize ?? Math.round(size * 0.52)}
          color={color}
        />
      )}
    </View>
  );
}
