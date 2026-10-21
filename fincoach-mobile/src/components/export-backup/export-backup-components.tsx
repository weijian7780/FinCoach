import { MaterialIcons } from '@expo/vector-icons';
import type { ComponentProps, ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import type { BackupRecord } from '@/lib/types';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

export function SectionHeading({ title, description }: { title: string; description?: string }) {
  return (
    <View style={styles.sectionHeading}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {description ? <Text style={styles.sectionDescription}>{description}</Text> : null}
    </View>
  );
}

export function ActionCard({
  icon,
  title,
  description,
  onPress,
  disabled,
  loading,
  trailing,
}: {
  icon: IconName;
  title: string;
  description?: string;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  trailing?: ReactNode;
}) {
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      disabled={disabled || !onPress}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && !disabled ? styles.pressed : null, disabled ? styles.disabled : null]}>
      <View style={styles.icon}>
        {loading ? <ActivityIndicator color={authColors.primary} /> : <MaterialIcons name={icon} size={23} color={authColors.primary} />}
      </View>
      <View style={styles.cardCopy}>
        <Text style={styles.cardTitle}>{title}</Text>
        {description ? <Text style={styles.cardDescription}>{description}</Text> : null}
      </View>
      {trailing ?? (onPress ? <MaterialIcons name="chevron-right" size={23} color={authColors.onSurfaceVariant} /> : null)}
    </Pressable>
  );
}

export function formatBackupSize(bytes: number | null) {
  if (bytes === null) return 'Size unavailable';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatBackupDate(value: string) {
  return new Intl.DateTimeFormat('en-MY', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

export function BackupCard({
  backup,
  selected,
  onSelect,
  onDelete,
}: {
  backup: BackupRecord;
  selected?: boolean;
  onSelect?: () => void;
  onDelete?: () => void;
}) {
  return (
    <Pressable
      accessibilityRole={onSelect ? 'radio' : undefined}
      accessibilityState={onSelect ? { selected: Boolean(selected) } : undefined}
      onPress={onSelect}
      style={[styles.backupCard, selected ? styles.selectedCard : null]}>
      <View style={[styles.icon, selected ? styles.selectedIcon : null]}>
        <MaterialIcons name={backup.backup_type === 'automatic' ? 'cloud-done' : 'cloud-upload'} size={22} color={authColors.primary} />
      </View>
      <View style={styles.cardCopy}>
        <Text numberOfLines={1} style={styles.cardTitle}>{backup.file_name}</Text>
        <Text style={styles.cardDescription}>
          {formatBackupDate(backup.completed_at ?? backup.created_at)} · {formatBackupSize(backup.file_size_bytes)}
        </Text>
        <Text style={styles.typeLabel}>{backup.backup_type === 'automatic' ? 'Automatic' : 'Manual'} backup</Text>
        <Text style={styles.cardDescription}>{backup.schema_version >= 2 ? `${backup.attachment_count ?? 0} saved attachments` : 'Legacy backup · files not included'}</Text>
        {backup.cleanup_warning ? <Text style={styles.cardDescription}>{backup.cleanup_warning}</Text> : null}
      </View>
      {onDelete ? (
        <Pressable accessibilityLabel={`Delete ${backup.file_name}`} hitSlop={8} onPress={onDelete} style={styles.deleteButton}>
          <MaterialIcons name="delete-outline" size={22} color={authColors.error} />
        </Pressable>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  sectionHeading: { gap: 3, marginTop: 8 },
  sectionTitle: { fontFamily: authFont.bold, fontSize: 18, color: authColors.onSurface },
  sectionDescription: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 19, color: authColors.onSurfaceVariant },
  card: { minHeight: 78, padding: 14, borderRadius: 18, flexDirection: 'row', alignItems: 'center', gap: 13, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  pressed: { opacity: 0.82 },
  disabled: { opacity: 0.55 },
  icon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed },
  selectedIcon: { backgroundColor: '#E2E4FF' },
  cardCopy: { flex: 1, gap: 3 },
  cardTitle: { fontFamily: authFont.semibold, fontSize: 15, color: authColors.onSurface },
  cardDescription: { fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, color: authColors.onSurfaceVariant },
  typeLabel: { fontFamily: authFont.semibold, fontSize: 11, color: authColors.primary },
  backupCard: { padding: 14, borderRadius: 18, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  selectedCard: { borderWidth: 1.5, borderColor: authColors.primary, backgroundColor: '#F7F7FF' },
  deleteButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
});
