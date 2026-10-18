import type { BackupAttachment, BackupCounts, BackupSourceData, FinancialBackupDocumentV2 } from './types';

export const backupSections = ['profile', 'customCategories', 'userCategories', 'transactions', 'monthlyBudgets',
  'categoryLimits', 'savingsGoals', 'savingsContributions', 'reports', 'notificationPreferences', 'reminders', 'alerts'] as const;

export function backupCounts(data: BackupSourceData): BackupCounts {
  return Object.fromEntries(backupSections.map(key => [key, Array.isArray(data[key]) ? data[key]!.length : data[key] ? 1 : 0])) as BackupCounts;
}

export function attachmentReferences(data: BackupSourceData) {
  const refs: { bucket: BackupAttachment['bucket']; path: string }[] = [];
  for (const t of data.transactions) if (t.receipt_image_path) refs.push({ bucket: 'receipts', path: t.receipt_image_path });
  for (const r of data.reports) if (r.storage_path) refs.push({ bucket: 'financial-reports', path: r.storage_path });
  for (const c of data.customCategories) if (c.icon_image_path) refs.push({ bucket: 'category-icons', path: c.icon_image_path });
  return [...new Map(refs.map(ref => [`${ref.bucket}/${ref.path}`, ref])).values()];
}

export function safeOwnerPath(path: string, userId: string) {
  return path.startsWith(`${userId}/`) && !path.includes('\\') && !path.split('/').some(p => p === '..' || p === '.' || p === '');
}

/** Compare independent counts and ensure every referenced attachment is covered.
 * Never accept a document that silently omits a section or its required files. */
export function validateV2Document(document: FinancialBackupDocumentV2) {
  const actual = backupCounts(document.data);
  if (!document.counts || backupSections.some(key => !Number.isSafeInteger(document.counts[key]) || document.counts[key] !== actual[key])) {
    throw new Error('Backup is incomplete: section count mismatch.');
  }
  if (!Array.isArray(document.data.userCategories) || !Array.isArray(document.attachments)) throw new Error('Incomplete backup manifest.');
  const references = attachmentReferences(document.data);
  const keys = new Set<string>();
  for (const asset of document.attachments) {
    const key = `${asset.bucket}/${asset.path}`;
    if (!['receipts', 'financial-reports', 'category-icons'].includes(asset.bucket) || keys.has(key) ||
      !safeOwnerPath(asset.path, document.userId) || !safeOwnerPath(asset.backupPath, document.userId) ||
      !Number.isSafeInteger(asset.size) || asset.size <= 0 || !/^[a-f0-9]{64}$/.test(asset.checksumSha256) ||
      typeof asset.contentType !== 'string') throw new Error('Invalid backup attachment manifest.');
    keys.add(key);
  }
  if (keys.size !== references.length || references.some(ref => !keys.has(`${ref.bucket}/${ref.path}`))) {
    throw new Error('Backup is incomplete: missing attachment.');
  }
  // Ownership is checked for all rows, including nested goals and contributions.
  for (const key of backupSections) {
    const value = document.data[key];
    const rows = Array.isArray(value) ? value : value ? [value] : [];
    if (rows.some(row => 'user_id' in row && row.user_id !== document.userId)) throw new Error('Backup contains another account\'s records.');
    const ids = rows.filter(row => 'id' in row).map(row => (row as { id: unknown }).id);
    if (new Set(ids).size !== ids.length) throw new Error('Backup contains duplicate records.');
  }
  if (document.data.profile && document.data.profile.id !== document.userId) throw new Error('Backup profile owner mismatch.');
  const goals = new Set(document.data.savingsGoals.map(goal => goal.id));
  if (document.data.savingsContributions.some(c => !goals.has(c.goal_id))) throw new Error('Backup contribution has no saved goal.');
  for (const goal of document.data.savingsGoals) {
    const cents = document.data.savingsContributions.filter(c => c.goal_id === goal.id).reduce((sum, c) => sum + Math.round(Number(c.amount) * 100), 0);
    if (cents !== Math.round(Number(goal.current_amount) * 100)) throw new Error('Backup is incomplete: savings balance mismatch.');
  }
  return document;
}
