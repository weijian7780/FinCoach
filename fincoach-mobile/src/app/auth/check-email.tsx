import { MaterialIcons } from '@expo/vector-icons';
import { Link, useLocalSearchParams } from 'expo-router';
import { ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text } from '@/components/ui/app-text';
import { AuthBackdrop } from '@/components/ui/auth-backdrop';
import { authColors, authFont, authRadius, authSpacing, authType } from '@/constants/auth-theme';

export default function CheckEmailScreen() {
  const { email } = useLocalSearchParams<{ email?: string }>();
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <AuthBackdrop color={authColors.primaryFixedDim} height={360} maxOpacity={0.4} />
      <ScrollView
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: 'center',
          paddingHorizontal: authSpacing.container,
          paddingTop: insets.top + authSpacing.lg,
          paddingBottom: insets.bottom + authSpacing.lg,
        }}>
        {/* Icon */}
        <View style={{ alignItems: 'center', marginBottom: authSpacing.lg }}>
          <View
            style={{
              width: 64,
              height: 64,
              borderRadius: authRadius.full,
              backgroundColor: authColors.surfaceContainerLowest,
              alignItems: 'center',
              justifyContent: 'center',
              shadowColor: authColors.primary,
              shadowOffset: { width: 0, height: 10 },
              shadowOpacity: 0.1,
              shadowRadius: 20,
              elevation: 4,
            }}>
            <MaterialIcons name="mark-email-unread" size={30} color={authColors.primary} />
          </View>
        </View>

        {/* Card */}
        <View
          style={{
            backgroundColor: authColors.surfaceContainerLowest,
            borderRadius: authRadius.lg,
            padding: authSpacing.container,
            shadowColor: authColors.primary,
            shadowOffset: { width: 0, height: 10 },
            shadowOpacity: 0.08,
            shadowRadius: 30,
            elevation: 3,
          }}>
          <Text style={[authType.displayTitle, { color: authColors.onSurface, marginBottom: authSpacing.unit }]}>
            Check your email
          </Text>
          <Text style={[authType.body, { color: authColors.onSurfaceVariant }]} selectable>
            We sent a verification link to{' '}
            <Text style={[authType.body, { color: authColors.onSurface, fontFamily: authFont.semibold }]}>
              {email || 'your email'}
            </Text>
            . Open it on this device, then return to FinCoach to continue.
          </Text>

          <Link href="/auth/login" style={[authType.titleSm, { color: authColors.primary, marginTop: authSpacing.lg }]}>
            Back to login
          </Link>
        </View>
      </ScrollView>
    </View>
  );
}
