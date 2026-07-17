import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BUDGET_CATEGORY_COLORS, BUDGET_CATEGORY_ICONS, IconColorPicker } from '@/components/budget/icon-color-picker';
import { AppText as Text, AppTextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { createCustomCategory, deleteCustomCategory, fetchBudgetCategories, updateCustomCategory } from '@/lib/budget';
import { validateCustomCategory } from '@/lib/budget-domain';
import { useAuth } from '@/lib/auth-context';
import type { Category } from '@/lib/types';

const initialForm = { name: '', icon: BUDGET_CATEGORY_ICONS[0] as string, color: BUDGET_CATEGORY_COLORS[0] };

function categoryError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('duplicate') || message.includes('categories_user_name_unique')) return 'A custom category with this name already exists.';
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

  function beginEdit(category: Category) {
    setEditing(category);
    setForm({ name: category.name, icon: category.icon ?? initialForm.icon, color: category.color ?? initialForm.color });
    setErrors({});
    setMessage(null);
  }

  function resetForm() {
    setEditing(null);
    setForm(initialForm);
    setErrors({});
  }

  async function save() {
    if (!userId) return;
    const otherNames = categories.filter((category) => category.id !== editing?.id).map((category) => category.name);
    const nextErrors = validateCustomCategory(form, otherNames);
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }
    setSaving(true);
    setMessage(null);
    try {
      const input = { name: form.name.trim(), icon: form.icon, color: form.color };
      if (editing) await updateCustomCategory(editing.id, userId, input);
      else await createCustomCategory(userId, input);
      resetForm();
      await load();
    } catch (error) {
      setMessage(categoryError(error));
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(category: Category) {
    if (!userId || category.user_id !== userId) return;
    Alert.alert('Delete custom category?', `Delete ${category.name} and its category limits?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => { setSaving(true); deleteCustomCategory(category.id, userId).then(async () => { if (editing?.id === category.id) resetForm(); await load(); }).catch((error) => setMessage(categoryError(error))).finally(() => setSaving(false)); } },
    ]);
  }

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 10, paddingHorizontal: 20, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}><Pressable accessibilityLabel="Go back" accessibilityRole="button" onPress={() => router.back()} style={iconButton}><MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} /></Pressable><View style={{ flex: 1 }}><Text selectable style={{ fontFamily: authFont.bold, fontSize: 22, color: authColors.onSurface }}>Manage Categories</Text><Text selectable style={{ fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant }}>Personalise how you track spending.</Text></View></View>

      {loading && categories.length === 0 ? <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}><ActivityIndicator color={authColors.primary} /><Text>Loading…</Text></View> : (
        <ScrollView keyboardShouldPersistTaps="handled" contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: insets.bottom + 40, gap: 22 }}>
          {message ? <Text selectable accessibilityRole="alert" style={errorBox}>{message}</Text> : null}

          <View style={sectionCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}><View style={{ width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: `${form.color}1F` }}><MaterialIcons name={form.icon as never} size={21} color={form.color} /></View><View style={{ flex: 1 }}><Text style={sectionTitle}>{editing ? `Edit ${editing.name}` : 'Add custom category'}</Text><Text selectable style={helperText}>Choose a name, icon and colour.</Text></View></View>
            <View style={{ gap: 6 }}><Text style={fieldLabel}>Category name</Text><AppTextInput accessibilityLabel="Category name" maxLength={50} value={form.name} onChangeText={(name) => { setForm((current) => ({ ...current, name })); setErrors((current) => ({ ...current, name: '' })); }} placeholder="e.g. Groceries" placeholderTextColor={authColors.outline} style={[textInput, errors.name ? { borderColor: authColors.error } : null]} />{errors.name ? <Text selectable style={fieldError}>{errors.name}</Text> : null}</View>
            <IconColorPicker icon={form.icon} color={form.color} onIconChange={(icon) => { setForm((current) => ({ ...current, icon })); setErrors((current) => ({ ...current, icon: '' })); }} onColorChange={(color) => { setForm((current) => ({ ...current, color })); setErrors((current) => ({ ...current, color: '' })); }} />
            {errors.icon ? <Text selectable style={fieldError}>{errors.icon}</Text> : null}{errors.color ? <Text selectable style={fieldError}>{errors.color}</Text> : null}
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
  return <View style={categoryChip}><View style={{ width: 25, height: 25, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: `${color}1F` }}><MaterialIcons name={(category.icon ?? 'category') as never} size={15} color={color} /></View><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>{category.name}</Text></View>;
}

function CategoryRow({ category, onDelete, onEdit }: { category: Category; onDelete?: () => void; onEdit?: () => void }) {
  return <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest, borderRadius: 15, padding: 12 }}><View style={{ width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', backgroundColor: `${category.color ?? authColors.primary}20` }}><MaterialIcons name={(category.icon ?? 'category') as never} size={22} color={category.color ?? authColors.primary} /></View><Text selectable style={{ flex: 1, fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface }}>{category.name}</Text>{onEdit ? <Pressable accessibilityLabel={`Edit ${category.name}`} onPress={onEdit} style={smallButton}><MaterialIcons name="edit" size={19} color={authColors.primary} /></Pressable> : <MaterialIcons name="lock-outline" size={19} color={authColors.outline} />}{onDelete ? <Pressable accessibilityLabel={`Delete ${category.name}`} onPress={onDelete} style={smallButton}><MaterialIcons name="delete-outline" size={19} color={authColors.error} /></Pressable> : null}</View>;
}

const iconButton = { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const;
const smallButton = { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const;
const categoryChip = { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 13, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh } as const;
const sectionCard = { gap: 14, padding: 16, borderRadius: 16, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 4px 12px rgba(27, 27, 35, 0.06)' } as const;
const sectionTitle = { fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface } as const;
const helperText = { fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant } as const;
const fieldLabel = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface } as const;
const fieldError = { fontFamily: authFont.regular, fontSize: 12, color: authColors.error } as const;
const textInput = { minHeight: 48, borderWidth: 1, borderColor: authColors.outlineVariant, borderRadius: 12, backgroundColor: authColors.surfaceContainerLowest, paddingHorizontal: 14, fontFamily: authFont.regular, fontSize: 16, color: authColors.onSurface } as const;
const errorBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', fontFamily: authFont.regular, fontSize: 13, color: authColors.error } as const;
const primaryButton = { minHeight: 48, borderRadius: 12, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingHorizontal: 14, boxShadow: '0 4px 12px rgba(70, 72, 212, 0.20)' } as const;
const primaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary } as const;
const secondaryButton = { minHeight: 48, borderRadius: 12, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14 } as const;
const secondaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary } as const;
