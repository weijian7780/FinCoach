import * as Crypto from 'expo-crypto';
import { decode } from 'base64-arraybuffer';
import { attachmentReferences, safeOwnerPath } from './backup-v2-domain';
import { defaultExportBackupClient, type ExportBackupDataClient } from './export-backup';
import type { BackupAttachment, BackupSourceData, FinancialBackupDocumentV2 } from './types';

export async function blobBytes(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === 'function') return blob.arrayBuffer();
  // Native React Native Blobs may lack both text() and arrayBuffer().
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== 'string' || !reader.result.includes(';base64,')) reject(new Error('Attachment could not be read.'));
      else resolve(decode(reader.result.split(';base64,')[1]));
    };
    reader.onerror = () => reject(reader.error ?? new Error('Attachment could not be read.'));
    reader.onabort = () => reject(new Error('Attachment reading cancelled.'));
    reader.readAsDataURL(blob);
  });
}

export async function hashAttachment(bytes: ArrayBuffer) {
  const hash = await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, bytes);
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}

async function downloaded(bucket: string, path: string, client: ExportBackupDataClient) {
  const result = await client.storage.from(bucket).download(path);
  if (result.error || !result.data) throw new Error(`Required attachment is unavailable: ${bucket}/${path}`);
  return result.data as Blob;
}

const mimeExtensions: Record<string, string> = { 'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' };

/** Backup copies are immutable and independent of the original file lifecycle. */
export async function captureBackupAttachments(userId: string, backupId: string, source: BackupSourceData,
  client: ExportBackupDataClient = defaultExportBackupClient,
  digest: (bytes: ArrayBuffer) => Promise<string> = hashAttachment): Promise<BackupAttachment[]> {
  const manifest: BackupAttachment[] = [];
  try {
    for (const ref of attachmentReferences(source)) {
      if (!safeOwnerPath(ref.path, userId)) throw new Error('Attachment owner mismatch.');
      const blob = await downloaded(ref.bucket, ref.path, client);
      const bytes = await blobBytes(blob);
      const contentType = blob.type.split(';')[0];
      if (!mimeExtensions[contentType] || !bytes.byteLength) throw new Error('Unsupported or empty backup attachment.');
      const checksumSha256 = await digest(bytes);
      const backupPath = `${userId}/assets/${backupId}/${manifest.length}-${checksumSha256}.${mimeExtensions[contentType]}`;
      const result = await client.storage.from('financial-backups').upload(backupPath, bytes, { contentType, upsert: false });
      if (result.error) throw result.error;
      manifest.push({ ...ref, backupPath, contentType, size: bytes.byteLength, checksumSha256 });
      // Verify the actual stored copy before allowing the backup to complete.
      const stored = await downloaded('financial-backups', backupPath, client);
      const storedBytes = await blobBytes(stored);
      if (storedBytes.byteLength !== bytes.byteLength || await digest(storedBytes) !== checksumSha256) throw new Error('Attachment copy verification failed.');
    }
    return manifest;
  } catch (error) {
    if (manifest.length) await client.storage.from('financial-backups').remove(manifest.map(a => a.backupPath));
    throw error;
  }
}

export type RestoredAttachmentPath = { bucket: BackupAttachment['bucket']; path: string; restoredPath: string };

/** Every copy is downloaded and hashed before any financial rows are replaced.
 * Existing source objects are never overwritten; recovery uses new owned paths. */
export async function prepareRestoreAttachments(backupId: string, document: FinancialBackupDocumentV2,
  client: ExportBackupDataClient = defaultExportBackupClient,
  digest: (bytes: ArrayBuffer) => Promise<string> = hashAttachment) {
  // Separate attempts must never clean up objects committed by another restore.
  const attemptId = Crypto.randomUUID();
  const paths: RestoredAttachmentPath[] = [];
  const created: RestoredAttachmentPath[] = [];
  const cleanup = async () => {
    for (const ref of created) {
      const result = await client.storage.from(ref.bucket).remove([ref.restoredPath]);
      if (result.error) console.warn('Unused restored attachment cleanup will need retry.', result.error);
    }
  };
  try {
    // Read and verify each immutable copy, then upload into the recovery namespace.
    for (const [index, asset] of document.attachments.entries()) {
      const blob = await downloaded('financial-backups', asset.backupPath, client);
      const bytes = await blobBytes(blob);
      if (bytes.byteLength !== asset.size || await digest(bytes) !== asset.checksumSha256) throw new Error('Backup attachment checksum or size mismatch.');
      const restoredPath = `${document.userId}/restored/${backupId}/${attemptId}/${index}-${asset.checksumSha256}.${mimeExtensions[asset.contentType]}`;
      const ref = { bucket: asset.bucket, path: asset.path, restoredPath };
      const existing = await client.storage.from(asset.bucket).download(restoredPath);
      if (existing.data && !existing.error) {
        const existingBytes = await blobBytes(existing.data as Blob);
        if (existingBytes.byteLength !== asset.size || await digest(existingBytes) !== asset.checksumSha256) throw new Error('Recovery destination contains different data.');
      } else {
        const result = await client.storage.from(asset.bucket).upload(restoredPath, bytes, { contentType: asset.contentType, upsert: false });
        if (result.error) throw result.error;
        created.push(ref);
        const uploaded = await blobBytes(await downloaded(asset.bucket, restoredPath, client));
        if (uploaded.byteLength !== asset.size || await digest(uploaded) !== asset.checksumSha256) throw new Error('Recovered attachment verification failed.');
      }
      paths.push(ref);
    }
    return { paths, cleanup };
  } catch (error) {
    await cleanup();
    throw error;
  }
}

export async function removeBackupAttachmentCopies(userId: string, backupId: string,
  client: ExportBackupDataClient = defaultExportBackupClient) {
  const prefix = `${userId}/assets/${backupId}`;
  // Delete from the front on each iteration; offset pagination while deleting
  // would skip objects as the remaining list shrinks.
  while (true) {
    const result = await client.storage.from('financial-backups').list(prefix, { limit: 100, offset: 0 });
    if (result.error) throw result.error;
    const files = (result.data ?? []) as { name: string }[];
    if (!files.length) return;
    const removed = await client.storage.from('financial-backups').remove(files.map(f => `${prefix}/${f.name}`));
    if (removed.error) throw removed.error;
  }
}
