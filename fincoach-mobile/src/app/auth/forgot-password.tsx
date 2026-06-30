import { Link } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, View } from 'react-native';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { AuthBackdrop } from '@/components/ui/auth-backdrop';
import { authColors, authFont, authRadius, authSpacing, authType } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';

export default function ForgotPasswordScreen() {
  const { resetPasswordForEmail } = useAuth();
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleReset() {
    setError(null);
    setMessage(null);
    setSubmitting(true);
    const result = await resetPasswordForEmail(email.trim());
    setSubmitting(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }

    setMessage('Reset email sent. Open the link on this device to set a new password.');
  }

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
          paddingVertical: authSpacing.lg,
        }}>
        {/* Logo */}
        <View style={{ alignItems: 'center', marginBottom: authSpacing.lg }}>
          <View
            style={{
              width: 96,
              height: 96,
              borderRadius: authRadius.md,
              backgroundColor: authColors.surfaceContainerLowest,
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: authSpacing.sm,
              shadowColor: authColors.primary,
              shadowOffset: { width: 0, height: 10 },
              shadowOpacity: 0.1,
              shadowRadius: 20,
              elevation: 4,
            }}>
            <Image
              source={require('../../../assets/images/fincoach-logo.png')}
              style={{ width: 76, height: 76 }}
              resizeMode="contain"
            />
          </View>
          <Text style={[authType.headline, { color: authColors.primary }]}>FinCoach</Text>
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
          <View style={{ marginBottom: authSpacing.lg }}>
            <Text style={[authType.displayTitle, { color: authColors.onSurface, marginBottom: authSpacing.unit }]}>
              Reset password
            </Text>
            <Text style={[authType.body, { color: authColors.onSurfaceVariant }]}>
              Recover access through your registered email.
            </Text>
          </View>

          <View style={{ gap: authSpacing.md }}>
            <View>
              <Text style={[authType.titleSm, { color: authColors.onSurface, marginBottom: authSpacing.unit, marginLeft: authSpacing.unit }]}>
                Email
              </Text>
              <TextInput
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                onChangeText={setEmail}
                placeholder="Enter email"
                placeholderTextColor={authColors.outline}
                style={resetInputStyle}
                value={email}
              />
            </View>

            {error ? <Text style={[authType.bodySm, { color: authColors.error }]}>{error}</Text> : null}
            {message ? <Text style={[authType.bodySm, { color: authColors.primary }]}>{message}</Text> : null}

            <Pressable
              disabled={submitting}
              onPress={handleReset}
              style={({ pressed }) => [resetPrimaryButtonStyle, pressed && { opacity: 0.9 }]}>
              {submitting ? (
                <ActivityIndicator color={authColors.onPrimary} />
              ) : (
                <Text style={[authType.titleSm, { color: authColors.onPrimary }]}>Send reset email</Text>
              )}
            </Pressable>
          </View>
        </View>

        {/* Footer */}
        <View style={{ alignItems: 'center', marginTop: authSpacing.lg }}>
          <Link href="/auth/login" style={[authType.bodySm, { color: authColors.primary, fontFamily: authFont.semibold }]}>
            Back to login
          </Link>
        </View>
      </ScrollView>
    </View>
  );
}

const resetInputStyle = {
  height: 48,
  borderRadius: authRadius.full,
  backgroundColor: authColors.surfaceContainerLow,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  paddingHorizontal: 20,
  fontSize: authType.body.fontSize,
  color: authColors.onSurface,
} as const;

const resetPrimaryButtonStyle = {
  height: 52,
  borderRadius: authRadius.full,
  backgroundColor: authColors.primary,
  alignItems: 'center',
  justifyContent: 'center',
  marginTop: authSpacing.sm,
} as const;
