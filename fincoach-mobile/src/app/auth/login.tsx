import { AntDesign, MaterialIcons } from '@expo/vector-icons';
import { Link, router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { AuthBackdrop } from '@/components/ui/auth-backdrop';
import { authColors, authFont, authRadius, authSpacing, authType } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';

export default function LoginScreen() {
  const { signInWithEmail, signInWithGoogle } = useAuth();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleEmailLogin() {
    setError(null);
    setSubmitting(true);
    const result = await signInWithEmail(email.trim(), password);
    setSubmitting(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }

    router.replace('/');
  }

  async function handleGoogleLogin() {
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
      <AuthBackdrop color={authColors.primaryFixedDim} height={360} maxOpacity={0.4} />
      <ScrollView
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: 'center',
          paddingHorizontal: authSpacing.container,
          paddingTop: insets.top + authSpacing.sm,
          paddingBottom: insets.bottom + authSpacing.sm,
        }}>
        {/* Logo */}
        <View style={{ alignItems: 'center', marginBottom: authSpacing.md }}>
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
          <View style={{ marginBottom: authSpacing.md }}>
            <Text style={[authType.displayTitle, { color: authColors.onSurface, marginBottom: authSpacing.unit }]}>
              Welcome Back
            </Text>
            <Text style={[authType.body, { color: authColors.onSurfaceVariant }]}>
              Log in to continue managing your money.
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
                style={loginInputStyle}
                value={email}
              />
            </View>

            <View>
              <Text style={[authType.titleSm, { color: authColors.onSurface, marginBottom: authSpacing.unit, marginLeft: authSpacing.unit }]}>
                Password
              </Text>
              <View style={{ position: 'relative', justifyContent: 'center' }}>
                <TextInput
                  autoCapitalize="none"
                  onChangeText={setPassword}
                  placeholder="Enter password"
                  placeholderTextColor={authColors.outline}
                  secureTextEntry={!showPassword}
                  style={[loginInputStyle, { paddingRight: 48 }]}
                  value={password}
                />
                <Pressable
                  hitSlop={8}
                  onPress={() => setShowPassword((prev) => !prev)}
                  style={{ position: 'absolute', right: 14, padding: 4 }}>
                  <MaterialIcons
                    name={showPassword ? 'visibility' : 'visibility-off'}
                    size={22}
                    color={authColors.outline}
                  />
                </Pressable>
              </View>
            </View>

            <View style={{ alignItems: 'flex-end' }}>
              <Link href="/auth/forgot-password" style={[authType.bodySm, { color: authColors.primary }]}>
                Forgot password?
              </Link>
            </View>

            {error ? <Text style={[authType.bodySm, { color: authColors.error }]}>{error}</Text> : null}

            <Pressable
              disabled={submitting}
              onPress={handleEmailLogin}
              style={({ pressed }) => [loginPrimaryButtonStyle, pressed && { opacity: 0.9 }]}>
              {submitting ? (
                <ActivityIndicator color={authColors.onPrimary} />
              ) : (
                <Text style={[authType.titleSm, { color: authColors.onPrimary }]}>Log In</Text>
              )}
            </Pressable>
          </View>

          {/* Divider */}
          <View style={{ flexDirection: 'row', alignItems: 'center', marginVertical: authSpacing.lg }}>
            <View style={{ flex: 1, height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.5 }} />
            <Text style={[authType.bodySm, { color: authColors.onSurfaceVariant, paddingHorizontal: 12 }]}>Or</Text>
            <View style={{ flex: 1, height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.5 }} />
          </View>

          {/* Google */}
          <Pressable
            disabled={submitting}
            onPress={handleGoogleLogin}
            style={({ pressed }) => [loginGoogleButtonStyle, pressed && { opacity: 0.9 }]}>
            <AntDesign name="google" size={18} color="#4285F4" />
            <Text style={[authType.bodySm, { color: authColors.onSurface, fontFamily: authFont.semibold }]}>Google</Text>
          </Pressable>
        </View>

        {/* Footer */}
        <View style={{ alignItems: 'center', marginTop: authSpacing.lg }}>
          <Text style={[authType.bodySm, { color: authColors.onSurfaceVariant }]}>
            Don&apos;t have an account?{' '}
            <Link href="/auth/sign-up" style={[authType.bodySm, { color: authColors.primary, fontFamily: authFont.semibold }]}>
              Sign Up
            </Link>
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const loginInputStyle = {
  height: 48,
  borderRadius: authRadius.full,
  backgroundColor: authColors.surfaceContainerLow,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  paddingHorizontal: 20,
  fontSize: authType.body.fontSize,
  color: authColors.onSurface,
} as const;

const loginPrimaryButtonStyle = {
  height: 52,
  borderRadius: authRadius.full,
  backgroundColor: authColors.primary,
  alignItems: 'center',
  justifyContent: 'center',
  marginTop: authSpacing.sm,
} as const;

const loginGoogleButtonStyle = {
  height: 48,
  borderRadius: authRadius.full,
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  flexDirection: 'row',
  alignItems: 'center',
  justifyContent: 'center',
  gap: authSpacing.sm,
} as const;
