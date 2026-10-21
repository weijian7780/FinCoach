import { describe, expect, test } from 'vitest';

import { receiptInitialDate, receiptReviewWarnings } from './receipt-review-domain';
import type { ReceiptExtractionDraft } from './types';

const draft: ReceiptExtractionDraft = { merchant: '', transactionDate: '', totalAmount: '', suggestedCategory: '', items: [], rawLines: [], confidence: { merchant: 0, transactionDate: 0, totalAmount: 0, category: 0 } };

describe('receipt review cannot hide incomplete extraction', () => {
  test('older responses without warning metadata still show missing fields', () => {
    expect(receiptReviewWarnings(draft, '2026-10-03')).toEqual(['Merchant was not detected.', 'Receipt date was not detected.', 'Total amount was not detected.']);
    expect(receiptInitialDate(draft.transactionDate, '2026-10-03')).toBe('');
  });
  test('future dates remain empty instead of silently becoming today', () => {
    expect(receiptInitialDate('2033-03-10', '2026-10-03')).toBe('');
    expect(receiptInitialDate('2026-10-03', '2026-10-03')).toBe('2026-10-03');
  });
  test('backend conflict warnings survive valid-looking fields without duplicates', () => {
    const result = { ...draft, merchant: 'CAFE', transactionDate: '2026-10-03', totalAmount: '24.50', reviewWarnings: ['Please confirm the payment.', 'Please confirm the payment.'] };
    expect(receiptReviewWarnings(result, '2026-10-03')).toEqual(['Please confirm the payment.']);
  });
});
