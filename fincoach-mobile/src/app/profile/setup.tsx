import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, StatusBar, View } from 'react-native';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { ChipGroup } from '@/components/ui/chip-group';
import { authColors, authFont } from '@/constants/auth-theme';
import {
  COACHING_STYLE_OPTIONS,
  DEFAULT_UNIVERSITY,
  FINANCIAL_STATUS_OPTIONS,
  INCOME_SOURCE_OPTIONS,
  UNIVERSITY_OPTIONS,
  YEAR_OF_STUDY_OPTIONS,
} from '@/constants/profile-options';
import { useAuth } from '@/lib/auth-context';
import { fetchCategories, fetchTrackedCategoryIds, setTrackedCategories } from '@/lib/finance';
import type { Category } from '@/lib/types';

type IconName = React.ComponentProps<typeof MaterialIcons>['name'];

const TOTAL_STEPS = 4;

const STEP_META = [
  { icon: 'person-add', title: 'About you', subtitle: 'Tell us who you are to personalise your experience.' },
  { icon: 'account-balance-wallet', title: 'Your money', subtitle: 'How much you get each month and where it comes from.' },
  { icon: 'insights', title: 'Your situation', subtitle: 'How would you describe your finances right now?' },
  { icon: 'tune', title: 'Preferences', subtitle: 'Pick what to track and how you want the AI coach to talk to you.' },
] as const;

export default function ProfileSetupScreen() {
  const { profile, session, updateProfile } = useAuth();
  const userId = session?.user.id;

  const [step, setStep] = useState(0);
  const [fullName, setFullName] = useState('');
  const [income, setIncome] = useState('');
  const [university, setUniversity] = useState(DEFAULT_UNIVERSITY);
  const [yearOfStudy, setYearOfStudy] = useState<string | null>(null);
  const [incomeSource, setIncomeSource] = useState<string | null>(null);
  const [financialStatus, setFinancialStatus] = useState<string | null>(null);
  const [coachingStyle, setCoachingStyle] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [trackedIds, setTrackedIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setFullName(profile?.full_name ?? '');
    setIncome(profile?.monthly_allowance != null ? String(profile.monthly_allowance) : '');
    setUniversity(profile?.university ?? DEFAULT_UNIVERSITY);
    setYearOfStudy(profile?.year_of_study ?? null);
    setIncomeSource(profile?.income_source ?? null);
    setFinancialStatus(profile?.financial_status ?? null);
    setCoachingStyle(profile?.coaching_style ?? null);
    if (!userId) return;
    try {
      const [cats, tracked] = await Promise.all([fetchCategories(), fetchTrackedCategoryIds(userId)]);
      setCategories(cats);
      setTrackedIds(tracked);
    } catch {
      // Categories load is best-effort; the wizard still works without them.
    }
  }, [userId, profile]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleCategory(id: number) {
    setTrackedIds((prev) => (prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]));
  }

  async function finish() {
    if (!userId) return;
    setError(null);
    setSubmitting(true);
    const result = await updateProfile({
      full_name: fullName.trim(),
      monthly_allowance: income ? Number(income) : null,
      university: university.trim() || DEFAULT_UNIVERSITY,
      year_of_study: yearOfStudy,
      income_source: incomeSource,
      financial_status: financialStatus,
      coaching_style: coachingStyle,
      onboarding_completed: true,
    });

    if (!result.ok) {
      setSubmitting(false);
      setError(result.message);
      return;
    }

    try {
      await setTrackedCategories(userId, trackedIds);
    } catch {
      // Non-fatal: the profile is saved; tracked categories can be set later in Edit Profile.
    }

    setSubmitting(false);
    router.replace('/(app)');
  }

  // "Skip for now" must NOT re-save the pre-filled form (that would re-commit data the
  // user just reset). It only marks onboarding done and leaves every field as-is.
  async function skip() {
    setSubmitting(true);
    await updateProfile({ onboarding_completed: true });
    setSubmitting(false);
    router.replace('/(app)');
  }

  function handleNext() {
    if (step < TOTAL_STEPS - 1) {
      setStep((current) => current + 1);
      return;
    }
    void finish();
  }

  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;
  const meta = STEP_META[step];

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface, paddingTop: topPad }}>
      {/* Progress + back */}
      <View style={{ paddingHorizontal: 20, paddingBottom: 8, gap: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          {step > 0 ? (
            <Pressable onPress={() => setStep((current) => current - 1)} hitSlop={8}>
              <MaterialIcons name="arrow-back" size={24} color={authColors.onSurfaceVariant} />
            </Pressable>
          ) : null}
          <View style={{ flex: 1, height: 8, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh, overflow: 'hidden' }}>
            <View style={{ height: '100%', width: `${((step + 1) / TOTAL_STEPS) * 100}%`, backgroundColor: authColors.primary, borderRadius: 999 }} />
          </View>
          <Text style={{ fontSize: 12, fontFamily: authFont.semibold, color: authColors.primary }}>{step + 1}/{TOTAL_STEPS}</Text>
        </View>
      </View>

      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 8, paddingBottom: 24, gap: 24 }}>
        {/* Header */}
        <View style={{ gap: 8, marginTop: 8 }}>
          <View style={{ width: 48, height: 48, borderRadius: 999, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
            <MaterialIcons name={meta.icon} size={26} color={authColors.primary} />
          </View>
          <Text style={{ fontSize: 26, lineHeight: 32, fontFamily: authFont.bold, color: authColors.onSurface }}>{meta.title}</Text>
          <Text style={{ fontSize: 16, lineHeight: 24, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>{meta.subtitle}</Text>
        </View>

        {/* Step 1: basic info */}
        {step === 0 ? (
          <View style={{ gap: 16 }}>
            <Field label="Full Name">
              <TextInput style={fieldStyle} value={fullName} onChangeText={setFullName} placeholder="e.g. Alex Chen" placeholderTextColor={authColors.outline} autoCapitalize="words" />
            </Field>
            <Field label="University">
              <ChipGroup options={UNIVERSITY_OPTIONS} value={university} onSelect={setUniversity} />
            </Field>
            <Field label="Year of Study">
              <ChipGroup options={YEAR_OF_STUDY_OPTIONS} value={yearOfStudy} onSelect={setYearOfStudy} />
            </Field>
          </View>
        ) : null}

        {/* Step 2: money source */}
        {step === 1 ? (
          <View style={{ gap: 16 }}>
            <Field label="Monthly Allowance / Income (RM)">
              <View style={{ position: 'relative', justifyContent: 'center' }}>
                <Text style={{ position: 'absolute', left: 16, zIndex: 1, fontSize: 16, fontFamily: authFont.regular, color: authColors.outline }}>RM</Text>
                <TextInput style={[fieldStyle, { paddingLeft: 44 }]} value={income} onChangeText={setIncome} placeholder="1500" placeholderTextColor={authColors.outline} keyboardType="decimal-pad" />
              </View>
            </Field>
            <Field label="Source Type">
              <ChipGroup options={INCOME_SOURCE_OPTIONS} value={incomeSource} onSelect={setIncomeSource} />
            </Field>
          </View>
        ) : null}

        {/* Step 3: financial status */}
        {step === 2 ? (
          <ChipGroup options={FINANCIAL_STATUS_OPTIONS} value={financialStatus} onSelect={setFinancialStatus} />
        ) : null}

        {/* Step 4: tracking preferences */}
        {step === 3 ? (
          <View style={{ gap: 20 }}>
            <Field label="Categories to track">
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {categories.map((category) => {
                  const selected = trackedIds.includes(category.id);
                  return (
                    <Pressable
                      key={category.id}
                      onPress={() => toggleCategory(category.id)}
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 6,
                        paddingHorizontal: 14,
                        paddingVertical: 9,
                        borderRadius: 999,
                        borderWidth: 1.5,
                        borderColor: selected ? authColors.primary : 'transparent',
                        backgroundColor: selected ? authColors.primaryFixed : authColors.surfaceContainer,
                      }}>
                      <MaterialIcons name={(category.icon as IconName) ?? 'category'} size={18} color={selected ? authColors.primary : authColors.onSurfaceVariant} />
                      <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: selected ? authColors.primary : authColors.onSurfaceVariant }}>{category.name}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </Field>
            <Field label="Preferred AI Coaching Style">
              <ChipGroup options={COACHING_STYLE_OPTIONS} value={coachingStyle} onSelect={setCoachingStyle} />
            </Field>
          </View>
        ) : null}

        {error ? <Text style={{ fontSize: 14, fontFamily: authFont.regular, color: authColors.error }}>{error}</Text> : null}
      </ScrollView>

      {/* Action */}
      <View style={{ paddingHorizontal: 20, paddingBottom: 24, paddingTop: 8 }}>
        <Pressable
          disabled={submitting}
          onPress={handleNext}
          style={({ pressed }) => [
            { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: authColors.primary, paddingVertical: 16, borderRadius: 16 },
            pressed && { opacity: 0.9 },
          ]}>
          {submitting ? (
            <ActivityIndicator color={authColors.onPrimary} />
          ) : (
            <>
              <Text style={{ fontSize: 16, fontFamily: authFont.semibold, color: authColors.onPrimary }}>
                {step === TOTAL_STEPS - 1 ? 'Get Started' : 'Continue'}
              </Text>
              <MaterialIcons name="arrow-forward" size={20} color={authColors.onPrimary} />
            </>
          )}
        </Pressable>
        <View style={{ alignItems: 'center', marginTop: 12 }}>
          <Pressable onPress={() => void skip()} hitSlop={8}>
            <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>Skip for now</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface, marginLeft: 4 }}>{label}</Text>
      {children}
    </View>
  );
}

const fieldStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  borderRadius: 8,
  paddingHorizontal: 16,
  paddingVertical: 12,
  fontSize: 16,
  fontFamily: authFont.regular,
  color: authColors.onSurface,
} as const;
