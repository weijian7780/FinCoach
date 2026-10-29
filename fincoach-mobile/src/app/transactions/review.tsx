import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { TransactionDateField } from '@/components/transactions/transaction-date-field';
import { ReceiptImageViewer } from '@/components/transactions/receipt-image-viewer';
import { malaysiaToday } from '@/lib/transaction-date';
import { authColors, authFont } from '@/constants/auth-theme';
import { emitBudgetAlertsAfterTransactionChange } from '@/lib/alert-events';
import { summarizeBudgetAlerts } from '@/lib/alerts-domain';
import { useAuth } from '@/lib/auth-context';
import { clearReceiptDraft, getReceiptDraft } from '@/lib/receipt-ocr';
import { receiptInitialDate, receiptReviewWarnings } from '@/lib/receipt-review-domain';
import { receiptSaveErrorMessage } from '@/lib/receipt-save-error';
import { parseMoney } from '@/lib/savings-domain';
import { validateTransactionInput } from '@/lib/transaction-domain';
import { saveReceiptTransaction, fetchTransactionCategories, TransactionDraftConflictError } from '@/lib/transactions';
import type { Category, ReceiptItemDraft } from '@/lib/types';

type EditableReceiptItem = Omit<ReceiptItemDraft, 'amount'> & { amount: string };

export default function ReviewReceiptScreen() {
  const insets = useSafeAreaInsets();
  const draft = getReceiptDraft();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [merchant, setMerchant] = useState(draft?.extraction.merchant ?? '');
  const [amount, setAmount] = useState(draft?.extraction.totalAmount ?? '');
  const [date, setDate] = useState(receiptInitialDate(draft?.extraction.transactionDate, malaysiaToday()));
  const [viewingReceipt, setViewingReceipt] = useState(false);
  // Keep partial input such as "12." intact; convert to money only on save.
  const [items, setItems] = useState<EditableReceiptItem[]>((draft?.extraction.items ?? []).map((item) => ({ ...item, amount: String(item.amount) })));
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [fallbackReviewed, setFallbackReviewed] = useState(false);
  const isFallback = draft?.extraction.extractionSource === 'ocr_fallback';

  useEffect(() => {
    if (!draft) { router.replace('/transactions/scan' as never); return; }
    if (!userId) return;
    fetchTransactionCategories(userId).then((loaded) => {
      const expenses = loaded.filter((category) => category.type === 'expense');
      setCategories(expenses);
      setCategoryId(expenses.find((category) => category.name.toLowerCase() === draft.extraction.suggestedCategory.toLowerCase())?.id ?? null);
    }).catch(() => setMessage('Could not load categories.'));
  }, [draft, userId]);

  const selectedCategory = useMemo(() => categories.find((category) => category.id === categoryId), [categories, categoryId]);
  const reviewWarnings = draft ? receiptReviewWarnings(draft.extraction, malaysiaToday()) : [];
  if (!draft) return null;
  const receiptDraft = draft;

  function updateItem(index: number, patch: Partial<EditableReceiptItem>) { setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item)); }

  async function syncBudgetAlerts(saved: Awaited<ReturnType<typeof saveReceiptTransaction>>) {
    try {
      const summary = summarizeBudgetAlerts(await emitBudgetAlertsAfterTransactionChange(userId!, null, saved));
      if (summary) await appDialog.open(summary.title, summary.message);
      clearReceiptDraft();
      router.replace('/transactions' as never);
    } catch {
      appDialog.open(
        'Receipt transaction saved',
        'The transaction is safe, but its budget alert could not synchronize. Retry the alert sync now?',
        [
          { text: 'Continue', onPress: () => { clearReceiptDraft(); router.replace('/transactions' as never); } },
          { text: 'Retry sync', onPress: () => void syncBudgetAlerts(saved) },
        ],
      );
    }
  }
  async function save() {
    if (!userId || receiptDraft.uploading) return;
    if (isFallback && !fallbackReviewed) { setMessage('Review the OCR fallback fields and confirm them before saving.'); return; }
    if (!categoryId) { setMessage('Choose a category before saving.'); return; }
    if (items.some((item) => !item.description.trim() || (parseMoney(item.amount) ?? 0) <= 0)) {
      setMessage('Enter a name and positive amount for each item, or remove the empty item.'); return;
    }
    const input = { type: 'expense' as const, amount, source: merchant, transactionDate: date, description: 'Scanned receipt', categoryId };
    const errors = validateTransactionInput(input, categories, malaysiaToday());
    if (Object.keys(errors).length) { setMessage(Object.values(errors)[0] ?? 'Correct the highlighted receipt fields.'); return; }
    const parsedAmount = parseMoney(amount); if (parsedAmount == null) return;
    setSaving(true); setMessage(null);
    const transactionId = receiptDraft.id;
    const extension = receiptDraft.image.mimeType === 'image/png' ? 'png' : receiptDraft.image.mimeType === 'image/webp' ? 'webp' : 'jpg';
    const receiptPath = `${userId}/${transactionId}.${extension}`;
    const payload = { id: transactionId, category_id: categoryId, amount: parsedAmount, transaction_date: date, source: merchant.trim(), description: 'Scanned receipt', receipt_image_path: receiptPath,
      receipt_items: items.map(item => ({ ...item, description: item.description.trim(), amount: parseMoney(item.amount)! })) };
    try {
      const saved = await saveReceiptTransaction(userId, payload, receiptDraft,
        () => fetch(receiptDraft.image.uri).then(response => response.arrayBuffer()), receiptDraft.image.mimeType);
      await syncBudgetAlerts(saved);
    } catch (caught) {
      // Never delete an attachment while the database commit outcome is uncertain.
      if (caught instanceof TransactionDraftConflictError) {
        appDialog.open('Receipt already saved', 'This receipt was saved before these edits. Open the saved transaction to review or edit it.', [
          { text: 'Stay here', style: 'cancel' },
          { text: 'Open transaction', onPress: () => { clearReceiptDraft(); router.replace(`/transactions/${caught.existing.id}` as never); } },
        ]);
      }
      setMessage(receiptSaveErrorMessage(caught));
    } finally {
      receiptDraft.uploading = false;
      setSaving(false);
    }
  }

  return <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1, backgroundColor: authColors.surface }}>
    <View style={[header, { paddingTop: insets.top + 8 }]}><Pressable onPress={() => router.back()} style={back}><MaterialIcons name="arrow-back" size={27} color={authColors.onSurface} /></Pressable><Text style={title}>Review Receipt</Text></View>
    <ScrollView style={{ flex: 1 }} keyboardDismissMode="on-drag" keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 34, gap: 16 }}>
      <Pressable accessibilityLabel="Open full receipt image" onPress={() => setViewingReceipt(true)} style={{ alignSelf: 'center' }}>
        <Image source={{ uri: draft.image.uri }} contentFit="contain" style={receiptImage} />
      </Pressable>
      <Text style={helper}>Tap the receipt to enlarge it. Correct the extracted fields before saving.</Text>
      {reviewWarnings.length ? <View style={attentionCard}>
        <View style={attentionTitleRow}><MaterialIcons name="warning-amber" size={20} color="#8A4B00" /><Text style={attentionTitle}>Needs your attention</Text></View>
        {reviewWarnings.map((warning) => <Text key={warning} style={attentionText}>• {warning}</Text>)}
        <Text style={attentionHint}>Correct these fields below or rescan the receipt.</Text>
      </View> : null}
      {draft.extraction.suggestedCategory ? <View style={suggestion}><MaterialIcons name="auto-awesome" size={16} color={authColors.primary} /><Text style={suggestionText}>Suggested: {draft.extraction.suggestedCategory}</Text></View> : null}
      <EditField label="Merchant" value={merchant} onChange={setMerchant} />
      <EditField label="Total amount (RM)" value={amount} onChange={(value) => setAmount(value.replace(/[^0-9.]/g, ''))} keyboard="decimal-pad" />
      <TransactionDateField value={date} onChange={setDate} />
      <View style={{ gap: 8 }}><Text style={label}>Category</Text><View style={categoryWrap}>{categories.map((category) => <Pressable key={category.id} onPress={() => setCategoryId(category.id)} style={[categoryChip, category.id === categoryId && selectedChip]}><Text style={[categoryChipText, category.id === categoryId && { color: authColors.primary }]}>{category.name}</Text></Pressable>)}</View>{selectedCategory ? null : <Text style={errorText}>Choose a category.</Text>}</View>
      <View style={itemsCard}>
        <View style={itemsHeader}><Text style={sectionTitle}>Items</Text><Pressable onPress={() => setItems((current) => [...current, { description: '', amount: '' }])}><MaterialIcons name="add-circle" size={24} color={authColors.primary} /></Pressable></View>
        {items.length ? items.map((item, index) => <View key={index} style={itemRow}>
          <View style={{ flex: 1, gap: 3 }}>
            <TextInput value={item.description} onChangeText={(value) => updateItem(index, { description: value })} placeholder="Item" style={itemName} />
            {item.modifiers?.length ? <Text style={{ fontSize: 12, color: authColors.onSurfaceVariant }}>{item.modifiers.join(' · ')}</Text> : null}
          </View>
          <Text style={itemRm}>RM</Text><TextInput keyboardType="decimal-pad" value={item.amount} onChangeText={(value) => updateItem(index, { amount: value.replace(/[^0-9.]/g, '') })} style={itemAmount} />
          <Pressable onPress={() => setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))}><MaterialIcons name="close" size={19} color={authColors.outline} /></Pressable>
        </View>) : <Text style={helper}>No line items detected. The transaction can still be saved.</Text>}
      </View>
      {message ? <Text style={messageBox}>{message}</Text> : null}
      {isFallback ? <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: fallbackReviewed }} accessibilityLabel="I reviewed the OCR fallback fields" onPress={() => setFallbackReviewed((value) => !value)} style={[attentionCard, { flexDirection: 'row', alignItems: 'center', minHeight: 48 }]}>
        <MaterialIcons name={fallbackReviewed ? 'check-box' : 'check-box-outline-blank'} size={24} color={authColors.primary} />
        <Text style={[attentionText, { flex: 1 }]}>I checked the merchant, date, total and items against the receipt image.</Text>
      </Pressable> : null}
      <Pressable disabled={saving} onPress={() => void save()} style={[saveButton, saving && { opacity: 0.65 }]}>{saving ? <ActivityIndicator color="white" /> : <MaterialIcons name="check-circle" size={21} color="white" />}<Text style={saveText}>{saving ? 'Saving receipt…' : 'Save transaction'}</Text></Pressable>
      <Pressable onPress={() => { appDialog.open('Rescan receipt?', 'The current extraction will be discarded.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Rescan', onPress: () => { clearReceiptDraft(); router.replace('/transactions/scan' as never); } }]); }}><Text style={rescan}>Rescan receipt</Text></Pressable>
    </ScrollView>
    <ReceiptImageViewer uri={draft.image.uri} originalUri={draft.image.originalUri} visible={viewingReceipt} onClose={() => setViewingReceipt(false)} />
  </KeyboardAvoidingView>;
}

function EditField({ label: name, value, onChange, placeholder, keyboard }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; keyboard?: 'decimal-pad' }) { return <View style={{ gap: 7 }}><Text style={label}>{name}</Text><TextInput value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={authColors.outline} keyboardType={keyboard} style={input} /></View>; }
const header = { minHeight: 66, paddingHorizontal: 18, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 8 } as const; const back = { width: 40, height: 44, justifyContent: 'center' } as const; const title = { fontSize: 24, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const receiptImage = { width: 116, height: 116, borderRadius: 18, alignSelf: 'center', backgroundColor: authColors.surfaceContainer } as const; const helper = { textAlign: 'center', fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const;
const attentionCard = { padding: 14, gap: 7, borderRadius: 16, borderWidth: 1, borderColor: '#FFB95C', backgroundColor: '#FFF1D6' } as const; const attentionTitleRow = { flexDirection: 'row', alignItems: 'center', gap: 7 } as const; const attentionTitle = { fontSize: 15, fontFamily: authFont.bold, color: '#663700' } as const; const attentionText = { fontSize: 13, fontFamily: authFont.regular, color: '#663700' } as const; const attentionHint = { marginTop: 2, fontSize: 12, fontFamily: authFont.semibold, color: '#8A4B00' } as const;
const suggestion = { alignSelf: 'center', flexDirection: 'row', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 18, backgroundColor: authColors.primaryFixed } as const; const suggestionText = { fontSize: 13, fontFamily: authFont.semibold, color: authColors.primary } as const;
const label = { fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface } as const; const input = { minHeight: 54, paddingHorizontal: 15, borderRadius: 14, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: 'white', fontFamily: authFont.regular, color: authColors.onSurface } as const;
const categoryWrap = { flexDirection: 'row', flexWrap: 'wrap', gap: 8 } as const; const categoryChip = { paddingHorizontal: 13, paddingVertical: 9, borderRadius: 18, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: 'white' } as const; const selectedChip = { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed } as const; const categoryChipText = { fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const itemsCard = { padding: 15, gap: 10, borderRadius: 18, backgroundColor: 'white', elevation: 2 } as const; const itemsHeader = { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' } as const; const sectionTitle = { fontSize: 16, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const itemRow = { minHeight: 45, flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 11, backgroundColor: authColors.surfaceContainerLow } as const; const itemName = { minHeight: 36, fontFamily: authFont.regular, color: authColors.onSurface } as const; const itemRm = { fontSize: 12, color: authColors.outline } as const; const itemAmount = { width: 58, textAlign: 'right', fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const errorText = { fontSize: 12, color: authColors.error } as const; const messageBox = { padding: 12, borderRadius: 12, backgroundColor: '#FFDAD6', color: authColors.error } as const;
const saveButton = { minHeight: 56, borderRadius: 16, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary, elevation: 4 } as const; const saveText = { fontSize: 16, fontFamily: authFont.semibold, color: 'white' } as const; const rescan = { textAlign: 'center', color: authColors.primary, fontFamily: authFont.semibold } as const;
