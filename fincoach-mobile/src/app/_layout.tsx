import {
  HankenGrotesk_400Regular,
  HankenGrotesk_600SemiBold,
  HankenGrotesk_700Bold,
  useFonts,
} from '@expo-google-fonts/hanken-grotesk';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { NotificationBootstrap } from '@/components/notifications/notification-bootstrap';
import { AppDialogProvider } from '@/components/ui/app-dialog';
import { AuthProvider } from '@/lib/auth-context';
import { AccountAccessGate } from '@/components/account-access-gate';

SplashScreen.preventAutoHideAsync().catch(() => {
  // The splash screen may already be hidden during fast refresh.
});

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [fontsLoaded] = useFonts({
    HankenGrotesk_400Regular,
    HankenGrotesk_600SemiBold,
    HankenGrotesk_700Bold,
  });

  useEffect(() => {
    if (fontsLoaded) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <AuthProvider>
          <AppDialogProvider>
            <AccountAccessGate>
            <NotificationBootstrap />
            <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: '#F6F7F2' },
            }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="onboarding/index" />
            <Stack.Screen name="auth/login" />
            <Stack.Screen name="auth/sign-up" />
            <Stack.Screen name="auth/forgot-password" />
            <Stack.Screen name="auth/reset-password" />
            <Stack.Screen name="auth/check-email" />
            <Stack.Screen name="auth/callback" />
            <Stack.Screen name="profile/setup" />
            <Stack.Screen name="savings/index" />
            <Stack.Screen name="savings/manage" />
            <Stack.Screen name="savings/[goalId]" />
            <Stack.Screen name="budget/manage" />
            <Stack.Screen name="budget/categories" />
            <Stack.Screen name="transactions/manage" />
            <Stack.Screen name="transactions/scan" />
            <Stack.Screen name="transactions/review" />
            <Stack.Screen name="transactions/[transactionId]" />
            <Stack.Screen name="alerts/index" />
            <Stack.Screen name="alerts/settings" />
            <Stack.Screen name="alerts/reminders" />
            <Stack.Screen name="alerts/reminders/manage" />
            <Stack.Screen name="export-backup/index" />
            <Stack.Screen name="export-backup/success" />
            <Stack.Screen name="export-backup/restore" />
            <Stack.Screen name="coach/history" />
            <Stack.Screen name="(app)" />
            </Stack>
            </AccountAccessGate>
          </AppDialogProvider>
        </AuthProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
