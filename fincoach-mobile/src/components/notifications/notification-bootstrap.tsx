import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import {
  ensureNotificationPreferences,
  refreshDeviceRegistration,
  registerDevice,
} from '@/lib/alerts';
import { appDialog } from '@/components/ui/app-dialog';
import { useAuth } from '@/lib/auth-context';
import {
  configureForegroundNotificationHandler,
  getCurrentExpoPushToken,
  loadNotificationSdk,
  registerForPushNotifications,
  routeFromNotificationResponse,
  setCurrentExpoPushToken,
  subscribeToNotificationEvents,
} from '@/lib/notification-platform';

function askForNotificationPermission(): Promise<boolean> {
  return new Promise((resolve) => {
    appDialog.open(
      'Stay on track with FinCoach',
      'Allow reminders for budgets, savings, spending records and bills. You can configure each type separately.',
      [
        { text: 'Not now', style: 'cancel', onPress: () => resolve(false) },
        { text: 'Allow notifications', onPress: () => resolve(true) },
      ],
      { cancelable: true, onDismiss: () => resolve(false) },
    );
  });
}

export function NotificationBootstrap() {
  const { session } = useAuth();
  const userId = session?.user.id ?? null;

  useEffect(() => {
    let disposed = false;
    let removeListeners: (() => void) | undefined;

    loadNotificationSdk()
      .then((sdk) => {
        if (disposed) return;
        configureForegroundNotificationHandler(sdk);

        const navigate = (response: unknown) => {
          router.push(routeFromNotificationResponse(response) as never);
        };
        removeListeners = subscribeToNotificationEvents(sdk, () => {}, navigate);

        const initialResponse = sdk.getLastNotificationResponse?.();
        if (initialResponse) navigate(initialResponse);
      })
      .catch(() => {
        // Native notification support becomes available after rebuilding the app binary.
      });

    return () => {
      disposed = true;
      removeListeners?.();
    };
  }, []);

  useEffect(() => {
    if (!userId) return;
    const signedInUserId = userId;

    let disposed = false;
    let promptedThisSession = false;
    const projectId =
      Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? '';
    const platform = process.env.EXPO_OS ?? 'android';

    async function synchronizeRegistration(allowPrompt: boolean) {
      try {
        await ensureNotificationPreferences(signedInUserId);
        const sdk = await loadNotificationSdk();
        let result = await registerForPushNotifications({
          sdk,
          platform,
          projectId,
          requestIfNeeded: false,
        });

        if (
          result.status === 'undetermined' &&
          allowPrompt &&
          !promptedThisSession &&
          !disposed
        ) {
          promptedThisSession = true;
          const accepted = await askForNotificationPermission();
          if (accepted) {
            result = await registerForPushNotifications({
              sdk,
              platform,
              projectId,
              requestIfNeeded: true,
            });
          }
        }

        if (!disposed && result.token) {
          await registerDevice(
            result.token,
            platform === 'ios' ? 'ios' : 'android',
            Device.modelName,
          );
          setCurrentExpoPushToken(result.token);
        }
      } catch (error) {
        console.warn('Notification registration will retry when FinCoach returns to foreground.', error);
      }
    }

    void synchronizeRegistration(true);
    const appState = AppState.addEventListener('change', (state) => {
      if (state !== 'active') return;
      const token = getCurrentExpoPushToken();
      if (token) {
        refreshDeviceRegistration(token).catch(() => void synchronizeRegistration(false));
      } else {
        void synchronizeRegistration(false);
      }
    });

    return () => {
      disposed = true;
      appState.remove();
    };
  }, [userId]);

  return null;
}
