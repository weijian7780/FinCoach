/** Additional acceptance checks use disposable users only. Failed checks are
 * evidence of product gaps, not a reason to skip cleanup or later checks. */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { SupabaseClient } from '@supabase/supabase-js';
import * as api from '../src/lib/export-backup';
import { buildExportCsv, buildExportHtml, validateExportSelection } from '../src/lib/export-backup-domain';
import { downloadAndValidateBackup, performCloudBackup, type BackupOrchestratorDependencies } from '../src/lib/backup-orchestrator';
import type { ExportContentType, ExportSelection } from '../src/lib/types';

type Context = {
  client: SupabaseClient; admin: SupabaseClient; userId: string;
  other: SupabaseClient; otherId: string; deps: BackupOrchestratorDependencies;
  uploaded: { bucket: string; path: string }[];
  check: (name: string, passed: boolean, detail?: unknown) => void;
  outputDirectory: string;
};
async function checked<T>(operation: PromiseLike<{ data: T; error: unknown }>) {
  const { data, error } = await operation;
  if (error) throw error;
  return data;
}

export async function auditExtendedExportBackup(ctx: Context) {
  const { client, userId, other, otherId, deps, uploaded, check, outputDirectory } = ctx;
  mkdirSync(outputDirectory, { recursive: true });
  const dataClient = client as unknown as api.ExportBackupDataClient;
  const sourceBefore = await deps.fetchBackupSourceData(userId);
  const categoryId = sourceBefore.customCategories[0].id;
  const specialDescription = 'AUDIT_UNICODE_测试 café "quoted", comma\nsecond line';
  await checked(client.from('transactions').insert([
    { user_id: userId, category_id: categoryId, amount: 23.45, transaction_date: '2026-10-01', description: specialDescription, source: 'manual' },
    { user_id: userId, category_id: categoryId, amount: 3, transaction_date: '2026-10-07', description: 'AUDIT_END_BOUNDARY', source: 'manual' },
    { user_id: userId, category_id: categoryId, amount: 4, transaction_date: '2026-09-30', description: 'AUDIT_BEFORE_RANGE', source: 'manual' },
    { user_id: userId, category_id: categoryId, amount: 5, transaction_date: '2026-10-08', description: 'AUDIT_AFTER_RANGE', source: 'manual' },
    { user_id: userId, category_id: categoryId, amount: 6, transaction_date: '2026-10-02', description: '=1+1', source: 'manual' },
  ]));
  await checked(client.from('monthly_budgets').insert([
    { user_id: userId, month: '2026-09-01', limit_amount: 800 },
    { user_id: userId, month: '2026-11-01', limit_amount: 700 },
  ]));
  // Only this test's second account is used for the isolation sentinel.
  const otherCategory = await checked(other.from('categories').insert({ user_id: otherId, name: 'Other audit category', type: 'expense', icon: 'restaurant', color: '#123456' }).select().single());
  const otherTransaction = await checked(other.from('transactions').insert({ user_id: otherId, category_id: otherCategory.id,
    amount: 19.19, transaction_date: '2026-10-01', description: 'AUDIT_OTHER_ACCOUNT', source: 'manual' }).select().single());
  const selection: ExportSelection = { format: 'csv', contents: ['transaction', 'budget', 'savings'], startDate: '2026-10-01', endDate: '2026-10-07' };
  const source = await api.fetchExportSourceData(userId, selection, dataClient);
  check('live export includes both transaction date boundaries', source.transactions.some(t => t.description === specialDescription) && source.transactions.some(t => t.description === 'AUDIT_END_BOUNDARY'));
  check('live export excludes transactions outside selected dates', !source.transactions.some(t => /AUDIT_(BEFORE|AFTER)_RANGE/.test(t.description ?? '')));
  check('live export excludes other account data', !source.transactions.some(t => t.user_id !== userId));
  check('live export budgets use only intersecting months', source.monthlyBudgets.length === 1 && source.monthlyBudgets[0].month === '2026-10-01');
  check('empty section selection rejected', !!validateExportSelection({ ...selection, contents: [] }));
  check('reversed date range rejected', !!validateExportSelection({ ...selection, startDate: '2026-11-01' }));
  check('invalid calendar date rejected', !!validateExportSelection({ ...selection, startDate: '2026-02-30' }));

  const options: ExportContentType[] = ['transaction', 'budget', 'savings'];
  const headings = ['Transactions', 'Budgets', 'Savings Goals'];
  const manifest: unknown[] = [];
  for (let mask = 1; mask < 8; mask++) {
    const contents = options.filter((_, index) => mask & (1 << index));
    for (const format of ['csv', 'pdf'] as const) {
      const chosen = { ...selection, format, contents };
      const name = `selection-${mask}`;
      const content = format === 'csv' ? buildExportCsv(source, chosen) : buildExportHtml(source, chosen);
      writeFileSync(join(outputDirectory, `${name}.${format === 'csv' ? 'csv' : 'html'}`), content, 'utf8');
      check(`${format} section selection ${mask} includes exactly requested sections`, headings.every((heading, i) =>
        content.includes(format === 'pdf' ? `<h2>${heading}</h2>` : heading + '\r\n') === contents.includes(options[i])));
      // Real metadata operations follow the production generation sequence;
      // PDF native printing is deliberately not claimed by these metadata checks.
      const record = await api.createDataExport(userId, chosen, `${name}.${format}`, dataClient);
      await api.saveExportContents(record.id, contents, dataClient);
      await api.updateDataExport(record.id, userId, { status: 'processing' }, dataClient);
      const completed = await api.updateDataExport(record.id, userId, { status: 'completed',
        completed_at: new Date().toISOString(), file_size_bytes: format === 'csv' ? Buffer.byteLength(content) : null }, dataClient);
      const storedContents = await checked(client.from('export_contents').select('content_type').eq('export_id', record.id));
      check(`${format} export history ${mask} stores selected contents`, completed.status === 'completed' &&
        JSON.stringify(storedContents!.map(r => r.content_type).sort()) === JSON.stringify([...contents].sort()));
      manifest.push({ mask, format, contents, expectedTransactionRows: contents.includes('transaction') ? source.transactions.length : 0 });
    }
  }
  writeFileSync(join(outputDirectory, 'selection-manifest.json'), JSON.stringify({ manifest, specialDescription,
    transactionDescriptions: source.transactions.map(t => t.description), expectedTransactionRows: source.transactions.length }, null, 2));
  const csv = buildExportCsv(source, selection);
  check('CSV neutralizes formula-like transaction descriptions', !csv.includes(',=1+1,'), { observedRawFormula: csv.includes(',=1+1,') });
  check('PDF source preserves transaction source field available in CSV', buildExportHtml(source, selection).includes('<th>Source</th>'));
  const empty = await api.fetchExportSourceData(userId, { ...selection, startDate: '2020-01-01', endDate: '2020-01-31' }, dataClient);
  check('empty date range contains no transactions or budgets', empty.transactions.length === 0 && empty.monthlyBudgets.length === 0 && empty.categoryLimits.length === 0);
  check('savings export is current snapshot independent of date range', empty.savingsGoals.length === source.savingsGoals.length && empty.savingsGoals.length > 0);
  writeFileSync(join(outputDirectory, 'empty-transactions.csv'), buildExportCsv(empty, { ...selection, contents: ['transaction'] }));

  // Malaysia's Oct 1 00:30 is Sep 30 16:30 UTC. Test both window edges.
  const reportFixtures = await checked(client.from('reports').insert([
    { user_id: userId, period: 'AUDIT_EARLY_OCT', type: 'monthly', generated_at: '2026-09-30T16:30:00Z' },
    { user_id: userId, period: 'AUDIT_EARLY_NOV', type: 'monthly', generated_at: '2026-10-31T16:30:00Z' },
  ]).select());
  const reportSource = await api.fetchExportSourceData(userId, { ...selection, endDate: '2026-10-31', contents: ['report'] }, dataClient);
  check('report export includes Malaysia start-day early hours', reportSource.reports.some(r => r.id === reportFixtures![0].id));
  check('report export excludes Malaysia next-month early hours', !reportSource.reports.some(r => r.id === reportFixtures![1].id));

  // Capture actual attachment bytes, remove only this run's objects, and restore.
  const receiptPath = `${userId}/audit-receipt.png`;
  const receiptBytes = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB1sAAAAASUVORK5CYII=', 'base64');
  await checked(client.storage.from('receipts').upload(receiptPath, receiptBytes, { contentType: 'image/png' }));
  uploaded.push({ bucket: 'receipts', path: receiptPath });
  await checked(client.from('transactions').update({ receipt_image_path: receiptPath, source: 'receipt' }).eq('id', source.transactions[0].id).eq('user_id', userId));
  const iconPath = `${userId}/audit-category.png`;
  await checked(client.storage.from('category-icons').upload(iconPath, receiptBytes, { contentType: 'image/png' }));
  uploaded.push({ bucket: 'category-icons', path: iconPath });
  await checked(client.from('categories').update({ icon_image_path: iconPath }).eq('id', categoryId).eq('user_id', userId));
  const attachmentBackup = await performCloudBackup(userId, 'manual', deps);
  const attachmentBlob = await api.downloadBackupObject(attachmentBackup.storage_path!, dataClient);
  const attachmentDocument = await downloadAndValidateBackup(attachmentBackup, userId, deps, attachmentBlob);
  const reportPath = attachmentDocument.data.reports.find(r => r.storage_path)?.storage_path;
  check('backup stores receipt and report path metadata', attachmentDocument.data.transactions.some(t => t.receipt_image_path === receiptPath) && !!reportPath);
  await checked(client.storage.from('receipts').remove([receiptPath]));
  await checked(client.storage.from('category-icons').remove([iconPath]));
  // A successful Storage delete response can contain no deleted objects when
  // the user's RLS policy disallows deletion. Admin removes only our own fixture.
  if (reportPath) await checked(ctx.admin.storage.from('financial-reports').remove([reportPath]));
  const reportFolder = reportPath?.slice(0, reportPath.lastIndexOf('/'));
  const reportLeaf = reportPath?.split('/').at(-1);
  const removedReports = reportPath ? await checked(ctx.admin.storage.from('financial-reports').list(reportFolder!, { search: reportLeaf })) : [];
  check('missing-report recovery fixture is actually deleted', removedReports?.length === 0);
  // Restore should not silently undo a more recent privacy decision.
  await checked(client.from('profiles').update({ spending_records_consent: 'denied', auto_backup_enabled: false }).eq('id', userId));
  await api.restoreFinancialBackup(attachmentBackup.id, attachmentDocument, dataClient);
  const afterAttachment = await deps.fetchBackupSourceData(userId);
  const recoveredReceiptPath = afterAttachment.transactions.find(t => t.receipt_image_path)?.receipt_image_path;
  const receipt = recoveredReceiptPath ? await client.storage.from('receipts').download(recoveredReceiptPath) : { data: null, error: true };
  const recoveredReportPath = afterAttachment.reports.find(r => r.storage_path)?.storage_path;
  const recoveredReport = recoveredReportPath ? await client.storage.from('financial-reports').download(recoveredReportPath) : { data: null, error: true };
  check('restore recovers deleted receipt image bytes', !receipt.error && !!receipt.data);
  check('restore recovers deleted generated report PDF object', !recoveredReport.error && !!recoveredReport.data);
  const recoveredIconPath = afterAttachment.customCategories.find(c => c.id === categoryId)?.icon_image_path;
  const recoveredIcon = recoveredIconPath ? await client.storage.from('category-icons').download(recoveredIconPath) : { data: null, error: true };
  check('restore recovers deleted custom category image bytes', !recoveredIcon.error && !!recoveredIcon.data &&
    Buffer.from(await recoveredIcon.data.arrayBuffer()).equals(receiptBytes));
  // A well-formed but edited financial document cannot bypass the immutable
  // server snapshot even if a caller bypasses client checksum validation.
  const edited = structuredClone(attachmentDocument);
  edited.data.transactions[0].amount += 1;
  const editedRestore = await client.rpc('restore_financial_backup_v2', { payload: edited, backup_record_id: attachmentBackup.id, restored_paths: [] });
  check('server rejects edited v2 financial snapshot', !!editedRestore.error);
  const foreignContribution = structuredClone(attachmentDocument);
  foreignContribution.data.savingsContributions[0].goal_id = otherTransaction.id;
  const foreignRestore = await client.rpc('restore_financial_backup_v1', { payload: { ...foreignContribution, schemaVersion: 1 }, backup_record_id: attachmentBackup.id });
  check('legacy RPC rejects contribution links outside owned snapshot', !!foreignRestore.error);
  const unchangedAfterRejected = await deps.fetchBackupSourceData(userId);
  check('rejected modified snapshots preserve all transaction values', JSON.stringify(unchangedAfterRejected.transactions) === JSON.stringify(afterAttachment.transactions));
  check('restore preserves newer denied spending consent', afterAttachment.profile?.spending_records_consent === 'denied', { actual: afterAttachment.profile?.spending_records_consent });
  check('restore preserves current automatic backup toggle', afterAttachment.profile?.auto_backup_enabled === false);

  // Above-cap input distinguishes a successful operation from complete data.
  const largeRows = Array.from({ length: 1105 }, (_, index) => ({ user_id: userId, category_id: categoryId,
    amount: 1 + index / 100, transaction_date: '2026-10-05', description: `AUDIT_BULK_${String(index).padStart(4, '0')}`, source: 'manual' }));
  for (let start = 0; start < largeRows.length; start += 250) await checked(client.from('transactions').insert(largeRows.slice(start, start + 250)));
  async function transactionCount(inWindow = false) {
    let query = client.from('transactions').select('id', { count: 'exact', head: true }).eq('user_id', userId);
    if (inWindow) query = query.gte('transaction_date', selection.startDate).lte('transaction_date', selection.endDate);
    const result = await query;
    if (result.error) throw result.error;
    return result.count!;
  }
  const expectedTotal = await transactionCount();
  const expectedSelected = await transactionCount(true);
  const goalId = sourceBefore.savingsGoals[0].id;
  await checked(client.from('savings_goals').update({ target_amount: 10000 }).eq('id', goalId).eq('user_id', userId));
  const contributions = Array.from({ length: 1005 }, (_, index) => ({ goal_id: goalId, amount: 1,
    contributed_on: '2026-10-01', note: `AUDIT_CONTRIBUTION_${index}` }));
  for (let start = 0; start < contributions.length; start += 250) await checked(client.from('savings_contributions').insert(contributions.slice(start, start + 250)));
  const fullGoal = await checked(client.from('savings_goals').select('current_amount').eq('id', goalId).single());
  if (!fullGoal) throw new Error('Disposable savings goal not found before backup.');
  const largeExport = await api.fetchExportSourceData(userId, selection, dataClient);
  check('export fetch includes all selected rows above API row cap', largeExport.transactions.length === expectedSelected,
    { expected: expectedSelected, actual: largeExport.transactions.length });
  writeFileSync(join(outputDirectory, 'large-export.csv'), buildExportCsv(largeExport, { ...selection, contents: ['transaction'] }));
  writeFileSync(join(outputDirectory, 'large-export.html'), buildExportHtml(largeExport, { ...selection, contents: ['transaction'] }));
  const largeBackup = await performCloudBackup(userId, 'manual', deps);
  const largeBlob = await api.downloadBackupObject(largeBackup.storage_path!, dataClient);
  const largeDocument = await downloadAndValidateBackup(largeBackup, userId, deps, largeBlob);
  check('completed cloud backup includes all transaction rows above API row cap', largeDocument.data.transactions.length === expectedTotal,
    { expected: expectedTotal, actual: largeDocument.data.transactions.length, status: largeBackup.status });
  const expectedContributions = sourceBefore.savingsContributions.length + contributions.length;
  check('completed cloud backup includes all savings contributions above API row cap', largeDocument.data.savingsContributions.length === expectedContributions,
    { expected: expectedContributions, actual: largeDocument.data.savingsContributions.length });
  await api.restoreFinancialBackup(largeBackup.id, largeDocument, dataClient);
  const restoredCount = await transactionCount();
  check('restore preserves full pre-backup transaction count', restoredCount === expectedTotal,
    { beforeBackup: expectedTotal, afterRestore: restoredCount, lost: expectedTotal - restoredCount });
  const restoredGoal = await checked(client.from('savings_goals').select('current_amount').eq('id', goalId).single());
  if (!restoredGoal) throw new Error('Disposable savings goal not found after restore.');
  check('restore preserves savings balance above contribution row cap', restoredGoal.current_amount === fullGoal.current_amount,
    { beforeBackup: fullGoal.current_amount, afterRestore: restoredGoal.current_amount });
  const otherAfter = await checked(other.from('transactions').select().eq('id', otherTransaction.id).single());
  check('large restore leaves second account transaction unchanged', JSON.stringify(otherAfter) === JSON.stringify(otherTransaction));
  writeFileSync(join(outputDirectory, 'volume-evidence.json'), JSON.stringify({ expectedTotal, expectedSelected,
    fetchedExport: largeExport.transactions.length, savedBackup: largeDocument.data.transactions.length, restoredCount,
    expectedContributions, savedContributions: largeDocument.data.savingsContributions.length,
    savingsBefore: fullGoal.current_amount, savingsAfter: restoredGoal.current_amount }, null, 2));
  const deletable = await performCloudBackup(userId, 'manual', deps);
  const ownedCopies = await checked(client.storage.from('financial-backups').list(`${userId}/assets/${deletable.id}`));
  check('backup deletion fixture contains immutable attachment copies', !!ownedCopies?.length);
  await api.deleteBackup(deletable, dataClient);
  const deletedCopies = await checked(client.storage.from('financial-backups').list(`${userId}/assets/${deletable.id}`));
  const deletedRows = await checked(client.from('backups').select('id').eq('id', deletable.id));
  check('deleting backup removes every immutable copy and metadata row', !deletedCopies?.length && !deletedRows?.length);
  const stillUsableReportPath = (await deps.fetchBackupSourceData(userId)).reports.find(r => r.storage_path)?.storage_path;
  const stillUsableReport = stillUsableReportPath ? await client.storage.from('financial-reports').download(stillUsableReportPath) : { data: null, error: true };
  check('deleting backup preserves already restored financial attachments', !stillUsableReport.error && !!stillUsableReport.data);
}
