import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CategoryIcon } from '@/components/categories/category-icon';
import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { appDialog } from '@/components/ui/app-dialog';
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
import { uploadAvatar } from '@/lib/profile';
import { parseMoney } from '@/lib/savings-domain';
import type { Category } from '@/lib/types';

type ImagePickerModule = typeof import('expo-image-picker');
type ImagePickerRuntime = Pick<ImagePickerModule, 'launchImageLibraryAsync' | 'requestMediaLibraryPermissionsAsync'>;

function resolveImagePickerModule(module: unknown): ImagePickerRuntime | null {
  const candidates = [module, (module as { default?: unknown })?.default];
  for (const candidate of candidates) {
    const picker = candidate as Partial<ImagePickerRuntime> | undefined;
    if (typeof picker?.launchImageLibraryAsync === 'function') {
      return picker as ImagePickerRuntime;
    }
  }
  return null;
}

async function loadImagePicker(): Promise<ImagePickerRuntime | null> {
  try {
    const module = await import('expo-image-picker');
    const imagePicker = resolveImagePickerModule(module);
    if (!imagePicker) {
      throw new Error('expo-image-picker loaded without launchImageLibraryAsync.');
    }
    return imagePicker;
  } catch (caught) {
    console.error('expo-image-picker native module is unavailable.', caught);
    appDialog.open(
      'Photo picker unavailable',
      'Rebuild and reinstall the development build so expo-image-picker is included in the native app.',
    );
    return null;
  }
}

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'FC';
  const last = parts.length > 1 ? parts[parts.length - 1][0] : '';
  return (parts[0][0] + last).toUpperCase();
}

export default function EditProfileScreen() {
  const insets = useSafeAreaInsets();
  const { profile, session, updateProfile } = useAuth();
  const userId = session?.user.id;

  const [fullName, setFullName] = useState('');
  const [income, setIncome] = useState('');
  const [university, setUniversity] = useState(DEFAULT_UNIVERSITY);
  const [yearOfStudy, setYearOfStudy] = useState<string | null>(null);
  const [incomeSource, setIncomeSource] = useState<string | null>(null);
  const [financialStatus, setFinancialStatus] = useState<string | null>(null);
  const [coachingStyle, setCoachingStyle] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [trackedIds, setTrackedIds] = useState<number[]>([]);

  const [loading, setLoading] = useState(true);
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const initialTrackedIds = useRef<number[]>([]);
  const saveInProgress = useRef(false);
  const recordInProgress = useRef(false);

  const load = useCallback(async () => {
    if (!userId) return;
    setFullName(profile?.full_name ?? '');
    setIncome(profile?.monthly_allowance != null ? String(profile.monthly_allowance) : '');
    setUniversity(profile?.university ?? DEFAULT_UNIVERSITY);
    setYearOfStudy(profile?.year_of_study ?? null);
    setIncomeSource(profile?.income_source ?? null);
    setFinancialStatus(profile?.financial_status ?? null);
    setCoachingStyle(profile?.coaching_style ?? null);
    setAvatarUrl(profile?.avatar_url ?? null);

    try {
      const [cats, tracked] = await Promise.all([fetchCategories(), fetchTrackedCategoryIds(userId)]);
      setCategories(cats);
      setTrackedIds(tracked);
      initialTrackedIds.current = tracked;
      setPreferencesReady(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load your profile data.');
    } finally {
      setLoading(false);
    }
  }, [userId, profile]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // Load once on mount; profile is already available from context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleCategory(id: number) {
    setTrackedIds((prev) => (prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]));
  }

  async function pickAvatar() {
    if (!userId) return;
    const imagePicker = await loadImagePicker();
    if (!imagePicker) return;

    let result: Awaited<ReturnType<ImagePickerRuntime['launchImageLibraryAsync']>>;
    try {
      if (typeof imagePicker.requestMediaLibraryPermissionsAsync === 'function') {
        const permission = await imagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) {
          appDialog.open('Permission needed', 'Allow photo access to change your picture.');
          return;
        }
      }
      result = await imagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.7,
        base64: true,
      });
    } catch (caught) {
      console.error('Could not open image picker.', caught);
      appDialog.open('Photo picker unavailable', caught instanceof Error ? caught.message : 'Could not open the photo picker.');
      return;
    }

    const asset = result.assets?.[0];
    if (result.canceled || !asset?.base64) return;

    const ext = asset.uri.split('.').pop()?.toLowerCase() === 'png' ? 'png' : 'jpg';
    setUploadingAvatar(true);
    try {
      const url = await uploadAvatar(userId, asset.base64, ext);
      const updated = await updateProfile({ avatar_url: url });
      if (updated.ok) setAvatarUrl(url);
      else appDialog.open('Upload failed', updated.message);
    } catch (caught) {
      appDialog.open('Upload failed', caught instanceof Error ? caught.message : 'Could not upload the image.');
    } finally {
      setUploadingAvatar(false);
    }
  }

  async function save(destination: 'back' | 'record_income' = 'back') {
    if (!userId || saveInProgress.current) return;
    saveInProgress.current = true;
    setError(null);
    setSaving(true);
    try {
      const profileResult = await updateProfile({
        full_name: fullName.trim(),
        monthly_allowance: income ? Number(income) : null,
        university: university.trim() || DEFAULT_UNIVERSITY,
        year_of_study: yearOfStudy,
        income_source: incomeSource,
        financial_status: financialStatus,
        coaching_style: coachingStyle,
      });
      if (!profileResult.ok) throw new Error(profileResult.message);

      await setTrackedCategories(userId, trackedIds);
      if (destination === 'record_income') openIncomeForm();
      else router.back();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your changes.');
      setSaving(false);
    } finally {
      saveInProgress.current = false;
      setSaving(false);
    }
  }

  function openIncomeForm() {
    router.push({ pathname: '/transactions/manage', params: { prefill: 'profile_income' } } as never);
  }

  async function recordMonthlyIncome() {
    if (!userId || saving || !preferencesReady || recordInProgress.current) return;
    const amount = parseMoney(income);
    if (amount == null || amount <= 0) return;
    recordInProgress.current = true;
    try {
      const changed = fullName.trim() !== (profile?.full_name ?? '').trim()
        || amount !== profile?.monthly_allowance || incomeSource !== (profile?.income_source ?? null)
        || university.trim() !== (profile?.university ?? DEFAULT_UNIVERSITY).trim()
        || yearOfStudy !== (profile?.year_of_study ?? null)
        || financialStatus !== (profile?.financial_status ?? null)
        || coachingStyle !== (profile?.coaching_style ?? null)
        || [...trackedIds].sort((a, b) => a - b).join(',') !== [...initialTrackedIds.current].sort((a, b) => a - b).join(',');
      if (changed) {
        const confirmed = await appDialog.open('Save Preferences first?', 'Save your changes, then review the income amount and date. Money is recorded only when you save the income transaction.', [
          { text: 'Cancel', style: 'cancel' }, { text: 'Save & continue' },
        ]);
        if (confirmed) await save('record_income');
      } else openIncomeForm();
    } finally { recordInProgress.current = false; }
  }

  const topPad = insets.top + 8;
  const monthlyAmount = parseMoney(income);
  const canRecordIncome = preferencesReady && !saving && !uploadingAvatar && monthlyAmount != null && monthlyAmount > 0;
  const displayName = fullName.trim() || 'Student';

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      {/* Indigo banner */}
      <View style={{ backgroundColor: authColors.primary, paddingTop: topPad, paddingHorizontal: 16, paddingBottom: 28 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <Pressable onPress={() => router.back()} hitSlop={8}>
            <MaterialIcons name="arrow-back" size={24} color="#fff" />
          </Pressable>
          <Text style={{ fontSize: 18, fontFamily: authFont.semibold, color: '#fff' }}>Edit Profile</Text>
        </View>

        <View style={{ alignItems: 'center', marginTop: 8 }}>
          <Pressable onPress={() => void pickAvatar()} disabled={uploadingAvatar}>
            <View
              style={{
                width: 96,
                height: 96,
                borderRadius: 48,
                backgroundColor: authColors.primaryFixed,
                borderWidth: 3,
                borderColor: '#fff',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
              }}>
              {uploadingAvatar ? (
                <ActivityIndicator color={authColors.primary} />
              ) : avatarUrl ? (
                <Image source={{ uri: avatarUrl }} style={{ width: '100%', height: '100%' }} contentFit="cover" />
              ) : (
                <Text style={{ fontSize: 30, fontFamily: authFont.bold, color: authColors.primary }}>{getInitials(displayName)}</Text>
              )}
            </View>
            <View
              style={{
                position: 'absolute',
                right: -2,
                bottom: -2,
                width: 30,
                height: 30,
                borderRadius: 15,
                backgroundColor: '#fff',
                borderWidth: 2,
                borderColor: authColors.primary,
                alignItems: 'center',
                justifyContent: 'center',
              }}>
              <MaterialIcons name="edit" size={15} color={authColors.primary} />
            </View>
          </Pressable>
          <Text style={{ fontSize: 18, fontFamily: authFont.semibold, color: '#fff', marginTop: 10 }}>{displayName}</Text>
          <Text style={{ fontSize: 12, fontFamily: authFont.regular, color: '#c7c8f4', marginTop: 2 }}>{university}</Text>
        </View>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={authColors.primary} />
        </View>
      ) : (
        <ScrollView
          keyboardShouldPersistTaps="handled"
          style={{ flex: 1, marginTop: -18 }}
          contentContainerStyle={{ backgroundColor: authColors.surface, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 16, paddingBottom: insets.bottom + 32, gap: 22 }}>
          {/* Basic info */}
          <View>
            <SectionTitle>BASIC INFO</SectionTitle>
            <View style={cardStyle}>
              <Field label="Full Name">
                <TextInput style={fieldStyle} value={fullName} onChangeText={setFullName} placeholder="e.g. Alex Chen" placeholderTextColor={authColors.outline} autoCapitalize="words" />
              </Field>
              <View style={{ gap: 6, marginBottom: 12 }}>
                <Text style={labelStyle}>University</Text>
                <ChipGroup options={UNIVERSITY_OPTIONS} value={university} onSelect={setUniversity} />
              </View>
              <View style={{ gap: 6, marginBottom: 4 }}>
                <Text style={labelStyle}>Year of Study</Text>
                <ChipGroup options={YEAR_OF_STUDY_OPTIONS} value={yearOfStudy} onSelect={setYearOfStudy} />
              </View>
            </View>
          </View>

          {/* Money source */}
          <View>
            <SectionTitle>MONTHLY MONEY SOURCE</SectionTitle>
            <View style={cardStyle}>
              <Field label="Expected Monthly Allowance / Income">
                <View style={{ position: 'relative', justifyContent: 'center' }}>
                  <Text style={prefixStyle}>RM</Text>
                  <TextInput style={[fieldStyle, { paddingLeft: 42 }]} value={income} onChangeText={setIncome} placeholder="1500" placeholderTextColor={authColors.outline} keyboardType="decimal-pad" />
                </View>
              </Field>
              <Text style={[labelStyle, { marginBottom: 12 }]}>Used for planning. Record money received to include it in Reports.</Text>
              <View style={{ gap: 6 }}>
                <Text style={labelStyle}>Source Type</Text>
                <ChipGroup options={INCOME_SOURCE_OPTIONS} value={incomeSource} onSelect={setIncomeSource} />
              </View>
              <Pressable accessibilityRole="button" disabled={!canRecordIncome} onPress={() => void recordMonthlyIncome()} style={{ marginTop: 14, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 10, backgroundColor: authColors.primaryFixed, opacity: canRecordIncome ? 1 : 0.5 }}>
                <Text style={{ color: authColors.primary, fontFamily: authFont.semibold, textAlign: 'center' }}>Record monthly income</Text>
              </Pressable>
              {monthlyAmount == null || monthlyAmount <= 0 ? <Text style={[labelStyle, { marginTop: 8 }]}>Enter a monthly amount greater than RM 0 to record income.</Text> : null}
            </View>
          </View>

          {/* Financial status */}
          <View>
            <SectionTitle>FINANCIAL STATUS</SectionTitle>
            <ChipGroup options={FINANCIAL_STATUS_OPTIONS} value={financialStatus} onSelect={setFinancialStatus} />
          </View>

          {/* Tracking preferences */}
          <View>
            <SectionTitle>TRACKING PREFERENCES</SectionTitle>
            <Text style={[labelStyle, { marginBottom: 6 }]}>Categories to track</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
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
                    <CategoryIcon category={category} size={22} glyphSize={18} tintColor={selected ? authColors.primary : authColors.onSurfaceVariant} backgroundColor="transparent" />
                    <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: selected ? authColors.primary : authColors.onSurfaceVariant }}>{category.name}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={[labelStyle, { marginBottom: 6 }]}>Preferred AI Coaching Style</Text>
            <ChipGroup options={COACHING_STYLE_OPTIONS} value={coachingStyle} onSelect={setCoachingStyle} />
          </View>

          {error ? <Text style={{ fontSize: 14, fontFamily: authFont.regular, color: authColors.error }}>{error}</Text> : null}

          <Pressable
            disabled={saving}
            onPress={() => void save()}
            style={({ pressed }) => [
              { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: authColors.primary, paddingVertical: 16, borderRadius: 14 },
              pressed && { opacity: 0.9 },
            ]}>
            {saving ? (
              <ActivityIndicator color={authColors.onPrimary} />
            ) : (
              <>
                <MaterialIcons name="check" size={20} color={authColors.onPrimary} />
                <Text style={{ fontSize: 15, fontFamily: authFont.semibold, color: authColors.onPrimary }}>Save Changes</Text>
              </>
            )}
          </Pressable>
        </ScrollView>
      )}
    </View>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Text style={{ fontSize: 12, fontFamily: authFont.semibold, color: authColors.primary, letterSpacing: 0.3, marginBottom: 8, marginLeft: 2 }}>
      {children}
    </Text>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: 4, marginBottom: 12 }}>
      <Text style={labelStyle}>{label}</Text>
      {children}
    </View>
  );
}

const labelStyle = { fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant, marginLeft: 2 } as const;

const fieldStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  borderRadius: 8,
  paddingHorizontal: 14,
  paddingVertical: 11,
  fontSize: 14,
  fontFamily: authFont.regular,
  color: authColors.onSurface,
} as const;

const prefixStyle = {
  position: 'absolute',
  left: 14,
  zIndex: 1,
  fontSize: 14,
  fontFamily: authFont.regular,
  color: authColors.outline,
} as const;

const cardStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderRadius: 12,
  borderWidth: 0.5,
  borderColor: authColors.outlineVariant,
  padding: 14,
} as const;
