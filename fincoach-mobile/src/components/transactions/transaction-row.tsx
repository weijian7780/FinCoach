import { Pressable, View } from 'react-native';

import { CategoryIcon } from '@/components/categories/category-icon';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { formatTransactionAmount } from '@/lib/transaction-domain';
import type { TransactionWithCategory } from '@/lib/types';

export function TransactionRow({ transaction, onPress }: { transaction: TransactionWithCategory; onPress: () => void }) {
  const income = transaction.category.type === 'income';
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.row, pressed && { opacity: 0.72 }]}>
      <CategoryIcon category={transaction.category} size={44} glyphSize={21} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={styles.source}>{transaction.source}</Text>
        <Text numberOfLines={1} style={styles.meta}>{transaction.category.name}</Text>
      </View>
      <Text style={[styles.amount, income && { color: '#067647' }]}>{formatTransactionAmount(transaction)}</Text>
    </Pressable>
  );
}

const styles = {
  row: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant, paddingVertical: 11 } as const,
  source: { fontSize: 15, fontFamily: authFont.semibold, color: authColors.onSurface } as const,
  meta: { marginTop: 2, fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  amount: { fontSize: 15, fontFamily: authFont.bold, color: authColors.onSurface } as const,
};
