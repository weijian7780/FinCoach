import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import { Linking, TextInput, View } from 'react-native';

import { AnimatedPressable } from '@/components/ui/animated-pressable';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { clarificationReply } from '@/lib/coach-agent';
import { createReportSignedUrl, fetchReportStoragePath } from '@/lib/reports';
import type {
  CoachActionPayload,
  CoachChoiceOption,
  CoachClarificationPayload,
  CoachReadClarificationPayload,
} from '@/lib/types';

export function CoachClarificationCard({
  disabled,
  onReply,
  payload,
}: {
  disabled: boolean;
  onReply: (reply: { content: string; value: string }) => void;
  // Accepts a write clarification or a read question — the card only reads the
  // shared question/input/options/allow_other fields, never write-only state.
  payload: CoachClarificationPayload | CoachReadClarificationPayload;
}) {
  const [otherVisible, setOtherVisible] = useState(payload.options.length === 0);
  const [otherText, setOtherText] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const selected = useMemo(
    () => payload.options.filter((option) => selectedIds.includes(option.id)),
    [payload.options, selectedIds],
  );
  const isMulti = payload.input_type === 'multi_select';

  const choose = (option: CoachChoiceOption) => {
    if (disabled) return;
    if (option.value === 'pick_date') {
      setOtherVisible(true);
      return;
    }
    if (!isMulti) {
      const reply = clarificationReply(option);
      if (reply) onReply(reply);
      return;
    }
    setSelectedIds((current) => (
      current.includes(option.id)
        ? current.filter((id) => id !== option.id)
        : [...current, option.id]
    ));
  };

  const submit = () => {
    const flexible = clarificationReply(null, otherText);
    const content = [
      ...selected.map((option) => option.label),
      ...(flexible ? [flexible.content] : []),
    ].join(', ');
    const value = [
      ...selected.map((option) => option.value),
      ...(flexible ? [flexible.value] : []),
    ].join(',');
    if (content && value) onReply({ content, value });
  };

  return (
    <View style={styles.card}>
      <View style={styles.cardHeading}>
        <View style={styles.iconShell}>
          <MaterialCommunityIcons name="tune-variant" size={17} color={authColors.primary} />
        </View>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>ONE DETAIL NEEDED</Text>
          <Text selectable style={styles.title}>{payload.question}</Text>
        </View>
      </View>

      {payload.options.length > 0 ? (
        <View style={styles.optionWrap}>
          {payload.options.map((option) => {
            const isSelected = selectedIds.includes(option.id);
            return (
              <AnimatedPressable
                accessibilityRole={isMulti ? 'checkbox' : 'button'}
                accessibilityState={{ checked: isMulti ? isSelected : undefined }}
                disabled={disabled}
                key={option.id}
                onPress={() => choose(option)}
                style={[styles.option, isSelected ? styles.optionSelected : null]}>
                {isMulti ? (
                  <MaterialCommunityIcons
                    name={isSelected ? 'checkbox-marked' : 'checkbox-blank-outline'}
                    size={18}
                    color={isSelected ? authColors.primary : authColors.onSurfaceVariant}
                  />
                ) : null}
                <Text style={[styles.optionText, isSelected ? styles.optionTextSelected : null]}>
                  {option.label}
                </Text>
              </AnimatedPressable>
            );
          })}
          {payload.allow_other ? (
            <AnimatedPressable
              accessibilityRole="button"
              accessibilityState={{ expanded: otherVisible }}
              disabled={disabled}
              onPress={() => setOtherVisible((current) => !current)}
              style={[styles.option, otherVisible ? styles.optionSelected : null]}>
              <MaterialCommunityIcons name="message-text-outline" size={17} color={authColors.primary} />
              <Text style={[styles.optionText, otherVisible ? styles.optionTextSelected : null]}>
                Other
              </Text>
            </AnimatedPressable>
          ) : null}
        </View>
      ) : null}

      {otherVisible ? (
        <View style={styles.otherSection}>
          <TextInput
            accessibilityLabel="Tell FinCoach in your own words"
            editable={!disabled}
            maxLength={300}
            multiline
            onChangeText={setOtherText}
            placeholder="Tell FinCoach in your own words"
            placeholderTextColor={authColors.outline}
            style={styles.otherInput}
            value={otherText}
          />
          <AnimatedPressable
            accessibilityRole="button"
            disabled={disabled || (!otherText.trim() && selected.length === 0)}
            onPress={submit}
            style={[
              styles.primaryButton,
              disabled || (!otherText.trim() && selected.length === 0)
                ? styles.disabled
                : null,
            ]}>
            <Text style={styles.primaryButtonText}>Send answer</Text>
            <MaterialCommunityIcons name="arrow-up" size={17} color={authColors.onPrimary} />
          </AnimatedPressable>
        </View>
      ) : isMulti ? (
        <AnimatedPressable
          accessibilityRole="button"
          disabled={disabled || selected.length === 0}
          onPress={submit}
          style={[
            styles.primaryButton,
            disabled || selected.length === 0 ? styles.disabled : null,
          ]}>
          <Text style={styles.primaryButtonText}>Continue</Text>
          <MaterialCommunityIcons name="arrow-right" size={17} color={authColors.onPrimary} />
        </AnimatedPressable>
      ) : null}
      <Text style={styles.flexibleHint}>You can also ignore these choices and type your answer below.</Text>
    </View>
  );
}

export function CoachActionCard({
  busy,
  onCancel,
  onChange,
  onConfirm,
  payload,
}: {
  busy: boolean;
  onCancel: () => void;
  onChange: () => void;
  onConfirm: () => void;
  payload: CoachActionPayload;
}) {
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const isPending = payload.status === 'pending';
  const canRun = isPending || (
    (payload.status === 'approved' || payload.status === 'failed')
    && payload.action_type === 'generate_report'
  );

  // The generated PDF lives in a private bucket and its local copy is deleted after
  // upload, so opening it always needs a fresh short-lived signed URL.
  const reportResult = payload.status === 'executed' && payload.action_type === 'generate_report'
    ? payload.result ?? {}
    : null;
  const storedPath = typeof reportResult?.storage_path === 'string'
    ? reportResult.storage_path
    : null;
  const storedReportId = typeof reportResult?.report_id === 'number'
    ? reportResult.report_id
    : null;
  const canOpenReport = Boolean(storedPath) || storedReportId !== null;

  const openReport = async () => {
    if (opening || !canOpenReport) return;
    setOpening(true);
    setOpenError(null);
    try {
      const path = storedPath ?? await fetchReportStoragePath(storedReportId as number);
      const signedUrl = await createReportSignedUrl(path);
      await Linking.openURL(signedUrl);
    } catch (error) {
      setOpenError(
        error instanceof Error ? error.message : 'The report PDF could not be opened.',
      );
    } finally {
      setOpening(false);
    }
  };
  const statusCopy = payload.status === 'executed'
    ? payload.action_type === 'create_reminder'
      ? 'Reminder created'
      : 'Report generated'
    : payload.status === 'cancelled'
      ? 'Cancelled'
      : payload.status === 'approved'
        ? busy
          ? 'Generating report…'
          : 'Approved — ready to finish'
        : payload.status === 'failed'
          ? 'Action failed'
          : null;

  return (
    <View style={[styles.card, styles.actionCard]}>
      <View style={styles.cardHeading}>
        <View style={styles.iconShell}>
          <MaterialCommunityIcons
            name={payload.action_type === 'create_reminder' ? 'bell-outline' : 'file-chart-outline'}
            size={18}
            color={authColors.primary}
          />
        </View>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>REVIEW BEFORE FINCOACH ACTS</Text>
          <Text selectable style={styles.title}>{payload.title}</Text>
          <Text selectable style={styles.description}>{payload.description}</Text>
        </View>
      </View>

      <View style={styles.fields}>
        {payload.fields.map((field) => (
          <View key={`${field.label}-${field.value}`} style={styles.fieldRow}>
            <Text style={styles.fieldLabel}>{field.label}</Text>
            <Text selectable style={styles.fieldValue}>{field.value}</Text>
          </View>
        ))}
      </View>

      {statusCopy ? (
        <View style={styles.statusRow}>
          <MaterialCommunityIcons
            name={payload.status === 'failed' ? 'alert-circle-outline' : 'check-circle-outline'}
            size={18}
            color={payload.status === 'failed' ? authColors.error : authColors.primary}
          />
          <Text style={[
            styles.statusText,
            payload.status === 'failed' ? { color: authColors.error } : null,
          ]}>
            {statusCopy}
          </Text>
        </View>
      ) : null}

      {canOpenReport ? (
        <View style={styles.openSection}>
          <AnimatedPressable
            accessibilityRole="button"
            accessibilityLabel="Open the generated report PDF"
            disabled={opening}
            onPress={openReport}
            style={[styles.primaryButton, styles.actionPrimary, opening ? styles.disabled : null]}>
            <MaterialCommunityIcons
              name="file-pdf-box"
              size={18}
              color={authColors.onPrimary}
            />
            <Text style={styles.primaryButtonText}>
              {opening ? 'Opening PDF…' : 'Open PDF'}
            </Text>
          </AnimatedPressable>
          {openError ? <Text style={styles.openError}>{openError}</Text> : null}
        </View>
      ) : null}

      {canRun ? (
        <View style={styles.actionButtons}>
          <AnimatedPressable
            accessibilityRole="button"
            disabled={busy}
            onPress={onConfirm}
            style={[styles.primaryButton, styles.actionPrimary, busy ? styles.disabled : null]}>
            <MaterialCommunityIcons name="check" size={18} color={authColors.onPrimary} />
            <Text style={styles.primaryButtonText}>
              {isPending
                ? payload.confirm_label
                : payload.status === 'failed'
                  ? 'Retry generation'
                  : 'Resume generation'}
            </Text>
          </AnimatedPressable>
          <View style={styles.secondaryActions}>
            <AnimatedPressable
              accessibilityRole="button"
              disabled={busy}
              onPress={onChange}
              style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>Change details</Text>
            </AnimatedPressable>
            <AnimatedPressable
              accessibilityRole="button"
              disabled={busy}
              onPress={onCancel}
              style={styles.secondaryButton}>
              <Text style={styles.cancelText}>Cancel</Text>
            </AnimatedPressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = {
  card: {
    marginLeft: 36,
    marginTop: 7,
    gap: 12,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: authColors.primaryFixedDim,
    padding: 14,
    backgroundColor: authColors.surfaceContainerLowest,
  } as const,
  actionCard: { gap: 14 } as const,
  cardHeading: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 } as const,
  iconShell: {
    width: 34,
    height: 34,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: authColors.primaryFixed,
  } as const,
  headingCopy: { flex: 1, gap: 3 } as const,
  eyebrow: {
    color: authColors.primary,
    fontFamily: authFont.bold,
    fontSize: 9,
    lineHeight: 13,
    letterSpacing: 0.6,
  } as const,
  title: { color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 15, lineHeight: 20 } as const,
  description: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17 } as const,
  optionWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 } as const,
  option: {
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: authColors.outlineVariant,
    paddingHorizontal: 12,
    backgroundColor: authColors.surfaceContainerLow,
  } as const,
  optionSelected: { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed } as const,
  optionText: { color: authColors.onSurfaceVariant, fontFamily: authFont.semibold, fontSize: 12, lineHeight: 16 } as const,
  optionTextSelected: { color: authColors.primary } as const,
  otherSection: { gap: 9 } as const,
  otherInput: {
    minHeight: 78,
    maxHeight: 130,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: authColors.outlineVariant,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: authColors.onSurface,
    fontFamily: authFont.regular,
    fontSize: 14,
    textAlignVertical: 'top',
    backgroundColor: authColors.surfaceContainerLow,
  } as const,
  primaryButton: {
    minHeight: 44,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    borderRadius: 14,
    paddingHorizontal: 14,
    backgroundColor: authColors.primary,
  } as const,
  primaryButtonText: { color: authColors.onPrimary, fontFamily: authFont.bold, fontSize: 12, lineHeight: 16 } as const,
  disabled: { opacity: 0.45 } as const,
  flexibleHint: { color: authColors.outline, fontFamily: authFont.regular, fontSize: 10, lineHeight: 14 } as const,
  fields: { overflow: 'hidden', borderRadius: 14, backgroundColor: authColors.surfaceContainerLow } as const,
  fieldRow: {
    minHeight: 43,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: authColors.outlineVariant,
  } as const,
  fieldLabel: { color: authColors.onSurfaceVariant, fontFamily: authFont.semibold, fontSize: 11, lineHeight: 15 } as const,
  fieldValue: { flex: 1, textAlign: 'right', color: authColors.onSurface, fontFamily: authFont.bold, fontSize: 12, lineHeight: 16 } as const,
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 7 } as const,
  statusText: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 12, lineHeight: 16 } as const,
  openSection: { gap: 7 } as const,
  openError: { color: authColors.error, fontFamily: authFont.regular, fontSize: 11, lineHeight: 15 } as const,
  actionButtons: { gap: 8 } as const,
  actionPrimary: { alignSelf: 'stretch' } as const,
  secondaryActions: { flexDirection: 'row', gap: 8 } as const,
  secondaryButton: {
    minHeight: 42,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: authColors.outlineVariant,
    paddingHorizontal: 10,
  } as const,
  secondaryButtonText: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 11, lineHeight: 15 } as const,
  cancelText: { color: authColors.onSurfaceVariant, fontFamily: authFont.bold, fontSize: 11, lineHeight: 15 } as const,
} as const;
