import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Switch, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ActionCard, formatBackupDate, SectionHeading } from '@/components/export-backup/export-backup-components';
import { ExportSheet } from '@/components/export-backup/export-sheet';
import { AppText as Text } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { performCloudBackup } from '@/lib/backup-orchestrator';
import {
  createDataExport,
  fetchBackups,
  fetchExportSourceData,
  reconcileStaleRecords,
  saveExportContents,
  updateAutoBackupEnabled,
  updateDataExport,
} from '@/lib/export-backup';
import { buildExportCsv, buildExportHtml, createExportFileName, createExportPreset } from '@/lib/export-backup-domain';
import { setCurrentExport, writeCsvExport, writePdfExport } from '@/lib/export-files';
import { useAuth } from '@/lib/auth-context';
import type { BackupRecord, ExportFormat, ExportSelection } from '@/lib/types';

function errorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? '');
  if (message.includes('schema cache') || message.includes('data_exports') || message.includes('backups')) {
    return 'Export & Backup database setup is not installed yet. Apply the module migration in Supabase, then retry.';
  }
  return message || 'The operation could not be completed.';
}

export default function ExportBackupScreen() {
  const insets = useSafeAreaInsets();
  const { profile, refreshProfile, session } = useAuth();
  const userId = session?.user.id;
  const preset = useMemo(() => createExportPreset('current_month'), []);
  const [sheetFormat, setSheetFormat] = useState<ExportFormat | null>(null);
  const [generating, setGenerating] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [autoBackup, setAutoBackup] = useState(profile?.auto_backup_enabled ?? true);
  const [backups, setBackups] = useState<BackupRecord[]>([]);

  const load = useCallback(async (refresh = false) => {
    if (!userId) return;
    if (refresh) setRefreshing(true);
    try {
      await reconcileStaleRecords(userId, new Date(Date.now() - 15 * 60 * 1000).toISOString());
      setBackups(await fetchBackups(userId, 20));
      setAutoBackup(profile?.auto_backup_enabled ?? true);
    } catch (error) {
      if (!refresh) console.warn('Export and backup history could not be loaded.', error);
    } finally {
      setRefreshing(false);
    }
  }, [profile, userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const initialSelection = useMemo<ExportSelection>(() => ({
    format: sheetFormat ?? 'csv',
    startDate: preset.startDate,
    endDate: preset.endDate,
    contents: ['transaction', 'budget', 'savings'],
  }), [preset.endDate, preset.startDate, sheetFormat]);
  const lastBackup = backups.find((backup) => backup.status === 'completed');

  async function generateExport(selection: ExportSelection) {
    if (!userId) return;
    setGenerating(true);
    let exportId: string | null = null;
    try {
      const fileName = createExportFileName(selection);
      const record = await createDataExport(userId, selection, fileName);
      exportId = record.id;
      await saveExportContents(record.id, selection.contents);
      await updateDataExport(record.id, userId, { status: 'processing' });
      const source = await fetchExportSourceData(userId, selection);
      const generated = selection.format === 'csv'
        ? writeCsvExport(fileName, buildExportCsv(source, selection))
        : await writePdfExport(buildExportHtml(source, selection));
      await updateDataExport(record.id, userId, {
        status: 'completed',
        file_size_bytes: generated.size,
        completed_at: new Date().toISOString(),
      });
      setCurrentExport({ ...generated, fileName, format: selection.format });
      setSheetFormat(null);
      router.push('/export-backup/success' as never);
    } catch (error) {
      if (exportId) await updateDataExport(exportId, userId, { status: 'failed' }).catch(() => undefined);
      appDialog.open('Export failed', errorMessage(error));
    } finally {
      setGenerating(false);
    }
  }

  async function createManualBackup() {
    if (!userId || backingUp) return;
    setBackingUp(true);
    try {
      await performCloudBackup(userId, 'manual');
      await load(true);
      appDialog.open('Backup completed', 'Your financial records and attached receipts, reports and category images were saved to your private cloud backup.');
    } catch (error) {
      appDialog.open('Backup failed', errorMessage(error));
    } finally {
      setBackingUp(false);
    }
  }

  async function changeAutoBackup(enabled: boolean) {
    if (!userId) return;
    const previous = autoBackup;
    setAutoBackup(enabled);
    try {
      await updateAutoBackupEnabled(userId, enabled);
      await refreshProfile();
    } catch (error) {
      setAutoBackup(previous);
      appDialog.open('Could not update preference', errorMessage(error));
    }
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityLabel="Go back" hitSlop={8} onPress={() => router.back()} style={styles.roundButton}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={styles.heading}>Export & Backup</Text>
        <View style={styles.roundButton} />
      </View>
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 30, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={authColors.primary} />}
        showsVerticalScrollIndicator={false}>
        <SectionHeading title="Export Data" description="Create PDF or CSV files from your financial records." />
        <ActionCard icon="table-view" title="Export as CSV" description="Open in spreadsheet apps or save to your device." onPress={() => setSheetFormat('csv')} />
        <ActionCard icon="picture-as-pdf" title="Export as PDF" description="Create a formatted document for sharing or printing." onPress={() => setSheetFormat('pdf')} />
        <SectionHeading title="Cloud Backup" description="Private backups are stored under your authenticated Supabase account." />
        <View style={styles.preferenceCard}>
          <View style={styles.preferenceIcon}><MaterialIcons name="cloud-sync" size={23} color={authColors.primary} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>Auto-backup to cloud</Text>
            <Text style={styles.cardDescription}>Checks for a daily backup when you sign in or reopen the app.</Text>
          </View>
          <Switch value={autoBackup} onValueChange={(enabled) => void changeAutoBackup(enabled)} trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }} thumbColor="#ffffff" />
        </View>
        <Text style={styles.lastBackup}>
          {lastBackup ? `Last backup: ${formatBackupDate(lastBackup.completed_at ?? lastBackup.created_at)}` : 'No completed cloud backup yet.'}
        </Text>
        <ActionCard icon="backup" title="Back up now" description="Create a full manual backup of your current FinCoach data." loading={backingUp} disabled={backingUp} onPress={() => void createManualBackup()} />
        <ActionCard icon="restore" title="Restore from backup" description="Review, restore, or delete your available cloud backups." onPress={() => router.push('/export-backup/restore' as never)} />
      </ScrollView>
      {sheetFormat ? (
        <ExportSheet
          key={sheetFormat}
          visible
          initialSelection={initialSelection}
          generating={generating}
          onClose={() => !generating && setSheetFormat(null)}
          onGenerate={(selection) => void generateExport(selection)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  preferenceCard: { minHeight: 88, padding: 14, borderRadius: 18, flexDirection: 'row', alignItems: 'center', gap: 13, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  preferenceIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  cardTitle: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  cardDescription: { marginTop: 3, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, color: authColors.onSurfaceVariant },
  lastBackup: { marginHorizontal: 4, fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant },
});
