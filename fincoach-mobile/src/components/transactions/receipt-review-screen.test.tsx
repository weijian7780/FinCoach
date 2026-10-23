import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import ReviewReceiptScreen from '@/app/transactions/review';

const mocks = vi.hoisted(() => ({ draft: null as any, save: vi.fn(), clear: vi.fn(), replace: vi.fn() }));
vi.mock('@expo/vector-icons', () => ({ MaterialIcons: 'Icon' }));
vi.mock('expo-image', () => ({ Image: 'Image' }));
vi.mock('expo-router', () => ({ router: { replace: mocks.replace, back: vi.fn() } }));
vi.mock('react-native', () => ({ ActivityIndicator: 'ActivityIndicator', KeyboardAvoidingView: 'KeyboardAvoidingView',
  Platform: { OS: 'android' }, Pressable: 'Pressable', ScrollView: 'ScrollView', View: 'View' }));
vi.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 24, bottom: 24 }) }));
vi.mock('@/components/ui/app-text', () => ({ AppText: 'Text', AppTextInput: 'TextInput' }));
vi.mock('@/components/ui/app-dialog', () => ({ appDialog: { open: vi.fn() } }));
vi.mock('@/components/transactions/transaction-date-field', () => ({ TransactionDateField: 'DateField' }));
vi.mock('@/components/transactions/receipt-image-viewer', () => ({ ReceiptImageViewer: 'ImageViewer' }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ session: { user: { id: 'owner' } } }) }));
vi.mock('@/lib/receipt-ocr', () => ({ getReceiptDraft: () => mocks.draft, clearReceiptDraft: mocks.clear }));
vi.mock('@/lib/alert-events', () => ({ emitBudgetAlertsAfterTransactionChange: vi.fn().mockResolvedValue([]) }));
vi.mock('@/lib/transactions', () => ({ saveReceiptTransaction: mocks.save,
  fetchTransactionCategories: vi.fn().mockResolvedValue([{ id: 1, name: 'Food', type: 'expense' }]),
  TransactionDraftConflictError: class extends Error {} }));

let tree: ReactTestRenderer;
function saveButton() { return tree.root.findAllByType('Pressable' as never).find(n => n.findAllByType('Text' as never).some(t => t.children.join('') === 'Save transaction'))!; }
beforeEach(() => {
  vi.clearAllMocks();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  mocks.draft = { id: 'draft-id', uploading: false, uploaded: false, image: { uri: 'file:///receipt.jpg', mimeType: 'image/jpeg' },
    extraction: { merchant: 'Old Legend', transactionDate: '2026-10-10', totalAmount: '14.80', suggestedCategory: 'Food',
      items: [], rawLines: [], extractionSource: 'ocr_fallback', reviewWarnings: ['OCR fallback results'], confidence: {} } };
  mocks.save.mockResolvedValue({ id: 'draft-id' });
});
afterEach(async () => { if (tree) await act(async () => tree.unmount()); });

test('fallback needs acknowledgement; save failure preserves corrected draft for retry', async () => {
  await act(async () => { tree = create(<ReviewReceiptScreen />); });
  await act(async () => { await saveButton().props.onPress(); });
  expect(mocks.save).not.toHaveBeenCalled();
  const check = tree.root.findByProps({ accessibilityLabel: 'I reviewed the OCR fallback fields' });
  await act(async () => check.props.onPress());
  const merchant = tree.root.findAllByType('TextInput' as never).find(n => n.props.value === 'Old Legend')!;
  await act(async () => merchant.props.onChangeText('Corrected merchant'));
  mocks.save.mockRejectedValueOnce({ message: 'Storage unavailable' });
  await act(async () => { saveButton().props.onPress(); });
  expect(mocks.clear).not.toHaveBeenCalled();
  expect(tree.root.findAllByType('Text' as never).some(t => t.children.join('') === 'Storage unavailable')).toBe(true);
  await act(async () => { saveButton().props.onPress(); });
  expect(mocks.save).toHaveBeenCalledTimes(2);
  expect(mocks.save.mock.calls[1][1]).toMatchObject({ id: 'draft-id', source: 'Corrected merchant', amount: 14.80, receipt_items: [] });
  expect(mocks.clear).toHaveBeenCalledTimes(1);
});

test('Gemini results save without fallback acknowledgement and allow no line items', async () => {
  mocks.draft.extraction.extractionSource = 'gemini';
  await act(async () => { tree = create(<ReviewReceiptScreen />); });
  expect(tree.root.findAllByProps({ accessibilityRole: 'checkbox' })).toHaveLength(0);
  await act(async () => { saveButton().props.onPress(); });
  expect(mocks.save).toHaveBeenCalledTimes(1);
  expect(mocks.replace).toHaveBeenCalledWith('/transactions');
});
