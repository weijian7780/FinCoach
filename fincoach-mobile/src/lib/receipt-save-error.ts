/** Supabase/PostgREST can reject with a plain object rather than an Error. */
export function receiptSaveErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'message' in error && typeof error.message === 'string' && error.message.trim()) {
    if (/receipt_items/i.test(error.message) && /does not exist|schema cache|could not find/i.test(error.message)) {
      return 'Receipt saving needs a database update. The receipt items field is missing. Your scan is still here; retry after the database is updated.';
    }
    return error.message;
  }
  return 'Could not save this receipt. Please try again.';
}
