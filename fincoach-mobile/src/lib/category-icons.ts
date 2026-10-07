import { decode } from 'base64-arraybuffer';
import * as Crypto from 'expo-crypto';

import {
  type CategoryIconExtension,
} from '@/lib/category-icon-domain';
import { supabase } from '@/lib/supabase';

export const CATEGORY_ICON_BUCKET = 'category-icons';

const CONTENT_TYPES: Record<CategoryIconExtension, string> = {
  jpg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
};

export async function uploadCategoryIcon(
  userId: string,
  base64: string,
  extension: CategoryIconExtension,
) {
  const path = `${userId}/${Crypto.randomUUID()}.${extension}`;
  const { error } = await supabase.storage
    .from(CATEGORY_ICON_BUCKET)
    .upload(path, decode(base64), {
      contentType: CONTENT_TYPES[extension],
      upsert: false,
    });

  if (error) throw error;
  return path;
}

export async function deleteCategoryIcon(path: string | null | undefined) {
  if (!path) return;
  const { error } = await supabase.storage.from(CATEGORY_ICON_BUCKET).remove([path]);
  if (error) throw error;
}

export function categoryIconPublicUrl(path: string | null | undefined) {
  if (!path) return null;
  return supabase.storage.from(CATEGORY_ICON_BUCKET).getPublicUrl(path).data.publicUrl;
}
