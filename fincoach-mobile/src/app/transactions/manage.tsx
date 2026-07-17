import { MaterialIcons } from '@expo/vector-icons';
import * as Crypto from 'expo-crypto';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { emitBudgetAlertsAfterTransactionChange } from '@/lib/alert-events';
import { useAuth } from '@/lib/auth-context';
import { parseMoney } from '@/lib/savings-domain';
import { type TransactionFormInput, type TransactionType, validateTransactionInput } from '@/lib/transaction-domain';
import { createTransaction, fetchTransaction, fetchTransactionCategories, updateTransaction } from '@/lib/transactions';
import type { Category, TransactionWithCategory } from '@/lib/types';

const today = () => new Date().toISOString().slice(0, 10);

export default function ManageTransactionScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ transactionId?: string }>();
  const transactionId = params.transactionId?.trim() || null;
  const { session } = useAuth();
  const userId = session?.user.id;
  const [categories, setCategories] = useState<Category[]>([]);
  const [type, setType] = useState<TransactionType>('expense');
  const [amount, setAmount] = useState('');
  const [source, setSource] = useState('');
  const [description, setDescription] = useState('');
  const [transactionDate, setTransactionDate] = useState(today());
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [existingTransaction, setExistingTransaction] = useState<TransactionWithCategory | null>(null);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    Promise.all([fetchTransactionCategories(userId), transactionId ? fetchTransaction(transactionId, userId) : Promise.resolve(null)])
      .then(([loadedCategories, transaction]) => {
        if (!active) return;
        setCategories(loadedCategories);
        if (transaction) {
          setExistingTransaction(transaction);
          setType(transaction.category.type);
          setAmount(String(transaction.amount));
          setSource(transaction.source);
          setDescription(transaction.description ?? '');
          setTransactionDate(transaction.transaction_date);
          setCategoryId(transaction.category_id);
        } else {
          setCategoryId(loadedCategories.find((category) => category.type === 'expense')?.id ?? null);
        }
      }).catch(() => { if (active) setMessage('Could not load the transaction form.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [transactionId, userId]);

  const visibleCategories = useMemo(() => categories.filter((category) => category.type === type), [categories, type]);
  function selectType(next: TransactionType) {
    setType(next);
    setCategoryId(categories.find((category) => category.type === next)?.id ?? null);
    setErrors({});
  }

  async function syncBudgetAlerts(previous: TransactionWithCategory | null, current: TransactionWithCategory) {
    try {
      await emitBudgetAlertsAfterTransactionChange(userId!, previous, current);
      router.replace('/transactions' as never);
    } catch {
      Alert.alert(
        'Transaction saved',
        'The transaction is safe, but its budget alert could not synchronize. Retry the alert sync now?',
        [
          { text: 'Continue', onPress: () => router.replace('/transactions' as never) },
          { text: 'Retry sync', onPress: () => void syncBudgetAlerts(previous, current) },
        ],
      );
    }
  }

  async function save() {
    if (!userId) return;
    const input: TransactionFormInput = { type, amount, source, description, transactionDate, categoryId };
    const nextErrors = validateTransactionInput(input, categories, today());
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    const value = parseMoney(amount);
    if (value == null || categoryId == null) return;
    setSaving(true); setMessage(null);
    const payload = { category_id: categoryId, amount: value, transaction_date: transactionDate, description: description.trim() || null, source: source.trim(), receipt_image_path: null };
    try {
      const saved = transactionId
        ? await updateTransaction(transactionId, userId, payload)
        : await createTransaction(userId, { id: Crypto.randomUUID(), ...payload });
      await syncBudgetAlerts(existingTransaction, saved);
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : '';
      setMessage(detail.includes('transactions') ? 'Run the transaction migration in Supabase first.' : 'Could not save this transaction.');
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={[header, { paddingTop: insets.top + 8 }]}><Pressable onPress={() => router.back()} style={back}><MaterialIcons name="arrow-back" size={27} color={authColors.onSurface} /></Pressable><Text style={title}>{transactionId ? 'Edit Transaction' : 'Add Transaction'}</Text></View>
      <View style={tabs}><Pressable onPress={() => {}} style={activeTab}><Text style={activeTabText}>Manual</Text></Pressable><Pressable onPress={() => router.replace('/transactions/scan' as never)} style={tab}><Text style={tabText}>Scan Receipt</Text></Pressable></View>
      {loading ? <View style={center}><ActivityIndicator color={authColors.primary} /></View> : <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 30, gap: 18 }}>
        <View style={segmented}><TypeButton active={type === 'expense'} label="Expense" onPress={() => selectType('expense')} /><TypeButton active={type === 'income'} label="Income" onPress={() => selectType('income')} /></View>
        <View style={amountCard}><Text style={fieldLabel}>Amount</Text><View style={{ flexDirection: 'row', alignItems: 'baseline' }}><Text style={rm}>RM</Text><TextInput autoFocus keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={authColors.outline} value={amount} onChangeText={(value) => { setAmount(value.replace(/[^0-9.]/g, '')); setErrors((old) => ({ ...old, amount: '' })); }} style={amountInput} /></View>{errors.amount ? <Text style={errorText}>{errors.amount}</Text> : null}</View>
        <View style={{ gap: 8 }}><Text style={label}>Category</Text><View style={categoryGrid}>{visibleCategories.map((category) => <Pressable key={category.id} onPress={() => { setCategoryId(category.id); setErrors((old) => ({ ...old, categoryId: '' })); }} style={[categoryButton, categoryId === category.id && selectedCategory]}><MaterialIcons name={(category.icon ?? 'category') as never} size={20} color={category.color ?? authColors.primary} /><Text numberOfLines={1} style={[categoryText, categoryId === category.id && { color: authColors.primary }]}>{category.name}</Text></Pressable>)}</View>{errors.categoryId ? <Text style={errorText}>{errors.categoryId}</Text> : null}</View>
        <Field label={type === 'expense' ? 'Merchant' : 'Income source'} value={source} placeholder={type === 'expense' ? 'e.g. Campus Cafeteria' : 'e.g. Part-time salary'} error={errors.source} onChange={(value) => { setSource(value); setErrors((old) => ({ ...old, source: '' })); }} />
        <Field label="Date" value={transactionDate} placeholder="YYYY-MM-DD" error={errors.transactionDate} onChange={(value) => { setTransactionDate(value); setErrors((old) => ({ ...old, transactionDate: '' })); }} />
        <Field label="Note (optional)" value={description} placeholder="Add a description…" error={errors.description} onChange={(value) => { setDescription(value); setErrors((old) => ({ ...old, description: '' })); }} />
        {message ? <Text style={messageBox}>{message}</Text> : null}
        <Pressable disabled={saving} onPress={() => void save()} style={[saveButton, saving && { opacity: 0.65 }]}>{saving ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="check" size={22} color={authColors.onPrimary} />}<Text style={saveText}>{saving ? 'Saving…' : transactionId ? 'Save changes' : 'Add transaction'}</Text></Pressable>
      </ScrollView>}
    </KeyboardAvoidingView>
  );
}

function TypeButton({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) { return <Pressable onPress={onPress} style={[typeButton, active && activeTypeButton]}><Text style={[typeText, active && activeTypeText]}>{label}</Text></Pressable>; }
function Field({ label: fieldName, value, placeholder, error, onChange }: { label: string; value: string; placeholder: string; error?: string; onChange: (value: string) => void }) { return <View style={{ gap: 7 }}><Text style={label}>{fieldName}</Text><TextInput value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={authColors.outline} style={[input, error ? { borderColor: authColors.error } : null]} />{error ? <Text style={errorText}>{error}</Text> : null}</View>; }

const header = { minHeight: 66, paddingHorizontal: 18, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 8 } as const;
const back = { width: 40, height: 44, justifyContent: 'center' } as const;
const title = { fontSize: 24, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const tabs = { height: 48, paddingHorizontal: 20, flexDirection: 'row', gap: 24, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant } as const;
const tab = { justifyContent: 'center' } as const; const activeTab = { justifyContent: 'center', borderBottomWidth: 2, borderBottomColor: authColors.primary } as const;
const tabText = { fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const; const activeTabText = { fontFamily: authFont.semibold, color: authColors.primary } as const;
const center = { flex: 1, alignItems: 'center', justifyContent: 'center' } as const;
const segmented = { padding: 4, flexDirection: 'row', borderRadius: 14, backgroundColor: authColors.surfaceContainer } as const;
const typeButton = { flex: 1, paddingVertical: 11, borderRadius: 11, alignItems: 'center' } as const; const activeTypeButton = { backgroundColor: authColors.surfaceContainerLowest, elevation: 2 } as const;
const typeText = { fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const; const activeTypeText = { color: authColors.primary } as const;
const amountCard = { padding: 18, borderRadius: 20, backgroundColor: authColors.surfaceContainerLowest, elevation: 3 } as const;
const fieldLabel = { fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const; const rm = { fontSize: 24, fontFamily: authFont.bold, color: authColors.primary } as const;
const amountInput = { flex: 1, fontSize: 36, textAlign: 'right', fontFamily: authFont.bold, color: authColors.onSurface, paddingVertical: 0 } as const;
const label = { marginLeft: 2, fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const categoryGrid = { flexDirection: 'row', flexWrap: 'wrap', gap: 8 } as const;
const categoryButton = { width: '48%', minHeight: 46, paddingHorizontal: 10, flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 13, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest } as const;
const selectedCategory = { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed } as const; const categoryText = { flex: 1, fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const input = { minHeight: 56, paddingHorizontal: 16, borderRadius: 15, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest, fontSize: 15, fontFamily: authFont.regular, color: authColors.onSurface } as const;
const errorText = { fontSize: 12, fontFamily: authFont.regular, color: authColors.error } as const; const messageBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', color: authColors.error } as const;
const saveButton = { minHeight: 56, borderRadius: 16, flexDirection: 'row', gap: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary, elevation: 4 } as const;
const saveText = { fontSize: 16, fontFamily: authFont.semibold, color: authColors.onPrimary } as const;
