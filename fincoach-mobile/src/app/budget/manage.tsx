import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BudgetProgress } from '@/components/budget/budget-progress';
import { CategoryLimitRow } from '@/components/budget/category-limit-row';
import { CategoryPicker } from '@/components/budget/category-picker';
import { MoneyField } from '@/components/budget/money-field';
import { AppText as Text } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { deleteMonthlyBudget, fetchBudgetCategories, fetchBudgetMonth, saveBudgetMonth } from '@/lib/budget';
import { formatBudgetMonth, monthKey, parseBudgetMoney, validateCategoryAllocation, validateMonthlyBudget } from '@/lib/budget-domain';
import { useAuth } from '@/lib/auth-context';
import type { BudgetMonthData, Category } from '@/lib/types';

function writeError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('Category limits cannot exceed')) return 'Category limits cannot exceed the overall monthly budget.';
  if (message.includes('Overall monthly budget cannot be lower')) return 'Reduce category limits before lowering the overall budget.';
  if (message.includes('monthly_budgets') || message.includes('schema cache')) return 'Run the Budget migration in Supabase before saving.';
  return 'Could not save the budget. Check your connection and try again.';
}

function compactMoney(value: number) {
  const rounded = Math.round(value * 100) / 100;
  return `RM ${rounded.toLocaleString('en-MY', {
    minimumFractionDigits: Number.isInteger(rounded) ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function ManageBudgetScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ categoryId?: string; month?: string }>();
  const selectedMonth = /^\d{4}-\d{2}-01$/.test(params.month ?? '') ? params.month! : monthKey();
  const suggestedCategoryId = /^\d+$/.test(params.categoryId ?? '') ? Number(params.categoryId) : null;
  const { session } = useAuth();
  const userId = session?.user.id;
  const [data, setData] = useState<BudgetMonthData | null>(null);
  const [overall, setOverall] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [editingOverall, setEditingOverall] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  useEffect(() => {
    let active = true;
    if (!userId) return;
    fetchBudgetMonth(userId, selectedMonth).then((result) => {
      if (!active) return;
      const savedCategoryIds = result.categoryLimits.map((limit) => limit.category_id);
      const canSuggestCategory = suggestedCategoryId != null
        && result.categories.some((category) => category.id === suggestedCategoryId);
      setData(result);
      setOverall(result.monthlyBudget ? String(result.monthlyBudget.limit_amount) : '');
      setSelectedIds(canSuggestCategory && !savedCategoryIds.includes(suggestedCategoryId)
        ? [...savedCategoryIds, suggestedCategoryId]
        : savedCategoryIds);
      setAmounts(Object.fromEntries(result.categoryLimits.map((limit) => [limit.category_id, String(limit.amount)])));
      setEditingOverall(!result.monthlyBudget);
      setMessage(null);
    }).catch((error) => { if (active) setMessage(writeError(error)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedMonth, suggestedCategoryId, userId]);

  useFocusEffect(useCallback(() => {
    if (!userId) return;
    let active = true;
    fetchBudgetCategories(userId)
      .then((categories) => {
        if (!active) return;
        setData((current) => current ? { ...current, categories } : current);
      })
      .catch(() => {});
    return () => { active = false; };
  }, [userId]));

  const selectedCategories = useMemo(() => {
    const categoriesById = new Map((data?.categories ?? []).map((category) => [category.id, category]));
    return selectedIds.map((id) => categoriesById.get(id)).filter((category): category is Category => Boolean(category));
  }, [data?.categories, selectedIds]);
  const addableCategories = useMemo(() => (data?.categories ?? []).filter((category) => !selectedIds.includes(category.id)), [data?.categories, selectedIds]);
  const parsedAmounts = selectedCategories.map((category) => parseBudgetMoney(amounts[category.id] ?? '') ?? 0);
  const allocatedTotal = Math.round(parsedAmounts.reduce((sum, amount) => sum + amount, 0) * 100) / 100;
  const overallAmount = parseBudgetMoney(overall) ?? 0;
  const availableAmount = Math.round((overallAmount - allocatedTotal) * 100) / 100;
  const allocationRatio = overallAmount > 0 ? allocatedTotal / overallAmount : 0;

  function addCategory(category: Category) {
    setErrors({});
    setSelectedIds((current) => current.includes(category.id) ? current : [...current, category.id]);
    setAmounts((current) => ({ ...current, [category.id]: current[category.id] ?? '' }));
    setPickerOpen(false);
  }

  function removeCategory(categoryId: number) {
    setSelectedIds((current) => current.filter((id) => id !== categoryId));
    setErrors((current) => {
      const next = { ...current };
      delete next[`category-${categoryId}`];
      return next;
    });
  }

  async function save() {
    if (!userId || !data) return;
    const nextErrors: Record<string, string> = {};
    const overallError = validateMonthlyBudget(overall, allocatedTotal);
    if (overallError) nextErrors.overall = overallError;

    selectedCategories.forEach((category) => {
      const own = parseBudgetMoney(amounts[category.id] ?? '') ?? 0;
      const error = validateCategoryAllocation(amounts[category.id] ?? '', { overallLimit: overallAmount, otherAllocated: allocatedTotal - own });
      if (error) nextErrors[`category-${category.id}`] = error;
    });

    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      if (nextErrors.overall) setEditingOverall(true);
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      await saveBudgetMonth(userId, selectedMonth, overallAmount,
        selectedCategories.map(category => ({ category_id: category.id, amount: parseBudgetMoney(amounts[category.id] ?? '')! })));
      router.back();
    } catch (error) {
      setMessage(writeError(error));
      setSaving(false);
    }
  }

  function confirmDelete() {
    if (!data?.monthlyBudget || !userId) return;
    appDialog.open('Delete monthly budget?', `This removes the overall budget and all category limits for ${formatBudgetMonth(selectedMonth)}.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => { setSaving(true); deleteMonthlyBudget(data.monthlyBudget!.id, userId).then(() => router.back()).catch((error) => { setMessage(writeError(error)); setSaving(false); }); } },
    ]);
  }

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ minHeight: insets.top + 82, paddingTop: insets.top + 8, paddingHorizontal: 20, paddingBottom: 10, alignItems: 'center', justifyContent: 'center' }}>
        <Pressable accessibilityLabel="Go back" accessibilityRole="button" hitSlop={8} onPress={() => router.back()} style={({ pressed }) => [backButton, { top: insets.top + 12, opacity: pressed ? 0.55 : 1 }]}><MaterialIcons name="arrow-back" size={27} color={authColors.primary} /></Pressable>
        <Text selectable style={{ fontFamily: authFont.bold, fontSize: 20, letterSpacing: -0.2, color: authColors.primary }}>Edit Monthly Budget</Text>
        <Text selectable style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurfaceVariant }}>{formatBudgetMonth(selectedMonth)}</Text>
      </View>

      {loading ? <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}><ActivityIndicator color={authColors.primary} /><Text>Loading…</Text></View> : (
        <>
          <ScrollView keyboardShouldPersistTaps="handled" contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: 24, gap: 18 }}>
            {message ? <Text selectable accessibilityRole="alert" style={errorBox}>{message}</Text> : null}

            <View style={limitCard}>
              <Text selectable style={labelCaps}>MONTHLY SPENDING LIMIT</Text>
              {editingOverall ? (
                <View style={{ gap: 10 }}>
                  <MoneyField label="Amount" value={overall} onChangeText={(value) => { setOverall(value); setErrors((current) => ({ ...current, overall: '' })); }} error={errors.overall} />
                  {overall ? <Pressable accessibilityRole="button" onPress={() => setEditingOverall(false)} style={({ pressed }) => ({ alignSelf: 'flex-end', minHeight: 40, justifyContent: 'center', paddingHorizontal: 10, opacity: pressed ? 0.55 : 1 })}><Text style={textAction}>Done</Text></Pressable> : null}
                </View>
              ) : (
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                  <Text selectable style={{ flex: 1, fontFamily: authFont.bold, fontSize: 32, letterSpacing: -0.5, color: authColors.onSurface, fontVariant: ['tabular-nums'] }}>{compactMoney(overallAmount)}</Text>
                  <Pressable accessibilityRole="button" onPress={() => setEditingOverall(true)} style={({ pressed }) => ({ minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 8, opacity: pressed ? 0.55 : 1 })}><MaterialIcons name="edit" size={20} color={authColors.primary} /><Text style={textAction}>Change</Text></Pressable>
                </View>
              )}
            </View>

            <View style={allocationCard}>
              <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
                <Text selectable style={{ fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface, fontVariant: ['tabular-nums'] }}>{compactMoney(allocatedTotal)} assigned</Text>
                <Text accessibilityLiveRegion="polite" selectable style={{ textAlign: 'right', fontFamily: authFont.semibold, fontSize: 15, color: availableAmount < 0 ? authColors.error : '#159B61', fontVariant: ['tabular-nums'] }}>{availableAmount < 0 ? `${compactMoney(Math.abs(availableAmount))} over limit` : `${compactMoney(availableAmount)} available`}</Text>
              </View>
              <BudgetProgress ratio={allocationRatio} color={availableAmount < 0 ? authColors.error : authColors.primary} height={8} />
            </View>

            <View style={{ gap: 5 }}>
              <Text selectable style={sectionTitle}>Set category limits</Text>
              <Text selectable style={helperText}>Choose only the categories you want to control.</Text>
            </View>

            {selectedCategories.length ? (
              <View style={categoryList}>
                {selectedCategories.map((category, index) => (
                  <CategoryLimitRow
                    key={category.id}
                    category={category}
                    error={errors[`category-${category.id}`]}
                    isLast={index === selectedCategories.length - 1}
                    onChangeText={(value) => {
                      setAmounts((current) => ({ ...current, [category.id]: value }));
                      setErrors((current) => ({ ...current, [`category-${category.id}`]: '' }));
                    }}
                    onRemove={() => removeCategory(category.id)}
                    value={amounts[category.id] ?? ''}
                  />
                ))}
              </View>
            ) : (
              <View style={[categoryList, { alignItems: 'center', gap: 7, paddingVertical: 22 }]}>
                <MaterialIcons name="category" size={27} color={authColors.outline} />
                <Text selectable style={{ textAlign: 'center', fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>No category limits selected</Text>
                <Text selectable style={[helperText, { textAlign: 'center' }]}>Your monthly spending limit still applies to every recorded expense.</Text>
              </View>
            )}

            {pickerOpen ? (
              <View style={pickerPanel}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                  <View style={{ flex: 1, gap: 2 }}><Text selectable style={{ fontFamily: authFont.bold, fontSize: 16, color: authColors.onSurface }}>Choose a category</Text><Text selectable style={helperText}>Select one to add its monthly limit.</Text></View>
                  <Pressable accessibilityLabel="Close category picker" accessibilityRole="button" hitSlop={8} onPress={() => setPickerOpen(false)} style={({ pressed }) => ({ width: 40, height: 40, alignItems: 'center', justifyContent: 'center', opacity: pressed ? 0.55 : 1 })}><MaterialIcons name="close" size={22} color={authColors.onSurfaceVariant} /></Pressable>
                </View>
                {addableCategories.length ? <CategoryPicker categories={addableCategories} selectedIds={[]} onToggle={addCategory} /> : <Text selectable style={helperText}>All available categories already have a limit.</Text>}
              </View>
            ) : null}

            <Pressable accessibilityRole="button" disabled={!addableCategories.length} onPress={() => setPickerOpen((current) => !current)} style={({ pressed }) => [outlineButton, { opacity: !addableCategories.length ? 0.45 : pressed ? 0.65 : 1 }]}><MaterialIcons name="add" size={23} color={authColors.primary} /><Text style={outlineButtonText}>{addableCategories.length ? 'Add category limit' : 'All categories added'}</Text></Pressable>

            <Pressable accessibilityRole="button" onPress={() => router.push('/budget/categories' as never)} style={({ pressed }) => [categoryLink, { opacity: pressed ? 0.6 : 1 }]}><MaterialIcons name="category" size={22} color={authColors.primary} /><Text style={textAction}>Manage expense categories</Text></Pressable>

            {data?.monthlyBudget ? <Pressable accessibilityRole="button" disabled={saving} onPress={confirmDelete} style={({ pressed }) => [deleteButton, { opacity: saving ? 0.45 : pressed ? 0.65 : 1 }]}><MaterialIcons name="delete-outline" size={20} color={authColors.error} /><Text style={{ fontFamily: authFont.semibold, color: authColors.error }}>Delete this month&apos;s budget</Text></Pressable> : null}
          </ScrollView>

          <View style={{ paddingHorizontal: 20, paddingTop: 12, paddingBottom: insets.bottom + 12, borderTopWidth: 1, borderTopColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest }}>
            <Pressable accessibilityRole="button" disabled={saving} onPress={() => void save()} style={({ pressed }) => [primaryButton, { opacity: saving ? 0.55 : pressed ? 0.82 : 1 }]}>{saving ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="save" size={21} color={authColors.onPrimary} />}<Text style={primaryButtonText}>{saving ? 'Saving…' : 'Save monthly budget'}</Text></Pressable>
          </View>
        </>
      )}
    </View>
  );
}

const backButton = { position: 'absolute', left: 20, width: 42, height: 42, alignItems: 'center', justifyContent: 'center', borderRadius: 12 } as const;
const limitCard = { gap: 8, padding: 14, borderRadius: 16, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 4px 12px rgba(27, 27, 35, 0.06)' } as const;
const allocationCard = { gap: 13, padding: 16, borderRadius: 16, backgroundColor: authColors.primaryFixed, borderWidth: 1, borderColor: authColors.primaryFixedDim } as const;
const categoryList = { paddingHorizontal: 14, borderRadius: 16, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 4px 12px rgba(27, 27, 35, 0.05)' } as const;
const pickerPanel = { gap: 14, padding: 16, borderRadius: 16, backgroundColor: authColors.surfaceContainerLow, borderWidth: 1, borderColor: authColors.outlineVariant } as const;
const sectionTitle = { fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface } as const;
const helperText = { fontFamily: authFont.regular, fontSize: 13, lineHeight: 18, color: authColors.onSurfaceVariant } as const;
const labelCaps = { fontFamily: authFont.bold, fontSize: 11, lineHeight: 15, letterSpacing: 0.6, color: authColors.onSurfaceVariant } as const;
const textAction = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary } as const;
const errorBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', fontFamily: authFont.regular, fontSize: 13, color: authColors.error } as const;
const outlineButton = { minHeight: 50, borderRadius: 14, borderWidth: 1.5, borderColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: authColors.surfaceContainerLowest } as const;
const outlineButtonText = { fontFamily: authFont.semibold, fontSize: 15, color: authColors.primary } as const;
const categoryLink = { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 } as const;
const primaryButton = { minHeight: 54, borderRadius: 14, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, boxShadow: '0 4px 12px rgba(70, 72, 212, 0.20)' } as const;
const primaryButtonText = { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onPrimary } as const;
const deleteButton = { minHeight: 46, borderRadius: 12, backgroundColor: '#FFF1F0', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 } as const;
