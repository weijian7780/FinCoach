import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BudgetProgress } from '@/components/budget/budget-progress';
import { MonthSelector } from '@/components/budget/month-selector';
import { StatusBadge } from '@/components/budget/status-badge';
import { CategoryIcon } from '@/components/categories/category-icon';
import { NotificationBell } from '@/components/notifications/notification-bell';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { fetchBudgetMonth } from '@/lib/budget';
import { formatBudgetMoney, getBudgetLeftColor, getLimitMetrics, getLimitStatus, getUnbudgetedCategorySpending, monthKey, shiftMonth } from '@/lib/budget-domain';
import { useAuth } from '@/lib/auth-context';
import { fetchTransactions } from '@/lib/transactions';
import type { BudgetMonthData, Category, TransactionWithCategory } from '@/lib/types';

const prototypeCard = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderRadius: 16,
  padding: 16,
  gap: 12,
  boxShadow: '0 4px 12px rgba(27, 27, 35, 0.06)',
} as const;

function errorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('monthly_budgets') || message.includes('schema cache')) return 'Budget database setup is not installed yet. Run the Budget migration in Supabase, then retry.';
  return 'Could not load this budget month. Check your connection and try again.';
}

function CategoryBudgetCard({ category, limitAmount, usedAmount }: { category: Category; limitAmount: number; usedAmount: number }) {
  const metrics = getLimitMetrics(usedAmount, limitAmount);
  const status = getLimitStatus(usedAmount, limitAmount);
  const categoryColor = category.color ?? authColors.primary;
  const leftColor = getBudgetLeftColor(usedAmount, limitAmount);
  return (
    <View style={prototypeCard}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <CategoryIcon category={category} size={40} glyphSize={21} tintColor={categoryColor} />
        <View style={{ flex: 1, gap: 3 }}><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 16, color: authColors.onSurface }}>{category.name}</Text>{status.tone !== 'success' ? <StatusBadge status={status} /> : null}</View>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>{formatBudgetMoney(metrics.usedAmount)} <Text style={{ fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>/ {formatBudgetMoney(metrics.limitAmount)}</Text></Text><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 13, color: leftColor.text, fontVariant: ['tabular-nums'] }}>{metrics.percentage}% used</Text></View>
      <BudgetProgress ratio={metrics.ratio} color={leftColor.bar} height={7} />
    </View>
  );
}

function UnbudgetedCategoryCard({
  category,
  onSetLimit,
  usedAmount,
}: {
  category: Category;
  onSetLimit: () => void;
  usedAmount: number;
}) {
  const categoryColor = category.color ?? authColors.primary;

  return (
    <View style={unbudgetedCard}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <CategoryIcon category={category} size={40} glyphSize={21} tintColor={categoryColor} />
        <View style={{ flex: 1, gap: 3 }}>
          <Text selectable style={{ fontFamily: authFont.semibold, fontSize: 16, color: authColors.onSurface }}>{category.name}</Text>
          <Text selectable style={{ fontFamily: authFont.regular, fontSize: 13, color: authColors.onSurfaceVariant, fontVariant: ['tabular-nums'] }}>{formatBudgetMoney(usedAmount)} spent this month</Text>
        </View>
        <View style={noLimitBadge}><Text selectable style={noLimitBadgeText}>No limit set</Text></View>
      </View>
      <Text selectable style={{ fontFamily: authFont.regular, fontSize: 13, lineHeight: 18, color: authColors.onSurfaceVariant }}>This category has recorded spending. Add a monthly limit to track it separately.</Text>
      <Pressable
        accessibilityLabel={`Set a monthly limit for ${category.name}`}
        accessibilityRole="button"
        onPress={onSetLimit}
        style={({ pressed }) => [suggestionButton, { opacity: pressed ? 0.65 : 1 }]}
      >
        <MaterialIcons name="add" size={20} color={authColors.primary} />
        <Text numberOfLines={1} style={suggestionButtonText}>Set {category.name} limit</Text>
      </Pressable>
    </View>
  );
}

export default function BudgetScreen() {
  const insets = useSafeAreaInsets();
  const { profile, session } = useAuth();
  const userId = session?.user.id;
  const [month, setMonth] = useState(() => monthKey());
  const [data, setData] = useState<BudgetMonthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<TransactionWithCategory[]>([]);

  const load = useCallback(async (refresh = false) => {
    if (!userId) return;
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try { const [budget, loadedTransactions] = await Promise.all([fetchBudgetMonth(userId, month), fetchTransactions(userId)]); setData(budget); setTransactions(loadedTransactions); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setLoading(false); setRefreshing(false); }
  }, [month, userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const parent = data?.monthlyBudget ?? null;
  const monthPrefix = month.slice(0, 7);
  const expenses = transactions.filter((item) => item.category.type === 'expense' && item.transaction_date.startsWith(monthPrefix));
  const spentByCategory = new Map<number, number>();
  expenses.forEach((item) => spentByCategory.set(item.category_id, (spentByCategory.get(item.category_id) ?? 0) + item.amount));
  const overall = getLimitMetrics(expenses.reduce((sum, item) => sum + item.amount, 0), parent?.limit_amount ?? 0);
  const categoriesById = new Map((data?.categories ?? []).map((category) => [category.id, category]));
  const unbudgetedCategories = getUnbudgetedCategorySpending(
    spentByCategory,
    (data?.categoryLimits ?? []).map((limit) => limit.category_id),
  ).flatMap((spending) => {
    const category = categoriesById.get(spending.categoryId);
    return category ? [{ category, usedAmount: spending.amount }] : [];
  });

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 8, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Pressable accessibilityLabel="Open profile" accessibilityRole="button" onPress={() => router.push('/profile')}>
          <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
            {profile?.avatar_url ? <Image source={{ uri: profile.avatar_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" /> : <MaterialIcons name="person" size={20} color={authColors.primary} />}
          </View>
        </Pressable>
        <Text style={{ fontFamily: authFont.bold, fontSize: 18, color: authColors.primary }}>FinCoach</Text>
        <NotificationBell />
      </View>
      <ScrollView contentInsetAdjustmentBehavior="automatic" refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={authColors.primary} />} contentContainerStyle={{ paddingTop: 8, paddingHorizontal: 20, paddingBottom: insets.bottom + 96, gap: 18 }}>
        <Text selectable style={{ fontFamily: authFont.bold, fontSize: 26, letterSpacing: -0.3, color: authColors.onSurface }}>Monthly Budget</Text>
        <MonthSelector month={month} onPrevious={() => setMonth((value) => shiftMonth(value, -1))} onNext={() => setMonth((value) => shiftMonth(value, 1))} />
        {loading ? (
          <View style={[prototypeCard, { alignItems: 'center', paddingVertical: 36 }]}><ActivityIndicator color={authColors.primary} /><Text style={{ color: authColors.onSurfaceVariant }}>Loading budget…</Text></View>
        ) : error ? (
          <View style={[prototypeCard, { alignItems: 'center', paddingVertical: 24 }]}><MaterialIcons name="cloud-off" size={30} color={authColors.error} /><Text selectable accessibilityRole="alert" style={{ textAlign: 'center', fontFamily: authFont.regular, color: authColors.error }}>{error}</Text><Pressable onPress={() => void load()} style={secondaryButton}><Text style={secondaryButtonText}>Retry</Text></Pressable></View>
        ) : !parent ? (
          <View style={[prototypeCard, { alignItems: 'center', paddingVertical: 28 }]}><View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center' }}><MaterialIcons name="account-balance-wallet" size={25} color={authColors.primary} /></View><Text selectable style={{ fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface }}>No budget for this month</Text><Text selectable style={{ textAlign: 'center', fontFamily: authFont.regular, fontSize: 14, lineHeight: 20, color: authColors.onSurfaceVariant }}>Set your monthly amount and optional category limits.</Text><Pressable onPress={() => router.push({ pathname: '/budget/manage', params: { month } } as never)} style={primaryButton}><Text style={primaryButtonText}>Set up budget</Text></Pressable></View>
        ) : (
          <>
            <View style={prototypeCard}>
              <Text selectable style={labelCaps}>TOTAL MONTHLY BUDGET</Text>
              <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}><Text selectable style={{ flexShrink: 1, fontFamily: authFont.bold, fontSize: 25, letterSpacing: -0.2, color: authColors.onSurface, fontVariant: ['tabular-nums'] }}>{formatBudgetMoney(overall.usedAmount)} <Text style={{ fontFamily: authFont.regular, fontSize: 14, color: authColors.onSurfaceVariant }}>/ {formatBudgetMoney(overall.limitAmount)}</Text></Text><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 12, color: authColors.onSurfaceVariant }}>{overall.percentage}% Used</Text></View>
              <BudgetProgress ratio={overall.ratio} height={8} />
              <Text selectable style={{ textAlign: 'right', fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant }}>{formatBudgetMoney(overall.remainingAmount)} remaining</Text>
              <View style={{ height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.45 }} />
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><MaterialIcons name="info-outline" size={16} color={authColors.onSurfaceVariant} /><Text selectable style={{ flex: 1, fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant }}>{expenses.length} expense{expenses.length === 1 ? '' : 's'} included for this month.</Text></View>
            </View>
            <Text selectable style={{ fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface }}>Category Breakdown</Text>
            {data?.categoryLimits.map((limit) => { const category = categoriesById.get(limit.category_id); return category ? <CategoryBudgetCard key={limit.id} category={category} limitAmount={limit.amount} usedAmount={spentByCategory.get(limit.category_id) ?? 0} /> : null; })}
            {unbudgetedCategories.map(({ category, usedAmount }) => (
              <UnbudgetedCategoryCard
                key={category.id}
                category={category}
                onSetLimit={() => router.push({ pathname: '/budget/manage', params: { categoryId: String(category.id), month } } as never)}
                usedAmount={usedAmount}
              />
            ))}
            {!data?.categoryLimits.length && !unbudgetedCategories.length ? <View style={prototypeCard}><Text selectable style={{ textAlign: 'center', fontFamily: authFont.regular, fontSize: 14, color: authColors.onSurfaceVariant }}>No category limits or recorded category spending yet.</Text></View> : null}
            <Pressable onPress={() => router.push({ pathname: '/budget/manage', params: { month } } as never)} style={primaryButton}><MaterialIcons name="edit" size={19} color={authColors.onPrimary} /><Text style={primaryButtonText}>Edit monthly budget</Text></Pressable>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const labelCaps = { fontFamily: authFont.bold, fontSize: 10, lineHeight: 14, letterSpacing: 0.65, color: authColors.onSurfaceVariant } as const;
const unbudgetedCard = { ...prototypeCard, borderWidth: 1, borderColor: '#E4B765' } as const;
const noLimitBadge = { minHeight: 28, justifyContent: 'center', paddingHorizontal: 9, borderRadius: 999, backgroundColor: '#FFF1D6' } as const;
const noLimitBadgeText = { fontFamily: authFont.semibold, fontSize: 11, color: '#8A5200' } as const;
const suggestionButton = { minHeight: 44, paddingHorizontal: 14, borderRadius: 12, borderWidth: 1.5, borderColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: authColors.surfaceContainerLowest } as const;
const suggestionButtonText = { flexShrink: 1, fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary } as const;
const primaryButton = { minHeight: 48, paddingHorizontal: 18, borderRadius: 12, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 } as const;
const primaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary } as const;
const secondaryButton = { minHeight: 42, paddingHorizontal: 18, borderRadius: 12, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center' } as const;
const secondaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary } as const;
