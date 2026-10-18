import { parseMoney } from './savings-domain';
import { isTransactionDate } from './transaction-date';
import type { ReceiptExtractionDraft } from './types';

export function receiptInitialDate(value: string | undefined, today: string) {
  // A picker may use today as its opening position; the transaction field must
  // remain empty until an actual receipt date or a manual selection is provided.
  return value && isTransactionDate(value) && value <= today ? value : '';
}

export function receiptReviewWarnings(extraction: ReceiptExtractionDraft, today: string): string[] {
  const warnings = [...(extraction.reviewWarnings ?? [])];
  // Derive missing-field warnings as well, including responses from older
  // backends which do not expose reviewRequired/reviewWarnings metadata.
  if (!extraction.merchant?.trim()) warnings.push('Merchant was not detected.');
  if (!receiptInitialDate(extraction.transactionDate, today)) warnings.push('Receipt date was not detected.');
  const amount = parseMoney(extraction.totalAmount ?? '');
  if (amount == null || amount <= 0) warnings.push('Total amount was not detected.');
  return [...new Set(warnings)];
}
