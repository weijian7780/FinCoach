import { describe, expect, test } from 'vitest';
import { receiptSaveErrorMessage } from './receipt-save-error';

describe('receipt save errors', () => {
  test('explains the confirmed missing hosted column and PostgREST schema cache variant', () => {
    for (const message of ['column transactions.receipt_items does not exist', "Could not find the 'receipt_items' column of 'transactions' in the schema cache"]) {
      expect(receiptSaveErrorMessage({ code: '42703', message })).toContain('database update');
    }
  });
  test('preserves plain-object storage or permission failures and native exceptions', () => {
    expect(receiptSaveErrorMessage({ message: 'new row violates row-level security policy' })).toBe('new row violates row-level security policy');
    expect(receiptSaveErrorMessage(new Error('Network request failed'))).toBe('Network request failed');
    expect(receiptSaveErrorMessage(null)).toContain('Please try again');
  });
});
