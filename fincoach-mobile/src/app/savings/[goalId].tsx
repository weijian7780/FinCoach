import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DateField } from '@/components/savings/date-field';
import { ProgressRing } from '@/components/savings/progress-ring';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { emitSavingsMilestonesAfterContribution } from '@/lib/alert-events';
import { useAuth } from '@/lib/auth-context';
import {
  addSavingsContribution,
  deleteSavingsContribution,
  deleteSavingsGoal,
  fetchSavingsContributions,
  fetchSavingsGoal,
} from '@/lib/savings';
import {
  formatGoalDate,
  formatMoney,
  getGoalStatus,
  getSavingsMetrics,
  getSavingsSuggestion,
  parseMoney,
  todayIsoDate,
  type ContributionInput,
  type FieldErrors,
  validateContributionInput,
} from '@/lib/savings-domain';
import type { SavingsContribution, SavingsGoal } from '@/lib/types';

export default function SavingsGoalDetailScreen() {
  const insets = useSafeAreaInsets();
  const { goalId: goalIdParam } = useLocalSearchParams<{ goalId: string }>();
  const goalId = goalIdParam?.trim() ?? '';
  const { session } = useAuth();
  const userId = session?.user.id;
  const today = todayIsoDate();

  const [goal, setGoal] = useState<SavingsGoal | null>(null);
  const [contributions, setContributions] = useState<SavingsContribution[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showContributionForm, setShowContributionForm] = useState(false);
  const [amount, setAmount] = useState('');
  const [contributedOn, setContributedOn] = useState(today);
  const [note, setNote] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<ContributionInput>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId || !goalId) {
      setError('Savings goal not found.');
      setLoading(false);
      return;
    }
    setError(null);
    try {
      const [nextGoal, nextContributions] = await Promise.all([
        fetchSavingsGoal(goalId, userId),
        fetchSavingsContributions(goalId),
      ]);
      if (!nextGoal) throw new Error('Savings goal not found.');
      setGoal(nextGoal);
      setContributions(nextContributions);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load this savings goal.');
    } finally {
      setLoading(false);
    }
  }, [goalId, userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  async function syncSavingsMilestones(savedGoal: SavingsGoal, previousAmount: number, currentAmount: number) {
    try {
      await emitSavingsMilestonesAfterContribution(userId!, savedGoal, previousAmount, currentAmount);
      await load();
    } catch {
      appDialog.open(
        'Contribution saved',
        'Your savings total is safe, but its milestone alert could not synchronize. Retry the alert sync now?',
        [
          { text: 'Continue', onPress: () => void load() },
          { text: 'Retry sync', onPress: () => void syncSavingsMilestones(savedGoal, previousAmount, currentAmount) },
        ],
      );
    }
  }

  async function addContribution() {
    if (!goal) return;
    const metrics = getSavingsMetrics(goal.current_amount, goal.target_amount);
    const input = { amount, contributedOn, note };
    const errors = validateContributionInput(input, { today, remainingAmount: metrics.remainingAmount });
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    const parsedAmount = parseMoney(amount);
    if (parsedAmount == null) return;

    setBusy(true);
    setError(null);
    try {
      const previousAmount = goal.current_amount;
      await addSavingsContribution(goal.id, { amount: parsedAmount, contributed_on: contributedOn, note });
      setAmount('');
      setNote('');
      setContributedOn(today);
      setShowContributionForm(false);
      await syncSavingsMilestones(goal, previousAmount, previousAmount + parsedAmount);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not add this contribution.');
    } finally {
      setBusy(false);
    }
  }

  function confirmDeleteGoal() {
    if (!goal || !userId) return;
    appDialog.open('Delete savings goal?', 'The goal and its full contribution history will be permanently removed.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          setBusy(true);
          deleteSavingsGoal(goal.id, userId)
            .then(() => router.replace('/savings'))
            .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not delete this goal.'))
            .finally(() => setBusy(false));
        },
      },
    ]);
  }

  function confirmDeleteContribution(contribution: SavingsContribution) {
    appDialog.open('Delete contribution?', `${formatMoney(contribution.amount)} will be removed from this goal.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => {
          setBusy(true);
          deleteSavingsContribution(contribution.id)
            .then(load)
            .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not delete this contribution.'))
            .finally(() => setBusy(false));
        },
      },
    ]);
  }

  if (loading) {
    return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surface }}><ActivityIndicator color={authColors.primary} /></View>;
  }

  if (!goal) {
    return (
      <View style={{ flex: 1, paddingTop: insets.top + 20, paddingHorizontal: 20, alignItems: 'center', justifyContent: 'center', gap: 12, backgroundColor: authColors.surface }}>
        <MaterialIcons name="error-outline" size={40} color={authColors.error} />
        <Text style={{ textAlign: 'center', fontSize: 15, fontFamily: authFont.semibold, color: authColors.onSurface }}>{error ?? 'Savings goal not found.'}</Text>
        <Pressable accessibilityRole="button" onPress={() => router.replace('/savings')} style={secondaryButtonStyle}><Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>Back to goals</Text></Pressable>
      </View>
    );
  }

  const metrics = getSavingsMetrics(goal.current_amount, goal.target_amount);
  const status = getGoalStatus({ currentAmount: goal.current_amount, targetAmount: goal.target_amount, createdAt: goal.created_at, deadline: goal.deadline }, today);
  const suggestion = getSavingsSuggestion({ currentAmount: goal.current_amount, targetAmount: goal.target_amount, deadline: goal.deadline }, today);
  const reached = metrics.remainingAmount === 0;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable accessibilityLabel="Go back" accessibilityRole="button" hitSlop={10} onPress={() => router.back()}><MaterialIcons name="arrow-back" size={25} color={authColors.onSurface} /></Pressable>
        <Text numberOfLines={1} style={{ flex: 1, fontSize: 20, fontFamily: authFont.bold, color: authColors.onSurface }}>{goal.name}</Text>
        <Pressable accessibilityLabel="Edit savings goal" accessibilityRole="button" hitSlop={10} onPress={() => router.push({ pathname: '/savings/manage', params: { goalId: String(goal.id) } })}><MaterialIcons name="edit" size={23} color={authColors.primary} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 6, paddingBottom: insets.bottom + 32, gap: 16 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={summaryCardStyle}>
          <ProgressRing color={status.color} progress={metrics.ratio} size={162} strokeWidth={12}>
            <Text style={{ fontSize: 20, fontFamily: authFont.bold, color: status.color }}>{metrics.percentage}%</Text>
            <Text style={{ marginTop: 2, fontSize: 21, fontFamily: authFont.bold, color: authColors.onSurface }}>{formatMoney(metrics.currentAmount)}</Text>
            <Text style={{ fontSize: 12, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>of {formatMoney(metrics.targetAmount)}</Text>
          </ProgressRing>
          <Text style={{ fontSize: 15, fontFamily: authFont.bold, color: status.color }}>{status.label}</Text>
          <View style={{ width: '100%', flexDirection: 'row', gap: 10 }}>
            <View style={metricTileStyle}><Text style={metricLabelStyle}>REMAINING</Text><Text style={metricValueStyle}>{formatMoney(metrics.remainingAmount)}</Text></View>
            <View style={metricTileStyle}><Text style={metricLabelStyle}>DEADLINE</Text><Text style={metricValueStyle}>{formatGoalDate(goal.deadline)}</Text></View>
          </View>
        </View>

        <View style={suggestionCardStyle}>
          <View style={suggestionIconStyle}><MaterialIcons name="lightbulb" size={22} color={authColors.primary} /></View>
          <View style={{ flex: 1 }}><Text style={{ fontSize: 13, fontFamily: authFont.bold, color: authColors.primary }}>FINCOACH SAVING SUGGESTION</Text><Text style={{ marginTop: 5, fontSize: 14, lineHeight: 20, fontFamily: authFont.regular, color: authColors.onSurface }}>{suggestion}</Text></View>
        </View>

        {!reached ? (
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => setShowContributionForm((visible) => !visible)} style={primaryButtonStyle}>
            <MaterialIcons name={showContributionForm ? 'close' : 'add'} size={20} color={authColors.onPrimary} />
            <Text style={{ fontSize: 15, fontFamily: authFont.semibold, color: authColors.onPrimary }}>{showContributionForm ? 'Close contribution form' : 'Add contribution'}</Text>
          </Pressable>
        ) : null}

        {showContributionForm && !reached ? (
          <View style={formCardStyle}>
            <Text style={{ fontSize: 17, fontFamily: authFont.bold, color: authColors.onSurface }}>Record contribution</Text>
            <View style={{ gap: 7 }}><Text style={labelStyle}>Amount</Text><View style={{ position: 'relative', justifyContent: 'center' }}><Text style={currencyPrefixStyle}>RM</Text><TextInput accessibilityLabel="Contribution amount in Ringgit Malaysia" keyboardType="decimal-pad" onChangeText={(value) => { setAmount(value.replace(/[^0-9.]/g, '')); setFieldErrors((previous) => ({ ...previous, amount: undefined })); }} placeholder="50.00" placeholderTextColor={authColors.outline} style={[fieldStyle, { paddingLeft: 48 }, fieldErrors.amount && errorFieldStyle]} value={amount} /></View>{fieldErrors.amount ? <Text style={errorTextStyle}>{fieldErrors.amount}</Text> : null}</View>
            <DateField error={fieldErrors.contributedOn} label="Contribution date" maximumDate={today} onChange={(value) => { setContributedOn(value); setFieldErrors((previous) => ({ ...previous, contributedOn: undefined })); }} value={contributedOn} />
            <View style={{ gap: 7 }}><Text style={labelStyle}>Note (optional)</Text><TextInput accessibilityLabel="Contribution note" maxLength={200} multiline onChangeText={(value) => { setNote(value); setFieldErrors((previous) => ({ ...previous, note: undefined })); }} placeholder="e.g. Part-time pay" placeholderTextColor={authColors.outline} style={[fieldStyle, { minHeight: 82, textAlignVertical: 'top' }, fieldErrors.note && errorFieldStyle]} value={note} />{fieldErrors.note ? <Text style={errorTextStyle}>{fieldErrors.note}</Text> : null}</View>
            <Pressable accessibilityRole="button" disabled={busy} onPress={() => void addContribution()} style={({ pressed }) => [primaryButtonStyle, (pressed || busy) && { opacity: 0.82 }]}>{busy ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="check" size={20} color={authColors.onPrimary} />}<Text style={{ fontSize: 15, fontFamily: authFont.semibold, color: authColors.onPrimary }}>{busy ? 'Saving…' : 'Save contribution'}</Text></Pressable>
          </View>
        ) : null}

        {error ? <Text style={[errorTextStyle, { fontSize: 14 }]}>{error}</Text> : null}

        <View style={{ gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}><Text style={{ fontSize: 18, fontFamily: authFont.bold, color: authColors.onSurface }}>Contribution history</Text><Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>{contributions.length} record{contributions.length === 1 ? '' : 's'}</Text></View>
          {contributions.length === 0 ? (
            <View style={emptyHistoryStyle}><MaterialIcons name="history" size={30} color={authColors.outline} /><Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface }}>No contributions recorded</Text><Text style={{ textAlign: 'center', fontSize: 13, lineHeight: 18, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Your dated contribution history will appear here.</Text></View>
          ) : contributions.map((contribution) => (
            <View key={contribution.id} style={historyRowStyle}>
              <View style={historyIconStyle}><MaterialIcons name="arrow-upward" size={19} color="#06764c" /></View>
              <View style={{ flex: 1 }}><Text style={{ fontSize: 16, fontFamily: authFont.bold, color: authColors.onSurface }}>{formatMoney(contribution.amount)}</Text><Text style={{ marginTop: 2, fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>{formatGoalDate(contribution.contributed_on)}</Text>{contribution.note ? <Text style={{ marginTop: 4, fontSize: 13, lineHeight: 18, fontFamily: authFont.regular, color: authColors.onSurface }}>{contribution.note}</Text> : null}</View>
              <Pressable accessibilityLabel={`Delete ${formatMoney(contribution.amount)} contribution`} accessibilityRole="button" disabled={busy} hitSlop={9} onPress={() => confirmDeleteContribution(contribution)}><MaterialIcons name="delete-outline" size={22} color={authColors.error} /></Pressable>
            </View>
          ))}
        </View>

        <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
          <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: '/savings/manage', params: { goalId: String(goal.id) } })} style={[secondaryButtonStyle, { flex: 1 }]}><MaterialIcons name="edit" size={18} color={authColors.primary} /><Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>Edit goal</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={busy} onPress={confirmDeleteGoal} style={[deleteButtonStyle, { flex: 1 }]}><MaterialIcons name="delete-outline" size={18} color={authColors.error} /><Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.error }}>Delete goal</Text></Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const summaryCardStyle = { alignItems: 'center', gap: 12, padding: 18, borderRadius: 20, backgroundColor: authColors.surfaceContainerLowest, borderWidth: 0.5, borderColor: authColors.outlineVariant } as const;
const metricTileStyle = { flex: 1, minHeight: 66, padding: 10, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLow } as const;
const metricLabelStyle = { fontSize: 11, fontFamily: authFont.bold, color: authColors.onSurfaceVariant } as const;
const metricValueStyle = { marginTop: 4, textAlign: 'center', fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const suggestionCardStyle = { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 16, borderRadius: 16, backgroundColor: authColors.primaryFixed } as const;
const suggestionIconStyle = { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest } as const;
const primaryButtonStyle = { minHeight: 50, borderRadius: 14, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8, backgroundColor: authColors.primary } as const;
const secondaryButtonStyle = { minHeight: 46, paddingHorizontal: 16, borderRadius: 13, borderWidth: 1, borderColor: authColors.primary, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 6 } as const;
const deleteButtonStyle = { minHeight: 46, paddingHorizontal: 16, borderRadius: 13, borderWidth: 1, borderColor: authColors.error, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 6 } as const;
const formCardStyle = { gap: 15, padding: 16, borderRadius: 18, backgroundColor: authColors.surfaceContainerLowest, borderWidth: 1, borderColor: authColors.primaryFixedDim } as const;
const labelStyle = { marginLeft: 2, fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const fieldStyle = { minHeight: 50, paddingHorizontal: 15, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: authColors.outlineVariant, backgroundColor: authColors.surfaceContainerLowest, fontSize: 15, fontFamily: authFont.regular, color: authColors.onSurface } as const;
const errorFieldStyle = { borderColor: authColors.error } as const;
const errorTextStyle = { marginLeft: 2, fontSize: 12, fontFamily: authFont.regular, color: authColors.error } as const;
const currencyPrefixStyle = { position: 'absolute', left: 15, zIndex: 1, fontSize: 15, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const;
const emptyHistoryStyle = { alignItems: 'center', gap: 7, padding: 24, borderRadius: 16, backgroundColor: authColors.surfaceContainerLow } as const;
const historyRowStyle = { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 14, borderRadius: 15, backgroundColor: authColors.surfaceContainerLowest, borderWidth: 0.5, borderColor: authColors.outlineVariant } as const;
const historyIconStyle = { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: '#d9f5e8' } as const;
