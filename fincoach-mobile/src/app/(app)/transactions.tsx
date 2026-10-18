import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TransactionRow } from '@/components/transactions/transaction-row';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { filterTransactions, groupTransactionsByDate } from '@/lib/transaction-domain';
import { fetchTransactions } from '@/lib/transactions';
import type { TransactionWithCategory } from '@/lib/types';

export default function TransactionsScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [transactions, setTransactions] = useState<TransactionWithCategory[]>([]);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    try { setError(null); setTransactions(await fetchTransactions(userId)); }
    catch { setError('Could not load transactions. Check the migration and connection.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [userId]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const categories = useMemo(() => Array.from(new Map(transactions.map((item) => [item.category.id, item.category])).values()), [transactions]);
  const groups = groupTransactionsByDate(filterTransactions(transactions, categoryId));

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 10, backgroundColor: authColors.surface }}>
        <View style={header}>
          <Text style={title}>Transactions</Text>
          <Pressable accessibilityLabel="Add transaction" onPress={() => router.push('/transactions/manage' as never)} style={addButton}><MaterialIcons name="add" size={27} color={authColors.onPrimary} /></Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={chips}>
          <FilterChip active={categoryId == null} label="All" onPress={() => setCategoryId(null)} />
          {categories.map((category) => <FilterChip key={category.id} active={category.id === categoryId} label={category.name} onPress={() => setCategoryId(category.id)} />)}
        </ScrollView>
      </View>
      {loading ? <View style={center}><ActivityIndicator color={authColors.primary} /></View> : (
        <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} />} contentContainerStyle={{ paddingHorizontal: 18, paddingBottom: 30 }}>
          {error ? <Text style={errorBox}>{error}</Text> : null}
          {groups.map((group) => <View key={group.date} style={{ marginTop: 17 }}>
            <Text style={dateLabel}>{formatDate(group.date)}</Text>
            <View style={card}>{group.items.map((transaction) => <TransactionRow key={transaction.id} transaction={transaction} onPress={() => router.push({ pathname: '/transactions/[transactionId]', params: { transactionId: transaction.id } } as never)} />)}</View>
          </View>)}
          {!error && groups.length === 0 ? <View style={empty}><MaterialIcons name="receipt-long" size={42} color={authColors.outline} /><Text style={emptyTitle}>No transactions yet</Text><Text style={emptyText}>Add one manually or scan a receipt.</Text><Pressable onPress={() => router.push('/transactions/manage' as never)} style={emptyButton}><Text style={emptyButtonText}>Add transaction</Text></Pressable></View> : null}
        </ScrollView>
      )}
    </View>
  );
}

function FilterChip({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) {
  return <Pressable onPress={onPress} style={[chip, active && activeChip]}><Text style={[chipText, active && activeChipText]}>{label}</Text></Pressable>;
}

function formatDate(value: string) {
  const today = new Date().toISOString().slice(0, 10);
  if (value === today) return 'TODAY';
  return new Date(`${value}T00:00:00`).toLocaleDateString('en-MY', { day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase();
}

const header = { minHeight: 58, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const;
const title = { fontSize: 28, fontFamily: authFont.bold, color: authColors.onSurface, letterSpacing: -0.4 } as const;
const addButton = { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary, elevation: 4 } as const;
const chips = { paddingHorizontal: 18, paddingVertical: 10, gap: 8 } as const;
const chip = { height: 36, paddingHorizontal: 15, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const;
const activeChip = { backgroundColor: authColors.primaryFixed, borderColor: authColors.primaryFixed } as const;
const chipText = { fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const activeChipText = { color: authColors.primary } as const;
const center = { flex: 1, alignItems: 'center', justifyContent: 'center' } as const;
const card = { paddingHorizontal: 15, borderRadius: 18, backgroundColor: authColors.surfaceContainerLowest, elevation: 2, overflow: 'hidden' } as const;
const dateLabel = { marginLeft: 3, marginBottom: 6, fontSize: 11, letterSpacing: 0.7, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const empty = { alignItems: 'center', paddingTop: 90, gap: 8 } as const;
const emptyTitle = { marginTop: 8, fontSize: 19, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const emptyText = { fontSize: 14, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const;
const emptyButton = { marginTop: 10, backgroundColor: authColors.primary, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 14 } as const;
const emptyButtonText = { color: authColors.onPrimary, fontFamily: authFont.semibold } as const;
const errorBox = { marginTop: 18, padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', color: authColors.error } as const;
