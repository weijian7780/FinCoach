import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BUDGET_CATEGORY_COLORS, BUDGET_CATEGORY_ICONS, IconColorPicker } from '@/components/budget/icon-color-picker';
import { CategoryIcon } from '@/components/categories/category-icon';
import { AppText as Text, AppTextInput } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { createCustomCategory, deleteCustomCategory, fetchBudgetCategories, updateCustomCategory } from '@/lib/budget';
import { validateCustomCategory } from '@/lib/budget-domain';
import { useAuth } from '@/lib/auth-context';
import {
  base64ByteLength,
  CATEGORY_ICON_MAX_BYTES,
  categoryIconExtension,
} from '@/lib/category-icon-domain';
import {
  deleteCategoryIcon,
  uploadCategoryIcon,
} from '@/lib/category-icons';
import type { Category } from '@/lib/types';

type ImagePickerModule = typeof import('expo-image-picker');
type ImagePickerRuntime = Pick<ImagePickerModule, 'launchImageLibraryAsync' | 'requestMediaLibraryPermissionsAsync'>;
type PendingImage = {
  base64: string;
  extension: ReturnType<typeof categoryIconExtension>;
  uri: string;
};
type AppearanceMode = 'image' | 'material';

const initialForm = {
  name: '',
  icon: BUDGET_CATEGORY_ICONS[0] as string,
  iconImagePath: null as string | null,
  color: BUDGET_CATEGORY_COLORS[0],
};

async function loadImagePicker(): Promise<ImagePickerRuntime | null> {
  try {
    const module = await import('expo-image-picker');
    const candidates = [module, (module as { default?: unknown }).default];
    for (const candidate of candidates) {
      const picker = candidate as Partial<ImagePickerRuntime> | undefined;
      if (typeof picker?.launchImageLibraryAsync === 'function') return picker as ImagePickerRuntime;
    }
    throw new Error('The photo picker native module is unavailable.');
  } catch (error) {
    console.error('Could not load expo-image-picker.', error);
    appDialog.open(
      'Photo picker unavailable',
      'Rebuild and reinstall the development build so photo upload is included.',
    );
    return null;
  }
}

function categoryError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('duplicate') || message.includes('categories_user_name_unique')) return 'A custom category with this name already exists.';
  if (message.includes('category-icons') || message.includes('storage')) return 'Run the custom category icon migration in Supabase before uploading an image.';
  if (message.includes('categories') || message.includes('schema cache')) return 'Run the Budget migration in Supabase before managing categories.';
  return 'Could not save the category. Check your connection and try again.';
}

export default function ManageCategoriesScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState<Category | null>(null);
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null);
  const [appearanceMode, setAppearanceMode] = useState<AppearanceMode>('material');

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try { setCategories(await fetchBudgetCategories(userId)); setMessage(null); }
    catch (error) { setMessage(categoryError(error)); }
    finally { setLoading(false); }
  }, [userId]);

  useEffect(() => {
    const task = setTimeout(() => { void load(); }, 0);
    return () => clearTimeout(task);
  }, [load]);

  const systemCategories = categories.filter((category) => category.user_id == null);
  const customCategories = categories.filter((category) => category.user_id === userId);
  const hasPersonalImage = Boolean(pendingImage || form.iconImagePath);

  function beginEdit(category: Category) {
    setEditing(category);
    setForm({
      name: category.name,
      icon: category.icon ?? initialForm.icon,
      iconImagePath: category.icon_image_path ?? null,
      color: category.color ?? initialForm.color,
    });
    setPendingImage(null);
    setAppearanceMode(category.icon_image_path ? 'image' : 'material');
    setErrors({});
    setMessage(null);
  }

  function resetForm() {
    setEditing(null);
    setForm(initialForm);
    setPendingImage(null);
    setAppearanceMode('material');
    setErrors({});
  }

  async function pickPersonalImage() {
    const imagePicker = await loadImagePicker();
    if (!imagePicker) return;

    try {
      const permission = await imagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        appDialog.open('Permission needed', 'Allow photo access to choose a category image.');
        return;
      }
      const result = await imagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.75,
        base64: true,
      });
      const asset = result.assets?.[0];
      if (result.canceled || !asset?.base64) return;

      const imageBytes = asset.fileSize ?? base64ByteLength(asset.base64);
      if (imageBytes > CATEGORY_ICON_MAX_BYTES) {
        appDialog.open('Image too large', 'Choose a JPG, PNG or WebP image smaller than 2 MB.');
        return;
      }
      setPendingImage({
        base64: asset.base64,
        extension: categoryIconExtension(asset.uri, asset.mimeType),
        uri: asset.uri,
      });
      setAppearanceMode('image');
      setMessage(null);
    } catch (error) {
      appDialog.open(
        'Could not choose image',
        error instanceof Error ? error.message : 'Try choosing another image.',
      );
    }
  }

  function chooseMaterialIcon(icon: string) {
    setAppearanceMode('material');
    setForm((current) => ({ ...current, icon }));
    setErrors((current) => ({ ...current, icon: '' }));
  }

  function removePersonalImage() {
    setPendingImage(null);
    setForm((current) => ({ ...current, iconImagePath: null }));
    setAppearanceMode('material');
    setErrors((current) => ({ ...current, icon: '' }));
  }

  async function save() {
    if (!userId) return;
    const otherNames = categories.filter((category) => category.id !== editing?.id).map((category) => category.name);
    const nextErrors = validateCustomCategory(form, otherNames);
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }
    setSaving(true);
    setMessage(null);
    let uploadedPath: string | null = null;
    try {
      let iconImagePath = appearanceMode === 'image' ? form.iconImagePath : null;
      if (appearanceMode === 'image' && pendingImage) {
        uploadedPath = await uploadCategoryIcon(
          userId,
          pendingImage.base64,
          pendingImage.extension,
        );
        iconImagePath = uploadedPath;
      }
      const input = {
        name: form.name.trim(),
        icon: form.icon,
        icon_image_path: iconImagePath,
        color: form.color,
      };
      if (editing) await updateCustomCategory(editing.id, userId, input);
      else await createCustomCategory(userId, input);
      if (editing?.icon_image_path && editing.icon_image_path !== iconImagePath) {
        await deleteCategoryIcon(editing.icon_image_path).catch((error) => {
          console.warn('The replaced category image could not be removed.', error);
        });
      }
      resetForm();
      await load();
    } catch (error) {
      if (uploadedPath) {
        await deleteCategoryIcon(uploadedPath).catch(() => undefined);
      }
      setMessage(categoryError(error));
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(category: Category) {
    if (!userId || category.user_id !== userId) return;
    appDialog.open('Delete custom category?', `Delete ${category.name} and its category limits?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          setSaving(true);
          deleteCustomCategory(category.id, userId)
            .then(async () => {
              await deleteCategoryIcon(category.icon_image_path).catch((error) => {
                console.warn('The deleted category image could not be removed.', error);
              });
              if (editing?.id === category.id) resetForm();
              await load();
            })
            .catch((error) => setMessage(categoryError(error)))
            .finally(() => setSaving(false));
        },
      },
    ]);
  }

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 10, paddingHorizontal: 20, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}><Pressable accessibilityLabel="Go back" accessibilityRole="button" onPress={() => router.back()} style={iconButton}><MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} /></Pressable><View style={{ flex: 1 }}><Text selectable style={{ fontFamily: authFont.bold, fontSize: 22, color: authColors.onSurface }}>Manage Categories</Text><Text selectable style={{ fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant }}>Personalise how you track spending.</Text></View></View>

      {loading && categories.length === 0 ? <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}><ActivityIndicator color={authColors.primary} /><Text>Loading…</Text></View> : (
        <ScrollView keyboardShouldPersistTaps="handled" contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: insets.bottom + 40, gap: 22 }}>
          {message ? <Text selectable accessibilityRole="alert" style={errorBox}>{message}</Text> : null}

          <View style={sectionCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              {appearanceMode === 'image' && !hasPersonalImage
                ? <View style={emptyHeaderPreview}><MaterialIcons name="add-photo-alternate" size={21} color={authColors.primary} /></View>
                : <CategoryIcon category={{ color: form.color, icon: form.icon, icon_image_path: appearanceMode === 'image' ? form.iconImagePath : null }} imageUri={appearanceMode === 'image' ? pendingImage?.uri : null} size={40} glyphSize={21} />}
              <View style={{ flex: 1 }}><Text style={sectionTitle}>{editing ? `Edit ${editing.name}` : 'Add custom category'}</Text><Text selectable style={helperText}>Choose a name, icon or image, and colour.</Text></View>
            </View>
            <View style={{ gap: 6 }}><Text style={fieldLabel}>Category name</Text><AppTextInput accessibilityLabel="Category name" maxLength={50} value={form.name} onChangeText={(name) => { setForm((current) => ({ ...current, name })); setErrors((current) => ({ ...current, name: '' })); }} placeholder="e.g. Groceries" placeholderTextColor={authColors.outline} style={[textInput, errors.name ? { borderColor: authColors.error } : null]} />{errors.name ? <Text selectable style={fieldError}>{errors.name}</Text> : null}</View>

            <View style={{ gap: 8 }}>
              <Text style={fieldLabel}>Category appearance</Text>
              <Text selectable style={helperText}>Choose one way to identify this category.</Text>
              <View accessibilityRole="radiogroup" style={appearanceSegment}>
                <Pressable
                  accessibilityLabel="Use a Material icon"
                  accessibilityRole="radio"
                  accessibilityState={{ checked: appearanceMode === 'material' }}
                  disabled={saving}
                  onPress={() => setAppearanceMode('material')}
                  style={({ pressed }) => [appearanceSegmentOption, appearanceMode === 'material' && appearanceSegmentOptionSelected, { opacity: saving ? 0.45 : pressed ? 0.65 : 1 }]}
                >
                  <MaterialIcons name="apps" size={21} color={appearanceMode === 'material' ? authColors.primary : authColors.onSurfaceVariant} />
                  <Text style={[appearanceSegmentText, appearanceMode === 'material' && appearanceSegmentTextSelected]}>Material icon</Text>
                </Pressable>
                <Pressable
                  accessibilityLabel="Use a personal image"
                  accessibilityRole="radio"
                  accessibilityState={{ checked: appearanceMode === 'image' }}
                  disabled={saving}
                  onPress={() => setAppearanceMode('image')}
                  style={({ pressed }) => [appearanceSegmentOption, appearanceMode === 'image' && appearanceSegmentOptionSelected, { opacity: saving ? 0.45 : pressed ? 0.65 : 1 }]}
                >
                  <MaterialIcons name="image" size={21} color={appearanceMode === 'image' ? authColors.primary : authColors.onSurfaceVariant} />
                  <Text style={[appearanceSegmentText, appearanceMode === 'image' && appearanceSegmentTextSelected]}>Personal image</Text>
                </Pressable>
              </View>
            </View>

            {appearanceMode === 'material' ? (
              <>
                <IconColorPicker icon={form.icon} color={form.color} onIconChange={chooseMaterialIcon} onColorChange={(color) => { setForm((current) => ({ ...current, color })); setErrors((current) => ({ ...current, color: '' })); }} />
                {errors.icon ? <Text selectable style={fieldError}>{errors.icon}</Text> : null}{errors.color ? <Text selectable style={fieldError}>{errors.color}</Text> : null}
              </>
            ) : (
              <View style={personalImagePanel}>
                {hasPersonalImage
                  ? <CategoryIcon category={{ color: form.color, icon: form.icon, icon_image_path: form.iconImagePath }} imageUri={pendingImage?.uri} size={112} glyphSize={54} />
                  : <View style={emptyImagePreview}><MaterialIcons name="add-photo-alternate" size={44} color={authColors.primary} /></View>}
                <Text selectable style={personalImageStatus}>{hasPersonalImage ? 'Personal image selected' : 'No image selected'}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 10 }}>
                  <Pressable accessibilityLabel={hasPersonalImage ? 'Change personal category image' : 'Upload personal category image'} accessibilityRole="button" disabled={saving} onPress={() => void pickPersonalImage()} style={({ pressed }) => [secondaryActionButton, { opacity: saving ? 0.45 : pressed ? 0.65 : 1 }]}><MaterialIcons name="add-photo-alternate" size={19} color={authColors.primary} /><Text style={secondaryButtonText}>{hasPersonalImage ? 'Change image' : 'Upload image'}</Text></Pressable>
                  {hasPersonalImage ? <Pressable accessibilityLabel="Remove personal category image" accessibilityRole="button" disabled={saving} onPress={removePersonalImage} style={({ pressed }) => [removeImageButton, { opacity: saving ? 0.45 : pressed ? 0.65 : 1 }]}><MaterialIcons name="delete-outline" size={19} color={authColors.primary} /><Text style={secondaryButtonText}>Remove</Text></Pressable> : null}
                </View>
                <Text selectable style={[helperText, { textAlign: 'center' }]}>JPG, PNG or WebP, maximum 2 MB.</Text>
              </View>
            )}

            <View style={{ flexDirection: 'row', gap: 10 }}>{editing ? <Pressable disabled={saving} onPress={resetForm} style={[secondaryButton, { flex: 1 }]}><Text style={secondaryButtonText}>Cancel</Text></Pressable> : null}<Pressable disabled={saving} onPress={() => void save()} style={[primaryButton, { flex: 1 }, saving && { opacity: 0.55 }]}>{saving ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name={editing ? 'save' : 'add'} size={20} color={authColors.onPrimary} />}<Text style={primaryButtonText}>{editing ? 'Save changes' : 'Add category'}</Text></Pressable></View>
          </View>

          <View style={{ gap: 10 }}><Text style={sectionTitle}>System categories</Text><Text selectable style={helperText}>Ready to use in every budget.</Text><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>{systemCategories.map((category) => <CategoryChip key={category.id} category={category} />)}</View></View>

          <View style={{ gap: 10 }}><Text style={sectionTitle}>Your custom categories</Text>{customCategories.length === 0 ? <View style={[sectionCard, { alignItems: 'center' }]}><MaterialIcons name="category" size={26} color={authColors.outline} /><Text selectable style={helperText}>No custom categories yet.</Text></View> : customCategories.map((category) => <CategoryRow key={category.id} category={category} onEdit={() => beginEdit(category)} onDelete={() => confirmDelete(category)} />)}</View>
        </ScrollView>
      )}
    </View>
  );
}

function CategoryChip({ category }: { category: Category }) {
  const color = category.color ?? authColors.primary;
  return <View style={categoryChip}><CategoryIcon category={category} size={25} glyphSize={15} tintColor={color} /><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>{category.name}</Text></View>;
}

function CategoryRow({ category, onDelete, onEdit }: { category: Category; onDelete?: () => void; onEdit?: () => void }) {
  return <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest, borderRadius: 15, padding: 12 }}><CategoryIcon category={category} size={42} glyphSize={22} /><Text selectable style={{ flex: 1, fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface }}>{category.name}</Text>{onEdit ? <Pressable accessibilityLabel={`Edit ${category.name}`} onPress={onEdit} style={smallButton}><MaterialIcons name="edit" size={19} color={authColors.primary} /></Pressable> : <MaterialIcons name="lock-outline" size={19} color={authColors.outline} />}{onDelete ? <Pressable accessibilityLabel={`Delete ${category.name}`} onPress={onDelete} style={smallButton}><MaterialIcons name="delete-outline" size={19} color={authColors.error} /></Pressable> : null}</View>;
}

const iconButton = { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const;
const smallButton = { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const;
const categoryChip = { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 13, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh } as const;
const sectionCard = { gap: 14, padding: 16, borderRadius: 16, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 4px 12px rgba(27, 27, 35, 0.06)' } as const;
const sectionTitle = { fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface } as const;
const helperText = { fontFamily: authFont.regular, fontSize: 13, lineHeight: 18, color: authColors.onSurfaceVariant } as const;
const fieldLabel = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface } as const;
const fieldError = { fontFamily: authFont.regular, fontSize: 12, color: authColors.error } as const;
const textInput = { minHeight: 48, borderWidth: 1, borderColor: authColors.outlineVariant, borderRadius: 12, backgroundColor: authColors.surfaceContainerLowest, paddingHorizontal: 14, fontFamily: authFont.regular, fontSize: 16, color: authColors.onSurface } as const;
const errorBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', fontFamily: authFont.regular, fontSize: 13, color: authColors.error } as const;
const emptyHeaderPreview = { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed } as const;
const appearanceSegment = { minHeight: 54, flexDirection: 'row', borderWidth: 1, borderColor: authColors.outlineVariant, borderRadius: 12, overflow: 'hidden', backgroundColor: authColors.surfaceContainerLowest } as const;
const appearanceSegmentOption = { flex: 1, minHeight: 52, paddingHorizontal: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: authColors.surfaceContainerLowest } as const;
const appearanceSegmentOptionSelected = { borderWidth: 1.5, borderColor: authColors.primary, borderRadius: 11, backgroundColor: authColors.primaryFixed } as const;
const appearanceSegmentText = { flexShrink: 1, fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurfaceVariant } as const;
const appearanceSegmentTextSelected = { color: authColors.primary } as const;
const personalImagePanel = { alignItems: 'center', gap: 12, paddingVertical: 8 } as const;
const emptyImagePreview = { width: 112, height: 112, borderRadius: 56, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: authColors.primaryFixedDim, backgroundColor: authColors.primaryFixed } as const;
const personalImageStatus = { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface } as const;
const primaryButton = { minHeight: 48, borderRadius: 12, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingHorizontal: 14, boxShadow: '0 4px 12px rgba(70, 72, 212, 0.20)' } as const;
const primaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary } as const;
const secondaryButton = { minHeight: 48, borderRadius: 12, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14 } as const;
const secondaryActionButton = { minHeight: 44, borderRadius: 12, backgroundColor: authColors.primaryFixed, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingHorizontal: 12 } as const;
const removeImageButton = { minHeight: 44, borderRadius: 12, borderWidth: 1, borderColor: authColors.primary, backgroundColor: authColors.surfaceContainerLowest, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingHorizontal: 12 } as const;
const secondaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary } as const;
