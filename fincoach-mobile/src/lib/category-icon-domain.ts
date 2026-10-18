export const CATEGORY_ICON_MAX_BYTES = 2 * 1024 * 1024;

export type CategoryIconExtension = 'jpg' | 'png' | 'webp';

export function base64ByteLength(value: string) {
  const padding = value.endsWith('==') ? 2 : value.endsWith('=') ? 1 : 0;
  return Math.max(0, Math.floor((value.length * 3) / 4) - padding);
}

export function categoryIconExtension(uri: string, mimeType?: string | null): CategoryIconExtension {
  const normalizedMimeType = mimeType?.toLowerCase();
  if (normalizedMimeType === 'image/png') return 'png';
  if (normalizedMimeType === 'image/webp') return 'webp';
  const extension = uri.split('?')[0].split('.').pop()?.toLowerCase();
  if (extension === 'png' || extension === 'webp') return extension;
  return 'jpg';
}
