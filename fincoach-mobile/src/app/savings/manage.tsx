import { MaterialIcons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DateField } from '@/components/savings/date-field';
import { ProgressRing } from '@/components/savings/progress-ring';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { createSavingsGoal, fetchSavingsGoal, updateSavingsGoal } from '@/lib/savings';
import { getSavingsMetrics, parseMoney, todayIsoDate, type FieldErrors, type GoalInput, validateGoalInput } from '@/lib/savings-domain';

export default function ManageSavingsGoalScreen() {
  const insets = useSafeAreaInsets();
  const { goalId: goalIdParam } = useLocalSearchParams<{ goalId?: string }>();
  const goalId = goalIdParam?.trim() || null;
  const editing = goalId != null;
  const { session } = useAuth();
  const userId = session?.user.id;
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [deadline, setDeadline] = useState('');
  const [currentAmount, setCurrentAmount] = useState(0);
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors<GoalInput>>({});
  const [error, setError] = useState<string | null>(null);
  const today = todayIsoDate();
  const progress = getSavingsMetrics(currentAmount, parseMoney(targetAmount) ?? 0);

  useEffect(() => {
    if (!editing || !goalId || !userId) return;
    let active = true;
    fetchSavingsGoal(goalId, userId).then((goal) => {
      if (!active) return;
      if (!goal) throw new Error('Savings goal not found.');
      setName(goal.name);
      setTargetAmount(String(goal.target_amount));
      setDeadline(goal.deadline ?? '');
      setCurrentAmount(goal.current_amount);
    }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : 'Could not load this goal.'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [editing, goalId, userId]);

  async function save() {
    if (!userId) return;
    const input = { name, targetAmount, deadline };
    const errors = validateGoalInput(input, { today, currentAmount });
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    const parsedTarget = parseMoney(targetAmount);
    if (parsedTarget == null) return;
    setSaving(true);
    setError(null);
    try {
      const payload = { name: name.trim(), target_amount: parsedTarget, deadline: deadline || null };
      const goal = editing && goalId ? await updateSavingsGoal(goalId, userId, payload) : await createSavingsGoal(userId, payload);
      router.replace({ pathname: '/savings/[goalId]', params: { goalId: String(goal.id) } });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save this goal.');
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={screenStyle}>
      <View style={[headerStyle, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityLabel="Go back" accessibilityRole="button" hitSlop={8} onPress={() => router.back()} style={{ width: 38, height: 44, alignItems: 'flex-start', justifyContent: 'center' }}><MaterialIcons name="arrow-back" size={30} color={authColors.onSurface} /></Pressable>
        <Text numberOfLines={1} style={headerTitleStyle}>{editing ? 'Edit Savings Goal' : 'New Savings Goal'}</Text>
      </View>
      {loading ? <View style={loadingStyle}><ActivityIndicator color={authColors.primary} /></View> : (
        <View style={{ flex: 1 }}>
          <ScrollView contentContainerStyle={scrollContentStyle} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
            <View style={previewCardStyle}>
              <View style={previewIconStyle}><MaterialIcons name="account-balance-wallet" size={30} color={authColors.primary} /></View>
              <View style={{ flex: 1, minWidth: 0 }}><Text numberOfLines={1} style={previewTitleStyle}>{name.trim() || 'Your new goal'}</Text><Text style={previewSubtitleStyle}>Start with a clear target</Text></View>
              <ProgressRing color={authColors.primary} progress={progress.ratio} size={68} strokeWidth={8}><Text style={progressTextStyle}>{progress.percentage}%</Text></ProgressRing>
            </View>
            <View style={{ gap: 8 }}>
              <Text style={labelStyle}>Goal purpose</Text>
              <View style={[fieldShellStyle, fieldErrors.name && errorFieldStyle]}><MaterialIcons name="flag" size={24} color={authColors.primary} /><TextInput accessibilityLabel="Goal purpose" autoCapitalize="sentences" maxLength={100} onChangeText={(value) => { setName(value); setFieldErrors((previous) => ({ ...previous, name: undefined })); }} placeholder="e.g. New laptop" placeholderTextColor={authColors.outline} style={fieldInputStyle} value={name} /></View>
              {fieldErrors.name ? <Text style={errorTextStyle}>{fieldErrors.name}</Text> : null}
            </View>
            <View style={{ gap: 8 }}>
              <Text style={labelStyle}>Target amount</Text>
              <View style={[fieldShellStyle, fieldErrors.targetAmount && errorFieldStyle]}><MaterialIcons name="account-balance-wallet" size={24} color={authColors.primary} /><Text style={currencyLabelStyle}>RM</Text><View style={amountDividerStyle} /><TextInput accessibilityLabel="Target amount in Ringgit Malaysia" keyboardType="decimal-pad" onChangeText={(value) => { setTargetAmount(value.replace(/[^0-9.]/g, '')); setFieldErrors((previous) => ({ ...previous, targetAmount: undefined })); }} placeholder="3,000.00" placeholderTextColor={authColors.outline} style={fieldInputStyle} value={targetAmount} /></View>
              {fieldErrors.targetAmount ? <Text style={errorTextStyle}>{fieldErrors.targetAmount}</Text> : null}
            </View>
            <DateField error={fieldErrors.deadline} helperText="Deadline is optional" label="Target deadline" leadingIcon="calendar-today" minimumDate={today} onChange={(value) => { setDeadline(value); setFieldErrors((previous) => ({ ...previous, deadline: undefined })); }} placeholder="Select date" value={deadline} variant="tonal" />
            {error ? <Text style={[errorTextStyle, { fontSize: 14 }]}>{error}</Text> : null}
          </ScrollView>
          <View style={[footerStyle, { paddingBottom: Math.max(insets.bottom, 12) }]}><Pressable accessibilityRole="button" disabled={saving} onPress={() => void save()} style={({ pressed }) => [saveButtonStyle, (pressed || saving) && { opacity: 0.82 }]}>{saving ? <ActivityIndicator color={authColors.onPrimary} /> : <MaterialIcons name="check" size={25} color={authColors.onPrimary} />}<Text style={saveButtonTextStyle}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create goal'}</Text></Pressable></View>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const screenStyle = { flex: 1, backgroundColor: authColors.surface } as const;
const headerStyle = { minHeight: 68, paddingHorizontal: 20, paddingBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 10 } as const;
const headerTitleStyle = { flex: 1, fontSize: 24, lineHeight: 31, fontFamily: authFont.bold, letterSpacing: -0.35, color: authColors.onSurface } as const;
const loadingStyle = { flex: 1, alignItems: 'center', justifyContent: 'center' } as const;
const scrollContentStyle = { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 24, gap: 22 } as const;
const previewCardStyle = { minHeight: 108, paddingHorizontal: 16, paddingVertical: 18, flexDirection: 'row', alignItems: 'center', gap: 13, borderRadius: 20, backgroundColor: authColors.surfaceContainerLowest, shadowColor: '#211F2C', shadowOffset: { width: 0, height: 7 }, shadowOpacity: 0.09, shadowRadius: 18, elevation: 4 } as const;
const previewIconStyle = { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed } as const;
const previewTitleStyle = { fontSize: 18, lineHeight: 24, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const previewSubtitleStyle = { marginTop: 3, fontSize: 14, lineHeight: 19, fontFamily: authFont.regular, color: authColors.outline } as const;
const progressTextStyle = { fontSize: 15, fontFamily: authFont.semibold, color: authColors.primary } as const;
const labelStyle = { marginLeft: 3, fontSize: 16, lineHeight: 22, fontFamily: authFont.semibold, color: authColors.onSurface } as const;
const fieldShellStyle = { minHeight: 64, paddingHorizontal: 17, flexDirection: 'row', alignItems: 'center', gap: 13, borderRadius: 16, borderWidth: 1, borderColor: 'transparent', backgroundColor: authColors.surfaceContainer } as const;
const fieldInputStyle = { flex: 1, minHeight: 58, paddingVertical: 0, fontSize: 16, fontFamily: authFont.regular, color: authColors.onSurface } as const;
const errorFieldStyle = { borderColor: authColors.error } as const;
const errorTextStyle = { marginLeft: 3, fontSize: 12, lineHeight: 17, fontFamily: authFont.regular, color: authColors.error } as const;
const currencyLabelStyle = { fontSize: 16, fontFamily: authFont.bold, color: authColors.onSurface } as const;
const amountDividerStyle = { width: 1, height: 28, backgroundColor: authColors.outlineVariant } as const;
const footerStyle = { paddingTop: 10, paddingHorizontal: 20, backgroundColor: authColors.surface } as const;
const saveButtonStyle = { minHeight: 58, borderRadius: 16, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 10, backgroundColor: authColors.primary, shadowColor: authColors.primary, shadowOffset: { width: 0, height: 7 }, shadowOpacity: 0.24, shadowRadius: 12, elevation: 5 } as const;
const saveButtonTextStyle = { fontSize: 17, fontFamily: authFont.semibold, color: authColors.onPrimary } as const;
