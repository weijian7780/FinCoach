import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView } from 'react-native';

import { AppButton } from '@/components/ui/app-button';
import { AuthCard } from '@/components/ui/auth-card';
import { FormError } from '@/components/ui/form-error';
import { TextField } from '@/components/ui/text-field';
import { colors, spacing } from '@/constants/design';
import { supabase } from '@/lib/supabase';

export default function ResetPasswordScreen() {
  const { code } = useLocalSearchParams<{ code?: string }>();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!code) {
      return;
    }
    supabase.auth.exchangeCodeForSession(code).catch(() => {});
  }, [code]);

  async function handleUpdatePassword() {
    setError(null);
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setSubmitting(false);

    if (updateError) {
      setError(updateError.message);
      return;
    }

    router.replace('/');
  }

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={{
        flexGrow: 1,
        justifyContent: 'center',
        gap: spacing.lg,
        padding: spacing.lg,
        backgroundColor: colors.background,
      }}>
      <AuthCard title="Set new password" subtitle="Use a new password for this FinCoach account.">
        <TextField
          label="New password"
          onChangeText={setPassword}
          placeholder="Minimum 6 characters"
          secureTextEntry
          value={password}
        />
        <TextField
          label="Confirm new password"
          onChangeText={setConfirmPassword}
          placeholder="Repeat password"
          secureTextEntry
          value={confirmPassword}
        />
        <FormError message={error} />
        <AppButton label="Update password" loading={submitting} onPress={handleUpdatePassword} />
      </AuthCard>
    </ScrollView>
  );
}
