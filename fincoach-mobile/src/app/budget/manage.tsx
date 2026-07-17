import { MaterialIcons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CategoryPicker } from '@/components/budget/category-picker';
import { MoneyField } from '@/components/budget/money-field';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { deleteCategoryLimit, deleteMonthlyBudget, fetchBudgetMonth, upsertCategoryLimit, upsertMonthlyBudget } from '@/lib/budget';
import { formatBudgetMoney, formatBudgetMonth, monthKey, parseBudgetMoney, validateCategoryAllocation, validateMonthlyBudget } from '@/lib/budget-domain';
import { useAuth } from '@/lib/auth-context';
import type { BudgetMonthData, Category } from '@/lib/types';

function writeError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('Category limits cannot exceed')) return 'Category limits cannot exceed the overall monthly budget.';
  if (message.includes('Overall monthly budget cannot be lower')) return 'Reduce category limits before lowering the overall budget.';
  if (message.includes('monthly_budgets') || message.includes('schema cache')) return 'Run the Budget migration in Supabase before saving.';
  return 'Could not save the budget. Check your connection and try again.';
}

export default function ManageBudgetScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ month?: string }>();
  const selectedMonth = /^\d{4}-\d{2}-01$/.test(params.month ?? '') ? params.month! : monthKey();
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

  useEffect(() => {
    let active = true;
    if (!userId) return;
    fetchBudgetMonth(userId, selectedMonth).then((result) => {
      if (!active) return;
      setData(result);
      setOverall(result.monthlyBudget ? String(result.monthlyBudget.limit_amount) : '');
      setSelectedIds(result.categoryLimits.map((limit) => limit.category_id));
      setAmounts(Object.fromEntries(result.categoryLimits.map((limit) => [limit.category_id, String(limit.amount)])));
      setMessage(null);
    }).catch((error) => { if (active) setMessage(writeError(error)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedMonth, userId]);

  const selectedCategories = useMemo(() => (data?.categories ?? []).filter((category) => selectedIds.includes(category.id)), [data?.categories, selectedIds]);
  const parsedAmounts = selectedCategories.map((category) => parseBudgetMoney(amounts[category.id] ?? '') ?? 0);
  const allocatedTotal = Math.round(parsedAmounts.reduce((sum, amount) => sum + amount, 0) * 100) / 100;

  function toggleCategory(category: Category) {
    setErrors({});
    setSelectedIds((current) => current.includes(category.id) ? current.filter((id) => id !== category.id) : [...current, category.id]);
    setAmounts((current) => ({ ...current, [category.id]: current[category.id] ?? '' }));
  }

  async function save() {
    if (!userId || !data) return;
    const nextErrors: Record<string, string> = {};
    const overallError = validateMonthlyBudget(overall, allocatedTotal);
    if (overallError) nextErrors.overall = overallError;
    const overallAmount = parseBudgetMoney(overall) ?? 0;

    selectedCategories.forEach((category) => {
      const own = parseBudgetMoney(amounts[category.id] ?? '') ?? 0;
      const error = validateCategoryAllocation(amounts[category.id] ?? '', { overallLimit: overallAmount, otherAllocated: allocatedTotal - own });
      if (error) nextErrors[`category-${category.id}`] = error;
    });

    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }

    setSaving(true);
    setMessage(null);
    try {
      const oldOverall = data.monthlyBudget?.limit_amount ?? 0;
      if (!data.monthlyBudget || overallAmount >= oldOverall) await upsertMonthlyBudget(userId, selectedMonth, overallAmount);

      const removed = data.categoryLimits.filter((limit) => !selectedIds.includes(limit.category_id));
      for (const limit of removed) await deleteCategoryLimit(limit.id, userId);
      for (const category of selectedCategories) await upsertCategoryLimit(userId, selectedMonth, category.id, parseBudgetMoney(amounts[category.id] ?? '')!);

      if (data.monthlyBudget && overallAmount < oldOverall) await upsertMonthlyBudget(userId, selectedMonth, overallAmount);
      router.back();
    } catch (error) {
      setMessage(writeError(error));
      setSaving(false);
    }
  }

  function confirmDelete() {
    if (!data?.monthlyBudget || !userId) return;
    Alert.alert('Delete monthly budget?', `This removes the overall budget and all category limits for ${formatBudgetMonth(selectedMonth)}.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => { setSaving(true); deleteMonthlyBudget(data.monthlyBudget!.id, userId).then(() => router.back()).catch((error) => { setMessage(writeError(error)); setSaving(false); }); } },
    ]);
  }

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 10, paddingHorizontal: 20, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable accessibilityLabel="Go back" accessibilityRole="button" onPress={() => router.back()} style={iconButton}><MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} /></Pressable>
        <View style={{ flex: 1 }}><Text selectable style={{ fontFamily: authFont.bold, fontSize: 22, color: authColors.onSurface }}>Manage Budget</Text><Text selectable style={{ fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant }}>{formatBudgetMonth(selectedMonth)}</Text></View>
        <Pressable accessibilityLabel="Manage category settings" accessibilityRole="button" onPress={() => router.push('/budget/categories' as never)} style={iconButton}><MaterialIcons name="category" size={21} color={authColors.primary} /></Pressable>
      </View>

      {loading ? <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}><ActivityIndicator color={authColors.primary} /><Text>Loading…</Text></View> : (
        <ScrollView keyboardShouldPersistTaps="handled" contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: insets.bottom + 36, gap: 20 }}>
          {message ? <Text selectable accessibilityRole="alert" style={errorBox}>{message}</Text> : null}

          <View style={sectionCard}>
            <Text style={sectionTitle}>Overall monthly budget</Text>
            <Text style={helperText}>Set the maximum amount you plan to spend this month.</Text>
            <MoneyField label="Amount" value={overall} onChangeText={(value) => { setOverall(value); setErrors((current) => ({ ...current, overall: '' })); }} error={errors.overall} />
            <View style={allocationPill}><Text selectable style={allocationText}>Allocated: {formatBudgetMoney(allocatedTotal)}</Text></View>
          </View>

          <View style={{ gap: 10 }}>
            <Text style={sectionTitle}>Category limits</Text>
            <Text style={helperText}>Select categories to limit. Their total cannot exceed your overall budget.</Text>
            <CategoryPicker categories={data?.categories ?? []} selectedIds={selectedIds} onToggle={toggleCategory} />
          </View>

          {selectedCategories.length ? <View style={sectionCard}>
            <Text style={sectionTitle}>Category limits</Text>
            {selectedCategories.map((category) => <View key={category.id} style={{ gap: 8, paddingBottom: 8 }}><View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><MaterialIcons name={(category.icon ?? 'category') as never} size={20} color={category.color ?? authColors.primary} /><Text style={{ fontFamily: authFont.semibold, color: authColors.onSurface }}>{category.name}</Text></View><MoneyField label={`${category.name} limit`} value={amounts[category.id] ?? ''} onChangeText={(value) => { setAmounts((current) => ({ ...current, [category.id]: value })); setErrors((current) => ({ ...current, [`category-${category.id}`]: '' })); }} error={errors[`category-${category.id}`]} /></View>)}
          </View> : null}

          <Pressable accessibilityRole="button" disabled={saving} onPress={() => void save()} style={[primaryButton, saving && { opacity: 0.55 }]}>{saving ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="save" size={20} color={authColors.onPrimary} />}<Text style={primaryButtonText}>{saving ? 'Saving…' : 'Save budget'}</Text></Pressable>
          {data?.monthlyBudget ? <Pressable accessibilityRole="button" disabled={saving} onPress={confirmDelete} style={deleteButton}><MaterialIcons name="delete-outline" size={20} color={authColors.error} /><Text style={{ fontFamily: authFont.semibold, color: authColors.error }}>Delete this month&apos;s budget</Text></Pressable> : null}
        </ScrollView>
      )}
    </View>
  );
}

const iconButton = { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const;
const sectionCard = { gap: 14, padding: 16, borderRadius: 16, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 4px 12px rgba(27, 27, 35, 0.06)' } as const;
const sectionTitle = { fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface } as const;
const helperText = { fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant } as const;
const allocationPill = { alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, backgroundColor: authColors.primaryFixed } as const;
const allocationText = { fontFamily: authFont.semibold, fontSize: 12, color: authColors.primary } as const;
const errorBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', fontFamily: authFont.regular, fontSize: 13, color: authColors.error } as const;
const primaryButton = { minHeight: 50, borderRadius: 12, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, boxShadow: '0 4px 12px rgba(70, 72, 212, 0.20)' } as const;
const primaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary } as const;
const deleteButton = { minHeight: 48, borderRadius: 12, backgroundColor: '#FFF1F0', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 } as const;
