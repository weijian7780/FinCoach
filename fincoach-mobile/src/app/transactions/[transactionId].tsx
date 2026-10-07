import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CategoryIcon } from '@/components/categories/category-icon';
import { AppText as Text } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { formatTransactionAmount } from '@/lib/transaction-domain';
import { createReceiptSignedUrl, deleteReceiptImage, deleteTransaction, fetchTransaction } from '@/lib/transactions';
import type { TransactionWithCategory } from '@/lib/types';

export default function TransactionDetailScreen() {
  const insets = useSafeAreaInsets();
  const { transactionId = '' } = useLocalSearchParams<{ transactionId: string }>();
  const { session } = useAuth();
  const [transaction, setTransaction] = useState<TransactionWithCategory | null>(null);
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (!session?.user.id || !transactionId) return;
    fetchTransaction(transactionId, session.user.id).then(async (item) => {
      setTransaction(item);
      if (item?.receipt_image_path) setReceiptUrl(await createReceiptSignedUrl(item.receipt_image_path));
    }).catch(() => setMessage('Could not load this transaction.')).finally(() => setLoading(false));
  }, [session?.user.id, transactionId]);

  function confirmDelete() {
    if (!transaction || !session?.user.id) return;
    appDialog.open('Delete transaction?', 'This cannot be undone.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: async () => {
      try { await deleteTransaction(transaction.id, session.user.id); if (transaction.receipt_image_path) await deleteReceiptImage(transaction.receipt_image_path); router.replace('/transactions' as never); }
      catch { setMessage('Could not delete this transaction.'); }
    } }]);
  }

  return <View style={{ flex: 1, backgroundColor: authColors.surface }}><View style={[header, { paddingTop: insets.top + 8 }]}><Pressable onPress={() => router.back()} style={icon}><MaterialIcons name="arrow-back" size={27} color={authColors.onSurface} /></Pressable><Text style={title}>Transaction</Text><Pressable disabled={!transaction} onPress={() => router.push({ pathname: '/transactions/manage', params: { transactionId } } as never)} style={icon}><MaterialIcons name="edit" size={22} color={authColors.primary} /></Pressable></View>
    {loading ? <View style={center}><ActivityIndicator color={authColors.primary} /></View> : transaction ? <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 30, gap: 16 }}>
      <View style={hero}><CategoryIcon category={transaction.category} size={68} glyphSize={34} /><Text style={[amount, transaction.category.type === 'income' && { color: '#067647' }]}>{formatTransactionAmount(transaction)}</Text><Text style={source}>{transaction.source}</Text></View>
      <View style={card}><Detail label="Type" value={transaction.category.type === 'income' ? 'Income' : 'Expense'} /><Detail label="Category" value={transaction.category.name} /><Detail label="Date" value={new Date(`${transaction.transaction_date}T00:00:00`).toLocaleDateString('en-MY', { day: 'numeric', month: 'long', year: 'numeric' })} /><Detail label="Note" value={transaction.description || '—'} /><Detail label="Entry" value={transaction.receipt_image_path ? 'Scanned receipt' : 'Manual'} /></View>
      {receiptUrl ? <View style={card}><Text style={sectionTitle}>Receipt image</Text><Image source={{ uri: receiptUrl }} contentFit="contain" style={receipt} /></View> : null}
      {message ? <Text style={errorBox}>{message}</Text> : null}<Pressable onPress={confirmDelete} style={deleteButton}><MaterialIcons name="delete-outline" size={21} color={authColors.error} /><Text style={deleteText}>Delete transaction</Text></Pressable>
    </ScrollView> : <View style={center}><Text>{message ?? 'Transaction not found.'}</Text></View>}
  </View>;
}
function Detail({ label, value }: { label: string; value: string }) { return <View style={detailRow}><Text style={detailLabel}>{label}</Text><Text style={detailValue}>{value}</Text></View>; }
const header = { minHeight: 66, paddingHorizontal: 18, paddingBottom: 8, flexDirection: 'row', alignItems: 'center' } as const; const icon = { width: 42, height: 44, justifyContent: 'center' } as const; const title = { flex: 1, fontSize: 24, fontFamily: authFont.bold, color: authColors.onSurface } as const; const center = { flex: 1, alignItems: 'center', justifyContent: 'center' } as const;
const hero = { alignItems: 'center', paddingVertical: 12 } as const; const amount = { marginTop: 12, fontSize: 36, fontFamily: authFont.bold, color: authColors.onSurface } as const; const source = { marginTop: 3, fontSize: 17, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const card = { padding: 16, gap: 4, borderRadius: 18, backgroundColor: 'white', elevation: 2 } as const; const detailRow = { minHeight: 47, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 20, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant } as const; const detailLabel = { color: authColors.onSurfaceVariant, fontFamily: authFont.regular } as const; const detailValue = { flex: 1, textAlign: 'right', color: authColors.onSurface, fontFamily: authFont.semibold } as const; const sectionTitle = { fontSize: 16, fontFamily: authFont.bold, color: authColors.onSurface } as const; const receipt = { width: '100%', height: 280, borderRadius: 12, backgroundColor: authColors.surfaceContainerLow } as const;
const errorBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', color: authColors.error } as const; const deleteButton = { minHeight: 54, borderRadius: 15, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: '#FFF1F0' } as const; const deleteText = { color: authColors.error, fontFamily: authFont.semibold } as const;
