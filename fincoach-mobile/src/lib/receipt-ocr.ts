import { fetch } from 'expo/fetch';
import { File } from 'expo-file-system';

import { fincoachApiUrl } from '@/lib/env';
import { buildReceiptUploadForm } from '@/lib/receipt-upload';
import type { ReceiptExtractionDraft } from '@/lib/types';

export type ReceiptImageDraft = {
  uri: string;
  fileName: string;
  mimeType: string;
};

let currentDraft: { image: ReceiptImageDraft; extraction: ReceiptExtractionDraft } | null = null;

export function setReceiptDraft(image: ReceiptImageDraft, extraction: ReceiptExtractionDraft) {
  currentDraft = { image, extraction };
}

export function getReceiptDraft() {
  return currentDraft;
}

export function clearReceiptDraft() {
  currentDraft = null;
}

export async function extractReceipt(image: ReceiptImageDraft, accessToken: string) {
  if (!fincoachApiUrl) throw new Error('Set EXPO_PUBLIC_FINCOACH_API_URL to the FastAPI server address.');
  // File implements Blob and is supported by Expo's native multipart encoder.
  const form = buildReceiptUploadForm(new File(image.uri));
  const response = await fetch(`${fincoachApiUrl}/receipts/extract`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: form,
  });
  const payload = await response.json().catch(() => null) as ReceiptExtractionDraft | { detail?: string } | null;
  if (!response.ok) {
    throw new Error(payload && 'detail' in payload && payload.detail ? payload.detail : 'Receipt extraction failed.');
  }
  return payload as ReceiptExtractionDraft;
}
