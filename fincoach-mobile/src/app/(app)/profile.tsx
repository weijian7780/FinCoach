import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import type { ComponentProps } from 'react';
import { Alert, Platform, Pressable, ScrollView, StatusBar, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { NotificationBell } from '@/components/notifications/notification-bell';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { setTrackedCategories } from '@/lib/finance';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

function getInitials(name: string | null | undefined) {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'FC';
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : '';
  return (first + last).toUpperCase();
}

export default function ProfileScreen() {
  const { profile, session, signOut, updateProfile } = useAuth();
  const userId = session?.user.id;

  async function handleLogout() {
    await signOut();
    router.replace('/auth/login');
  }

  function handleResetProfile() {
    Alert.alert(
      'Reset Financial Profile?',
      'This clears your allowance, study and income details, financial status and preferences. Your account and name are kept. You will be taken back to setup.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: () => {
            void (async () => {
              const result = await updateProfile({
                monthly_allowance: null,
                year_of_study: null,
                income_source: null,
                financial_status: null,
                coaching_style: null,
                onboarding_completed: false,
                spending_records_consent: 'unset',
              });
              if (result.ok) {
                // Tracked categories live in their own table, so clear them too —
                // otherwise the previous "preferences" survive a reset.
                if (userId) {
                  try {
                    await setTrackedCategories(userId, []);
                  } catch {
                    // Non-fatal: the profile fields are already cleared.
                  }
                }
                router.replace('/profile/setup');
              } else {
                Alert.alert('Could not reset', result.message);
              }
            })();
          },
        },
      ],
    );
  }

  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;
  const name = profile?.full_name || 'Student';

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      {/* Top app bar */}
      <View
        style={{
          paddingTop: topPad,
          paddingHorizontal: 16,
          paddingBottom: 12,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {profile?.avatar_url ? (
            <Image
              source={{ uri: profile.avatar_url }}
              style={{ width: 28, height: 28, borderRadius: 14 }}
              contentFit="cover"
            />
          ) : (
            <MaterialIcons name="account-circle" size={26} color={authColors.primary} />
          )}
          <Text style={{ fontSize: 24, fontFamily: authFont.bold, color: authColors.primary }}>FinCoach</Text>
        </View>
        <NotificationBell filled />
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, gap: 24 }}>
        {/* Profile header card */}
        <View style={[cardStyle, { alignItems: 'center', padding: 24 }]}>
          <View
            style={{
              width: 96,
              height: 96,
              borderRadius: 48,
              backgroundColor: authColors.primaryFixed,
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 16,
              borderWidth: 4,
              borderColor: authColors.surfaceContainerHigh,
              overflow: 'hidden',
            }}>
            {profile?.avatar_url ? (
              <Image source={{ uri: profile.avatar_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" />
            ) : (
              <Text style={{ fontSize: 32, fontFamily: authFont.bold, color: authColors.primary }}>{getInitials(profile?.full_name)}</Text>
            )}
          </View>
          <Text style={{ fontSize: 20, fontFamily: authFont.semibold, color: authColors.onSurface, marginBottom: 4 }}>{name}</Text>
          <Text style={{ fontSize: 16, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, marginBottom: 12, textAlign: 'center' }}>
            {profile?.university ?? 'UMS Kota Kinabalu'}
          </Text>
        </View>

        {/* Options */}
        <View style={{ gap: 12 }}>
          <OptionRow icon="tune" label="Preferences" onPress={() => router.push('/profile/edit')} />
          <OptionRow icon="settings" label="App Settings" onPress={() => router.push('/profile/settings')} />
          <OptionRow icon="restart-alt" label="Reset Financial Profile" onPress={handleResetProfile} danger />

          <Pressable
            onPress={handleLogout}
            style={({ pressed }) => [
              {
                marginTop: 12,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                backgroundColor: '#ffdad6',
                borderRadius: 12,
                padding: 16,
              },
              pressed && { opacity: 0.9 },
            ]}>
            <MaterialIcons name="logout" size={20} color="#93000a" />
            <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: '#93000a' }}>Logout</Text>
          </Pressable>
        </View>

        <Text style={{ textAlign: 'center', fontSize: 12, fontFamily: authFont.regular, color: authColors.outline }}>
          {session?.user.email}
        </Text>
      </ScrollView>
    </View>
  );
}

function OptionRow({ icon, label, value, onPress, danger }: { icon: IconName; label: string; value?: string; onPress?: () => void; danger?: boolean }) {
  const accent = danger ? authColors.error : authColors.primary;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [cardStyle, { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16 }, pressed && onPress ? { opacity: 0.85 } : null]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }}>
        <View style={{ padding: 8, backgroundColor: danger ? '#ffdad6' : authColors.surfaceContainer, borderRadius: 8 }}>
          <MaterialIcons name={icon} size={22} color={accent} />
        </View>
        <View>
          <Text style={{ fontSize: 16, fontFamily: authFont.regular, color: danger ? authColors.error : authColors.onSurface }}>{label}</Text>
          {value ? <Text style={{ fontSize: 12, fontFamily: authFont.semibold, color: authColors.primary }}>{value}</Text> : null}
        </View>
      </View>
      <MaterialIcons name="chevron-right" size={22} color={authColors.onSurfaceVariant} />
    </Pressable>
  );
}

const cardStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderRadius: 12,
  shadowColor: authColors.primary,
  shadowOffset: { width: 0, height: 4 },
  shadowOpacity: 0.05,
  shadowRadius: 12,
  elevation: 2,
} as const;
