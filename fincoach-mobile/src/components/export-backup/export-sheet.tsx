import { MaterialIcons } from '@expo/vector-icons';
import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { validateExportSelection } from '@/lib/export-backup-domain';
import type { ExportContentType, ExportSelection } from '@/lib/types';

const contentOptions: { value: ExportContentType; label: string; icon: keyof typeof MaterialIcons.glyphMap }[] = [
  { value: 'transaction', label: 'Transactions', icon: 'receipt-long' },
  { value: 'budget', label: 'Budgets', icon: 'account-balance-wallet' },
  { value: 'savings', label: 'Savings', icon: 'savings' },
];

export function ExportSheet({
  visible,
  initialSelection,
  generating,
  onClose,
  onGenerate,
}: {
  visible: boolean;
  initialSelection: ExportSelection;
  generating: boolean;
  onClose: () => void;
  onGenerate: (selection: ExportSelection) => void;
}) {
  const [selection, setSelection] = useState(initialSelection);
  const [error, setError] = useState<string | null>(null);

  function toggleContent(content: ExportContentType) {
    setSelection((current) => ({
      ...current,
      contents: current.contents.includes(content)
        ? current.contents.filter((item) => item !== content)
        : [...current.contents, content],
    }));
  }

  function submit() {
    const message = validateExportSelection(selection);
    setError(message);
    if (!message) onGenerate(selection);
  }

  return (
    <Modal animationType="slide" transparent visible={visible} onRequestClose={onClose}>
      <View style={styles.scrim}>
        <Pressable accessibilityLabel="Close export options" onPress={onClose} style={StyleSheet.absoluteFill} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>Export financial data</Text>
              <Text style={styles.subtitle}>Choose the period and sections to include.</Text>
            </View>
            <Pressable accessibilityLabel="Close" hitSlop={8} onPress={onClose}>
              <MaterialIcons name="close" size={24} color={authColors.onSurfaceVariant} />
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            <Text style={styles.label}>FORMAT</Text>
            <View style={styles.segment}>
              {(['csv', 'pdf'] as const).map((format) => (
                <Pressable
                  key={format}
                  onPress={() => setSelection((current) => ({ ...current, format }))}
                  style={[styles.segmentButton, selection.format === format && styles.segmentActive]}>
                  <Text style={[styles.segmentText, selection.format === format && styles.segmentTextActive]}>
                    {format === 'csv' ? 'CSV spreadsheet' : 'PDF document'}
                  </Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.label}>DATE RANGE</Text>
            <View style={styles.dateRow}>
              <View style={styles.dateField}>
                <Text style={styles.fieldLabel}>From</Text>
                <TextInput
                  autoCapitalize="none"
                  keyboardType="numbers-and-punctuation"
                  onChangeText={(startDate) => setSelection((current) => ({ ...current, startDate }))}
                  placeholder="YYYY-MM-DD"
                  style={styles.input}
                  value={selection.startDate}
                />
              </View>
              <View style={styles.dateField}>
                <Text style={styles.fieldLabel}>To</Text>
                <TextInput
                  autoCapitalize="none"
                  keyboardType="numbers-and-punctuation"
                  onChangeText={(endDate) => setSelection((current) => ({ ...current, endDate }))}
                  placeholder="YYYY-MM-DD"
                  style={styles.input}
                  value={selection.endDate}
                />
              </View>
            </View>

            <Text style={styles.label}>INCLUDE</Text>
            <View style={styles.options}>
              {contentOptions.map((option) => (
                <View key={option.value} style={styles.optionRow}>
                  <MaterialIcons name={option.icon} size={21} color={authColors.primary} />
                  <Text style={styles.optionLabel}>{option.label}</Text>
                  <Switch
                    value={selection.contents.includes(option.value)}
                    onValueChange={() => toggleContent(option.value)}
                    trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }}
                    thumbColor="#ffffff"
                  />
                </View>
              ))}
            </View>
            {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          </ScrollView>

          <Pressable disabled={generating} onPress={submit} style={[styles.generate, generating && styles.disabled]}>
            <Text style={styles.generateText}>{generating ? 'Generating…' : `Generate ${selection.format.toUpperCase()}`}</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(20,20,30,0.38)' },
  sheet: { maxHeight: '90%', paddingHorizontal: 20, paddingTop: 10, paddingBottom: 24, borderTopLeftRadius: 28, borderTopRightRadius: 28, backgroundColor: authColors.surface },
  handle: { alignSelf: 'center', width: 42, height: 4, borderRadius: 2, backgroundColor: authColors.outlineVariant },
  header: { paddingTop: 17, paddingBottom: 12, flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  title: { fontFamily: authFont.bold, fontSize: 20, color: authColors.onSurface },
  subtitle: { marginTop: 3, fontFamily: authFont.regular, fontSize: 12, color: authColors.onSurfaceVariant },
  content: { gap: 12, paddingBottom: 14 },
  label: { marginTop: 7, fontFamily: authFont.bold, fontSize: 11, letterSpacing: 0.7, color: authColors.onSurfaceVariant },
  segment: { padding: 4, borderRadius: 14, flexDirection: 'row', backgroundColor: authColors.surfaceContainerHigh },
  segmentButton: { flex: 1, minHeight: 42, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  segmentActive: { backgroundColor: authColors.surfaceContainerLowest },
  segmentText: { fontFamily: authFont.semibold, fontSize: 13, color: authColors.onSurfaceVariant },
  segmentTextActive: { color: authColors.primary },
  dateRow: { flexDirection: 'row', gap: 10 },
  dateField: { flex: 1, gap: 5 },
  fieldLabel: { fontFamily: authFont.semibold, fontSize: 12, color: authColors.onSurfaceVariant },
  input: { minHeight: 46, paddingHorizontal: 12, borderRadius: 12, fontFamily: authFont.regular, fontSize: 14, color: authColors.onSurface, backgroundColor: authColors.surfaceContainerLowest, borderWidth: StyleSheet.hairlineWidth, borderColor: authColors.outlineVariant },
  options: { borderRadius: 16, overflow: 'hidden', backgroundColor: authColors.surfaceContainerLowest },
  optionRow: { minHeight: 54, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', gap: 11, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: authColors.outlineVariant },
  optionLabel: { flex: 1, fontFamily: authFont.regular, fontSize: 14, color: authColors.onSurface },
  error: { fontFamily: authFont.semibold, fontSize: 12, color: authColors.error },
  generate: { minHeight: 52, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary },
  generateText: { fontFamily: authFont.bold, fontSize: 15, color: authColors.onPrimary },
  disabled: { opacity: 0.55 },
});
