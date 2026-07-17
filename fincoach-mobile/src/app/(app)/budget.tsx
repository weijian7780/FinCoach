import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BudgetProgress } from '@/components/budget/budget-progress';
import { MonthSelector } from '@/components/budget/month-selector';
import { StatusBadge } from '@/components/budget/status-badge';
import { NotificationBell } from '@/components/notifications/notification-bell';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { fetchBudgetMonth } from '@/lib/budget';
import { formatBudgetMoney, getLimitMetrics, getLimitStatus, monthKey, shiftMonth } from '@/lib/budget-domain';
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
  const color = status.tone === 'danger' ? authColors.error : status.tone === 'warning' ? '#B26A00' : categoryColor;
  return (
    <View style={prototypeCard}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: `${categoryColor}1F` }}><MaterialIcons name={(category.icon ?? 'category') as never} size={21} color={categoryColor} /></View>
        <View style={{ flex: 1, gap: 3 }}><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 16, color: authColors.onSurface }}>{category.name}</Text>{status.tone !== 'success' ? <StatusBadge status={status} /> : null}</View>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 14, color: authColors.onSurface }}>{formatBudgetMoney(metrics.usedAmount)} <Text style={{ fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>/ {formatBudgetMoney(metrics.limitAmount)}</Text></Text><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 13, color, fontVariant: ['tabular-nums'] }}>{metrics.percentage}%</Text></View>
      <BudgetProgress ratio={metrics.ratio} color={color} height={7} />
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
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text selectable style={{ fontFamily: authFont.bold, fontSize: 26, letterSpacing: -0.3, color: authColors.onSurface }}>My Budgets</Text>
          <Pressable accessibilityLabel="Manage categories" accessibilityRole="button" onPress={() => router.push('/budget/categories' as never)} style={compactIconButton}><MaterialIcons name="category" size={20} color={authColors.primary} /></Pressable>
        </View>
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
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text selectable style={{ fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface }}>Category Breakdown</Text><Pressable onPress={() => router.push('/budget/categories' as never)}><Text style={{ fontFamily: authFont.semibold, fontSize: 13, color: authColors.primary }}>Manage</Text></Pressable></View>
            {data?.categoryLimits.length ? data.categoryLimits.map((limit) => { const category = categoriesById.get(limit.category_id); return category ? <CategoryBudgetCard key={limit.id} category={category} limitAmount={limit.amount} usedAmount={spentByCategory.get(limit.category_id) ?? 0} /> : null; }) : <View style={prototypeCard}><Text selectable style={{ textAlign: 'center', fontFamily: authFont.regular, fontSize: 14, color: authColors.onSurfaceVariant }}>No category limits yet.</Text></View>}
            <Pressable onPress={() => router.push({ pathname: '/budget/manage', params: { month } } as never)} style={primaryButton}><MaterialIcons name="edit" size={19} color={authColors.onPrimary} /><Text style={primaryButtonText}>Edit Budgets</Text></Pressable>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const labelCaps = { fontFamily: authFont.bold, fontSize: 10, lineHeight: 14, letterSpacing: 0.65, color: authColors.onSurfaceVariant } as const;
const compactIconButton = { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed } as const;
const primaryButton = { minHeight: 48, paddingHorizontal: 18, borderRadius: 12, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 } as const;
const primaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.onPrimary } as const;
const secondaryButton = { minHeight: 42, paddingHorizontal: 18, borderRadius: 12, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center' } as const;
const secondaryButtonText = { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary } as const;
