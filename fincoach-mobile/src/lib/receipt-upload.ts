/**
 * Builds the multipart body with an actual Blob/File.
 * Expo's native FormData encoder rejects legacy React Native pseudo-files
 * shaped like `{ uri, name, type }`.
 */
export function buildReceiptUploadForm(file: Blob) {
  const form = new FormData();
  form.append('file', file);
  return form;
}
