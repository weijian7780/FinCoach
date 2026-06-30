import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, ScrollView, StatusBar, View } from 'react-native';

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
import { uploadAvatar } from '@/lib/profile';
import type { Category } from '@/lib/types';

type IconName = React.ComponentProps<typeof MaterialIcons>['name'];
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
    Alert.alert(
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
  const [saving, setSaving] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          Alert.alert('Permission needed', 'Allow photo access to change your picture.');
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
      Alert.alert('Photo picker unavailable', caught instanceof Error ? caught.message : 'Could not open the photo picker.');
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
      else Alert.alert('Upload failed', updated.message);
    } catch (caught) {
      Alert.alert('Upload failed', caught instanceof Error ? caught.message : 'Could not upload the image.');
    } finally {
      setUploadingAvatar(false);
    }
  }

  async function save() {
    if (!userId) return;
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
      router.back();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your changes.');
      setSaving(false);
    }
  }

  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;
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
          contentContainerStyle={{ backgroundColor: authColors.surface, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 16, paddingBottom: 32, gap: 22 }}>
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
              <Field label="Monthly Allowance / Income">
                <View style={{ position: 'relative', justifyContent: 'center' }}>
                  <Text style={prefixStyle}>RM</Text>
                  <TextInput style={[fieldStyle, { paddingLeft: 42 }]} value={income} onChangeText={setIncome} placeholder="1500" placeholderTextColor={authColors.outline} keyboardType="decimal-pad" />
                </View>
              </Field>
              <View style={{ gap: 6 }}>
                <Text style={labelStyle}>Source Type</Text>
                <ChipGroup options={INCOME_SOURCE_OPTIONS} value={incomeSource} onSelect={setIncomeSource} />
              </View>
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
                    <MaterialIcons name={(category.icon as IconName) ?? 'category'} size={18} color={selected ? authColors.primary : authColors.onSurfaceVariant} />
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
