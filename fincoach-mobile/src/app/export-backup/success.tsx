import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { formatBackupSize } from '@/components/export-backup/export-backup-components';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { clearCurrentExport, getCurrentExport, shareExportFile } from '@/lib/export-files';

export default function ExportSuccessScreen() {
  const insets = useSafeAreaInsets();
  const file = getCurrentExport();
  const [sharing, setSharing] = useState(false);

  async function share() {
    if (!file || sharing) return;
    setSharing(true);
    try {
      await shareExportFile(file);
    } catch (error) {
      Alert.alert('Could not share export', error instanceof Error ? error.message : 'Sharing failed.');
    } finally {
      setSharing(false);
    }
  }

  function done() {
    clearCurrentExport();
    router.replace('/export-backup' as never);
  }

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 30, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.successIcon}><MaterialIcons name="check-circle" size={54} color={authColors.primary} /></View>
      <Text style={styles.title}>Export Ready</Text>
      <Text style={styles.subtitle}>{file ? 'Your financial export was generated on this device.' : 'The previous temporary export is no longer available.'}</Text>
      {file ? (
        <View style={styles.fileCard}>
          <View style={styles.fileIcon}><MaterialIcons name={file.format === 'pdf' ? 'picture-as-pdf' : 'table-view'} size={28} color={authColors.primary} /></View>
          <View style={{ flex: 1 }}>
            <Text numberOfLines={2} style={styles.fileName}>{file.fileName}</Text>
            <Text style={styles.fileMeta}>{file.format.toUpperCase()} · {formatBackupSize(file.size)}</Text>
          </View>
        </View>
      ) : null}
      <View style={styles.actions}>
        {file ? (
          <Pressable disabled={sharing} onPress={() => void share()} style={[styles.primaryButton, sharing && styles.disabled]}>
            <MaterialIcons name="share" size={20} color={authColors.onPrimary} />
            <Text style={styles.primaryText}>{sharing ? 'Opening share options…' : 'Share or save file'}</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={done} style={styles.secondaryButton}><Text style={styles.secondaryText}>{file ? 'Done' : 'Back to Export & Backup'}</Text></Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingHorizontal: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surface },
  successIcon: { width: 92, height: 92, borderRadius: 46, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  title: { marginTop: 22, fontFamily: authFont.bold, fontSize: 27, color: authColors.onSurface },
  subtitle: { marginTop: 8, maxWidth: 310, fontFamily: authFont.regular, fontSize: 14, lineHeight: 21, textAlign: 'center', color: authColors.onSurfaceVariant },
  fileCard: { width: '100%', marginTop: 28, padding: 17, borderRadius: 20, flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  fileIcon: { width: 52, height: 52, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  fileName: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  fileMeta: { marginTop: 4, fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant },
  actions: { width: '100%', marginTop: 28, gap: 11 },
  primaryButton: { minHeight: 52, borderRadius: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, backgroundColor: authColors.primary },
  primaryText: { fontFamily: authFont.bold, fontSize: 15, color: authColors.onPrimary },
  secondaryButton: { minHeight: 50, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: authColors.outlineVariant },
  secondaryText: { fontFamily: authFont.semibold, fontSize: 14, color: authColors.primary },
  disabled: { opacity: 0.55 },
});
