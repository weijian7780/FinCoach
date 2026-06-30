import { AntDesign, MaterialIcons } from '@expo/vector-icons';
import { Link, router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { AuthBackdrop } from '@/components/ui/auth-backdrop';
import { authColors, authRadius, authSpacing, authType } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';

export default function SignUpScreen() {
  const { signInWithGoogle, signUpWithEmail } = useAuth();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleEmailSignup() {
    setError(null);
    setSubmitting(true);
    // Full name is collected on the profile setup screen that follows sign-up.
    const result = await signUpWithEmail(email.trim(), password, '');
    setSubmitting(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }

    if (result.requiresEmailConfirmation) {
      router.replace({ pathname: '/auth/check-email', params: { email: email.trim() } });
      return;
    }

    router.replace('/profile/setup');
  }

  async function handleGoogleSignup() {
    setError(null);
    setSubmitting(true);
    const result = await signInWithGoogle();
    setSubmitting(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }

    router.replace('/');
  }

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <AuthBackdrop color={authColors.primaryFixed} height={300} maxOpacity={0.9} />
      <ScrollView
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{
          flexGrow: 1,
          paddingHorizontal: authSpacing.container,
          paddingTop: insets.top + authSpacing.sm,
          paddingBottom: insets.bottom + authSpacing.sm,
        }}>
        {/* Header */}
        <View style={{ alignItems: 'center' }}>
          <View
            style={{
              width: 48,
              height: 48,
              borderRadius: authRadius.full,
              backgroundColor: authColors.surfaceContainerLowest,
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: authSpacing.md,
              shadowColor: authColors.primary,
              shadowOffset: { width: 0, height: 16 },
              shadowOpacity: 0.12,
              shadowRadius: 20,
              elevation: 4,
            }}>
            <MaterialIcons name="lock" size={22} color={authColors.onSurface} />
          </View>
          <Text style={[authType.displayTitle, { color: authColors.onSurface, textAlign: 'center' }]}>
            Get Started with FinCoach
          </Text>
          <Text
            style={[
              authType.body,
              { color: authColors.onSurfaceVariant, textAlign: 'center', marginTop: authSpacing.sm, maxWidth: 280 },
            ]}>
            Create your account in just a few steps.
          </Text>
        </View>

        {/* Form */}
        <View style={{ marginTop: authSpacing.md, gap: authSpacing.md }}>
          <View style={{ gap: authSpacing.unit }}>
            <Text style={[authType.labelCaps, { color: authColors.onSurface, marginLeft: authSpacing.md }]}>
              Email
            </Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="Enter email"
              placeholderTextColor={authColors.outline}
              style={inputStyle}
              value={email}
            />
          </View>

          <View style={{ gap: authSpacing.unit }}>
            <Text style={[authType.labelCaps, { color: authColors.onSurface, marginLeft: authSpacing.md }]}>
              Password
            </Text>
            <View style={{ position: 'relative', justifyContent: 'center' }}>
              <TextInput
                autoCapitalize="none"
                onChangeText={setPassword}
                placeholder="••••••••"
                placeholderTextColor={authColors.outline}
                secureTextEntry={!showPassword}
                style={[inputStyle, { paddingRight: 52 }]}
                value={password}
              />
              <Pressable
                hitSlop={8}
                onPress={() => setShowPassword((prev) => !prev)}
                style={{ position: 'absolute', right: 16, padding: 4 }}>
                <MaterialIcons
                  name={showPassword ? 'visibility' : 'visibility-off'}
                  size={22}
                  color={authColors.onSurfaceVariant}
                />
              </Pressable>
            </View>
          </View>

          {error ? <Text style={[authType.bodySm, { color: authColors.error }]}>{error}</Text> : null}

          <Pressable
            disabled={submitting}
            onPress={handleEmailSignup}
            style={({ pressed }) => [primaryButtonStyle, pressed && { opacity: 0.9 }]}>
            {submitting ? (
              <ActivityIndicator color={authColors.onPrimary} />
            ) : (
              <Text style={[authType.titleSm, { color: authColors.onPrimary }]}>Sign Up</Text>
            )}
          </Pressable>

          <View style={{ alignItems: 'center', marginTop: authSpacing.unit }}>
            <Text style={[authType.body, { color: authColors.onSurfaceVariant }]}>
              Already have an account?{' '}
              <Link href="/auth/login" style={[authType.titleSm, { color: authColors.primary }]}>
                Log In
              </Link>
            </Text>
          </View>
        </View>

        {/* Divider */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: authSpacing.md, marginTop: authSpacing.md }}>
          <View style={{ flex: 1, height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.5 }} />
          <Text style={[authType.labelCaps, { color: authColors.onSurfaceVariant }]}>Or</Text>
          <View style={{ flex: 1, height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.5 }} />
        </View>

        {/* Google */}
        <Pressable
          disabled={submitting}
          onPress={handleGoogleSignup}
          style={({ pressed }) => [googleButtonStyle, pressed && { opacity: 0.9 }]}>
          <AntDesign name="google" size={18} color="#4285F4" />
          <Text style={[authType.titleSm, { color: authColors.onSurface }]}>Google</Text>
        </Pressable>

        {/* Spacer pushes the footer to the bottom on tall screens */}
        <View style={{ flex: 1, minHeight: authSpacing.lg }} />

        {/* Footer */}
        <View style={{ alignItems: 'center', paddingTop: authSpacing.md }}>
          <Text
            style={[
              authType.bodySm,
              { color: authColors.onSurfaceVariant, textAlign: 'center', maxWidth: 290, lineHeight: 20 },
            ]}>
            By creating an account, you agree to our{' '}
            <Text style={{ color: authColors.primary }}>Terms &amp; Conditions</Text> and{' '}
            <Text style={{ color: authColors.primary }}>Privacy Policy</Text>
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const inputStyle = {
  height: 56,
  borderRadius: authRadius.full,
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  paddingHorizontal: 24,
  fontSize: authType.body.fontSize,
  color: authColors.onSurface,
} as const;

const primaryButtonStyle = {
  height: 56,
  borderRadius: authRadius.full,
  backgroundColor: authColors.primary,
  alignItems: 'center',
  justifyContent: 'center',
  marginTop: authSpacing.sm,
} as const;

const googleButtonStyle = {
  height: 56,
  borderRadius: authRadius.full,
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  flexDirection: 'row',
  alignItems: 'center',
  justifyContent: 'center',
  gap: authSpacing.sm,
  marginTop: authSpacing.md,
} as const;
