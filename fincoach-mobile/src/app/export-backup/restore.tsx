import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BackupCard } from '@/components/export-backup/export-backup-components';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { downloadAndValidateBackup } from '@/lib/backup-orchestrator';
import { deleteBackup, downloadBackupObject, fetchBackups, restoreFinancialBackup, updateBackupRecord } from '@/lib/export-backup';
import { useAuth } from '@/lib/auth-context';
import type { BackupRecord } from '@/lib/types';

export default function RestoreBackupScreen() {
  const insets = useSafeAreaInsets();
  const { refreshProfile, session } = useAuth();
  const userId = session?.user.id;
  const [backups, setBackups] = useState<BackupRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const load = useCallback(async (refresh = false) => {
    if (!userId) return;
    if (refresh) setRefreshing(true);
    else setLoading(true);
    try {
      const records = (await fetchBackups(userId, 100)).filter((record) => record.status === 'completed' && Boolean(record.storage_path));
      setBackups(records);
      setSelectedId((current) => records.some((record) => record.id === current) ? current : records[0]?.id ?? null);
    } catch (error) {
      Alert.alert('Could not load backups', error instanceof Error ? error.message : 'Check your connection and retry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  function confirmRestore() {
    const selected = backups.find((backup) => backup.id === selectedId);
    if (!selected || !userId) return;
    Alert.alert(
      'Replace current financial data?',
      'Restoring will replace your current data with the selected backup. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Restore backup', style: 'destructive', onPress: () => void executeRestore(selected) },
      ],
    );
  }

  async function executeRestore(selected: BackupRecord) {
    if (!userId || restoring || !selected.storage_path) return;
    setRestoring(true);
    try {
      const blob = await downloadBackupObject(selected.storage_path);
      const document = await downloadAndValidateBackup(selected, userId, undefined, blob);
      await updateBackupRecord(selected.id, userId, { last_restore_status: 'processing' });
      await restoreFinancialBackup(selected.id, document);
      await refreshProfile();
      await load(true);
      Alert.alert('Restore completed', 'Your FinCoach financial data was restored successfully.', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (error) {
      await updateBackupRecord(selected.id, userId, { last_restore_status: 'failed' }).catch(() => undefined);
      Alert.alert('Restore blocked', error instanceof Error ? error.message : 'The backup could not be restored.');
    } finally {
      setRestoring(false);
    }
  }

  function confirmDelete(record: BackupRecord) {
    Alert.alert('Delete cloud backup?', 'This permanently deletes the selected backup file and its history record.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteBackup(record);
            await load(true);
          } catch (error) {
            Alert.alert('Delete failed', error instanceof Error ? error.message : 'The backup could not be deleted.');
          }
        },
      },
    ]);
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityLabel="Go back" hitSlop={8} onPress={() => router.back()} style={styles.roundButton}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={styles.heading}>Restore from backup</Text>
        <View style={styles.roundButton} />
      </View>
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 110, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={authColors.primary} />}>
        <View style={styles.warning}>
          <MaterialIcons name="warning-amber" size={23} color="#8A4B00" />
          <Text style={styles.warningText}>Restoring will replace your current data with the selected backup.</Text>
        </View>
        <Text style={styles.sectionTitle}>Available backups</Text>
        {loading ? (
          <View style={styles.state}><ActivityIndicator color={authColors.primary} /><Text style={styles.stateText}>Loading private cloud backups…</Text></View>
        ) : backups.length === 0 ? (
          <View style={styles.state}>
            <MaterialIcons name="cloud-off" size={30} color={authColors.onSurfaceVariant} />
            <Text style={styles.stateTitle}>No completed backups</Text>
            <Text style={styles.stateText}>Create a manual backup first, or leave automatic backup enabled.</Text>
          </View>
        ) : backups.map((backup) => (
          <BackupCard key={backup.id} backup={backup} selected={backup.id === selectedId} onSelect={() => setSelectedId(backup.id)} onDelete={() => confirmDelete(backup)} />
        ))}
      </ScrollView>
      <View style={[styles.bottomBar, { paddingBottom: insets.bottom + 14 }]}>
        <Pressable disabled={!selectedId || restoring} onPress={confirmRestore} style={[styles.restoreButton, (!selectedId || restoring) && styles.disabled]}>
          {restoring ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="restore" size={21} color={authColors.onPrimary} />}
          <Text style={styles.restoreText}>{restoring ? 'Verifying and restoring…' : 'Restore selected backup'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: authColors.surface },
  topBar: { minHeight: 64, paddingHorizontal: 20, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  roundButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  heading: { fontFamily: authFont.semibold, fontSize: 18, color: authColors.onSurface },
  warning: { padding: 15, borderRadius: 17, flexDirection: 'row', alignItems: 'flex-start', gap: 10, backgroundColor: '#FFF3E0', borderWidth: StyleSheet.hairlineWidth, borderColor: '#F2C078' },
  warningText: { flex: 1, fontFamily: authFont.semibold, fontSize: 13, lineHeight: 19, color: '#6C3B00' },
  sectionTitle: { marginTop: 8, fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface },
  state: { padding: 28, borderRadius: 20, alignItems: 'center', gap: 9, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  stateTitle: { fontFamily: authFont.semibold, fontSize: 16, color: authColors.onSurface },
  stateText: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, textAlign: 'center', color: authColors.onSurfaceVariant },
  bottomBar: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: 20, paddingTop: 12, backgroundColor: authColors.surface, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: authColors.outlineVariant },
  restoreButton: { minHeight: 52, borderRadius: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, backgroundColor: authColors.primary },
  restoreText: { fontFamily: authFont.bold, fontSize: 15, color: authColors.onPrimary },
  disabled: { opacity: 0.5 },
});
