import { MaterialIcons } from '@expo/vector-icons';
import * as Crypto from 'expo-crypto';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CategoryIcon } from '@/components/categories/category-icon';
import { TransactionDateField } from '@/components/transactions/transaction-date-field';
import { malaysiaToday } from '@/lib/transaction-date';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { emitBudgetAlertsAfterTransactionChange } from '@/lib/alert-events';
import { summarizeBudgetAlerts } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import { parseMoney } from '@/lib/savings-domain';
import { fetchProfile } from '@/lib/profile';
import { buildProfileIncomeDraft, findSimilarIncomeEntries, transactionMatchesInput, type TransactionFormInput, type TransactionType, validateTransactionInput } from '@/lib/transaction-domain';
import { createTransactionWithRecovery, fetchIncomeCandidates, fetchTransaction, fetchTransactionCategories, TransactionDraftConflictError, updateTransaction } from '@/lib/transactions';
import type { Category, TransactionWithCategory, TransactionWriteInput } from '@/lib/types';

const today = malaysiaToday;

export default function ManageTransactionScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ transactionId?: string; prefill?: string }>();
  const transactionId = params.transactionId?.trim() || null;
  const profileIncome = params.prefill === 'profile_income' && !transactionId;
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
  const draftId = useRef<string | null>(null);
  const attemptedPayload = useRef<TransactionWriteInput | null>(null);
  const submitting = useRef(false);
  const draftRevision = useRef(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    draftId.current = Crypto.randomUUID();
    attemptedPayload.current = null;
    Promise.all([fetchTransactionCategories(userId), transactionId ? fetchTransaction(transactionId, userId) : Promise.resolve(null), profileIncome ? fetchProfile(userId) : Promise.resolve(null)])
      .then(([loadedCategories, transaction, savedProfile]) => {
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
        } else if (profileIncome) {
          // Read the saved profile once. Later profile refreshes must not overwrite typed values.
          const draft = savedProfile ? buildProfileIncomeDraft(savedProfile, loadedCategories, today()) : null;
          setType('income');
          setAmount(draft?.amount ?? '');
          setSource(draft?.source ?? '');
          setDescription('');
          setTransactionDate(draft?.transactionDate ?? today());
          setCategoryId(draft?.categoryId ?? null);
          if (!draft) setMessage('No valid saved monthly amount is available. Enter the money you received.');
        } else {
          setCategoryId(loadedCategories.find((category) => category.type === 'expense')?.id ?? null);
        }
      }).catch(() => { if (active) setMessage('Could not load the transaction form.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [transactionId, userId, profileIncome]);

  const visibleCategories = useMemo(() => categories.filter((category) => category.type === type), [categories, type]);
  function selectType(next: TransactionType) {
    draftRevision.current += 1;
    setType(next);
    setCategoryId(categories.find((category) => category.type === next)?.id ?? null);
    setErrors({});
  }

  async function syncBudgetAlerts(previous: TransactionWithCategory | null, current: TransactionWithCategory) {
    try {
      // Shown in-app as well, so the warning never depends on push delivery alone.
      const summary = summarizeBudgetAlerts(await emitBudgetAlertsAfterTransactionChange(userId!, previous, current));
      if (summary) await appDialog.open(summary.title, summary.message);
      router.replace('/transactions' as never);
    } catch {
      appDialog.open(
        'Transaction saved',
        'The transaction is safe, but its budget alert could not synchronize. Retry the alert sync now?',
        [
          { text: 'Continue', onPress: () => router.replace('/transactions' as never) },
          { text: 'Retry sync', onPress: () => void syncBudgetAlerts(previous, current) },
        ],
      );
    }
  }

  async function reviewSavedPayment(transaction: TransactionWithCategory) {
    await appDialog.open('Payment already saved', 'An earlier save recorded this payment. Review it before creating another payment.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Review payment', onPress: () => router.replace({ pathname: '/transactions/[transactionId]', params: { transactionId: transaction.id } } as never) },
    ]);
  }

  async function confirmSimilarPayment(input: TransactionFormInput, payload: TransactionWriteInput): Promise<boolean> {
    if (input.type !== 'income' || transactionId) return true;
    while (alive.current) {
      let candidates: Awaited<ReturnType<typeof fetchIncomeCandidates>>;
      try { candidates = await fetchIncomeCandidates(userId!, payload); }
      catch {
        if (!alive.current) return false;
        const retry = await appDialog.open('Could not check existing income', 'Check your connection and retry before recording this payment.', [
          { text: 'Cancel', style: 'cancel' }, { text: 'Retry check' },
        ]);
        if (retry) continue;
        return false;
      }
      if (!alive.current) return false;
      const matches = findSimilarIncomeEntries(candidates.entries, input);
      if (!matches.length && !candidates.truncated) return true;
      const decision = { value: 'cancel' };
      const details = matches.slice(0, 5).map((entry) => `${entry.transaction_date}: ${entry.source} — RM ${Number(entry.amount).toFixed(2)}`).join('\n');
      await appDialog.open('Similar income already recorded', `${details || 'Several payments of this amount already exist this month.'}\n\n${candidates.truncated ? 'The results are limited. Review existing entries before continuing. ' : ''}Record another payment only if you received this money separately.`, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Review entries', onPress: () => { router.replace('/transactions' as never); } },
        { text: 'Record another payment', onPress: () => { decision.value = 'record'; } },
      ]);
      return alive.current && decision.value === 'record';
    }
    return false;
  }

  async function save() {
    if (!userId || loading || submitting.current) return;
    // Synchronous guard closes the gap before React renders the disabled save button.
    submitting.current = true;
    const submittedRevision = draftRevision.current;
    setSaving(true); setMessage(null);
    try {
      const input: TransactionFormInput = { type, amount, source, description, transactionDate, categoryId };
      const nextErrors = validateTransactionInput(input, categories, today());
      setErrors(nextErrors);
      if (Object.keys(nextErrors).length) return;
      const value = parseMoney(amount);
      if (value == null || categoryId == null) return;
      const payload: TransactionWriteInput = { id: draftId.current!, category_id: categoryId, amount: value, transaction_date: transactionDate, description: description.trim() || null, source: source.trim(), receipt_image_path: existingTransaction?.receipt_image_path ?? null };
      // A prior uncertain attempt is resolved before submitting edited draft values.
      if (!transactionId && attemptedPayload.current) {
        const previous = await fetchTransaction(attemptedPayload.current.id, userId);
        if (!alive.current) return;
        if (previous) {
          if (!transactionMatchesInput(previous, payload)) { await reviewSavedPayment(previous); return; }
          await syncBudgetAlerts(null, previous);
          return;
        }
      }
      if (!await confirmSimilarPayment(input, payload) || !alive.current) return;
      // Keyboard input can still change a focused field during an asynchronous check.
      // A confirmation for old values must never authorize a changed financial draft.
      if (submittedRevision !== draftRevision.current) {
        setMessage('The payment details changed. Review them and save again.');
        return;
      }
      attemptedPayload.current = payload;
      // The draft UUID belongs only to creates. Editing must retain the stored transaction ID.
      const { id, ...editablePayload } = payload;
      const saved = transactionId
        ? await updateTransaction(transactionId, userId, editablePayload)
        : await createTransactionWithRecovery(userId, { id, ...editablePayload });
      if (!alive.current) return;
      await syncBudgetAlerts(existingTransaction, saved);
    } catch (caught) {
      if (!alive.current) return;
      if (caught instanceof TransactionDraftConflictError) await reviewSavedPayment(caught.existing);
      else setMessage('Could not confirm that this transaction was saved. Check your connection and retry. Your earlier attempt will be checked first.');
    } finally {
      submitting.current = false;
      if (alive.current) setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={[header, { paddingTop: insets.top + 8 }]}><Pressable onPress={() => router.back()} style={back}><MaterialIcons name="arrow-back" size={27} color={authColors.onSurface} /></Pressable><Text style={title}>{transactionId ? 'Edit Transaction' : 'Add Transaction'}</Text></View>
      <View style={tabs}><Pressable onPress={() => {}} style={activeTab}><Text style={activeTabText}>Manual</Text></Pressable><Pressable onPress={() => router.replace('/transactions/scan' as never)} style={tab}><Text style={tabText}>Scan Receipt</Text></Pressable></View>
      {loading ? <View style={center}><ActivityIndicator color={authColors.primary} /></View> : <ScrollView pointerEvents={saving ? 'none' : 'auto'} style={{ flex: 1 }} keyboardDismissMode="on-drag" keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 30, gap: 18 }}>
        {profileIncome ? <Text style={label}>Confirm the money you received. Saving adds this payment to Reports.</Text> : null}
        <View style={segmented}><TypeButton active={type === 'expense'} label="Expense" onPress={() => selectType('expense')} /><TypeButton active={type === 'income'} label="Income" onPress={() => selectType('income')} /></View>
        <View style={amountCard}><Text style={fieldLabel}>Amount</Text><View style={{ flexDirection: 'row', alignItems: 'baseline' }}><Text style={rm}>RM</Text><TextInput editable={!saving} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={authColors.outline} value={amount} onChangeText={(value) => { draftRevision.current += 1; setAmount(value.replace(/[^0-9.]/g, '')); setErrors((old) => ({ ...old, amount: '' })); }} style={amountInput} /></View>{errors.amount ? <Text style={errorText}>{errors.amount}</Text> : null}</View>
        <View style={{ gap: 8 }}><Text style={label}>Category</Text><View style={categoryGrid}>{visibleCategories.map((category) => <Pressable key={category.id} onPress={() => { draftRevision.current += 1; setCategoryId(category.id); setErrors((old) => ({ ...old, categoryId: '' })); }} style={[categoryButton, categoryId === category.id && selectedCategory]}><CategoryIcon category={category} size={28} glyphSize={20} backgroundColor="transparent" /><Text numberOfLines={1} style={[categoryText, categoryId === category.id && { color: authColors.primary }]}>{category.name}</Text></Pressable>)}</View>{errors.categoryId ? <Text style={errorText}>{errors.categoryId}</Text> : null}</View>
        <Field editable={!saving} label={type === 'expense' ? 'Merchant' : 'Income source'} value={source} placeholder={type === 'expense' ? 'e.g. Campus Cafeteria' : 'e.g. Part-time salary'} error={errors.source} onChange={(value) => { draftRevision.current += 1; setSource(value); setErrors((old) => ({ ...old, source: '' })); }} />
        <TransactionDateField value={transactionDate} error={errors.transactionDate} onChange={(value) => { draftRevision.current += 1; setTransactionDate(value); setErrors((old) => ({ ...old, transactionDate: '' })); }} />
        <Field editable={!saving} label="Note (optional)" value={description} placeholder="Add a description…" error={errors.description} onChange={(value) => { draftRevision.current += 1; setDescription(value); setErrors((old) => ({ ...old, description: '' })); }} />
        {message ? <Text style={messageBox}>{message}</Text> : null}
        <Pressable disabled={saving} onPress={() => void save()} style={[saveButton, saving && { opacity: 0.65 }]}>{saving ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="check" size={22} color={authColors.onPrimary} />}<Text style={saveText}>{saving ? 'Saving…' : transactionId ? 'Save changes' : 'Add transaction'}</Text></Pressable>
      </ScrollView>}
    </KeyboardAvoidingView>
  );
}

function TypeButton({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) { return <Pressable onPress={onPress} style={[typeButton, active && activeTypeButton]}><Text style={[typeText, active && activeTypeText]}>{label}</Text></Pressable>; }
function Field({ label: fieldName, value, placeholder, error, editable = true, onChange }: { label: string; value: string; placeholder: string; error?: string; editable?: boolean; onChange: (value: string) => void }) { return <View style={{ gap: 7 }}><Text style={label}>{fieldName}</Text><TextInput editable={editable} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={authColors.outline} style={[input, error ? { borderColor: authColors.error } : null]} />{error ? <Text style={errorText}>{error}</Text> : null}</View>; }

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
