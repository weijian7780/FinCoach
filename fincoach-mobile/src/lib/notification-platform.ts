type PermissionStatus = 'granted' | 'denied' | 'undetermined';

type ListenerSubscription = { remove: () => void };

export type NotificationSdk = {
  AndroidImportance: { DEFAULT: number; HIGH: number };
  setNotificationChannelAsync: (
    id: string,
    options: Record<string, unknown>,
  ) => Promise<unknown>;
  getPermissionsAsync: () => Promise<{ status: string }>;
  requestPermissionsAsync: () => Promise<{ status: string }>;
  getExpoPushTokenAsync: (options: { projectId: string }) => Promise<{ data: string }>;
  addNotificationReceivedListener: (listener: (notification: unknown) => void) => ListenerSubscription;
  addNotificationResponseReceivedListener: (
    listener: (response: unknown) => void,
  ) => ListenerSubscription;
  setNotificationHandler?: (handler: {
    handleNotification: () => Promise<Record<string, boolean>>;
  }) => void;
  getLastNotificationResponse?: () => unknown;
};

export const FINCOACH_NOTIFICATION_CHANNELS = [
  { id: 'general', name: 'FinCoach updates', importance: 'DEFAULT' as const },
  { id: 'budget', name: 'Budget alerts', importance: 'HIGH' as const },
  { id: 'savings', name: 'Savings reminders', importance: 'DEFAULT' as const },
  { id: 'spending', name: 'Spending reminders', importance: 'DEFAULT' as const },
  { id: 'bills', name: 'Bill reminders', importance: 'HIGH' as const },
];

let currentExpoPushToken: string | null = null;

export function setCurrentExpoPushToken(token: string | null): void {
  currentExpoPushToken = token;
}

export function getCurrentExpoPushToken(): string | null {
  return currentExpoPushToken;
}

export async function loadNotificationSdk(): Promise<NotificationSdk> {
  return (await import('expo-notifications')) as unknown as NotificationSdk;
}

export async function configureAndroidNotificationChannels(
  sdk: NotificationSdk,
  platform: string,
): Promise<void> {
  if (platform !== 'android') return;

  for (const channel of FINCOACH_NOTIFICATION_CHANNELS) {
    await sdk.setNotificationChannelAsync(channel.id, {
      name: channel.name,
      importance: sdk.AndroidImportance[channel.importance],
      vibrationPattern: [0, 250, 150, 250],
      lightColor: '#4F46E5',
      showBadge: true,
    });
  }
}

function normalizePermissionStatus(status: string): PermissionStatus {
  if (status === 'granted' || status === 'denied') return status;
  return 'undetermined';
}

export async function registerForPushNotifications(input: {
  sdk: NotificationSdk;
  platform: string;
  projectId: string;
  requestIfNeeded?: boolean;
}): Promise<{ status: PermissionStatus; token: string | null }> {
  if (!input.projectId.trim()) throw new Error('EAS project ID is missing.');

  await configureAndroidNotificationChannels(input.sdk, input.platform);
  let status = normalizePermissionStatus((await input.sdk.getPermissionsAsync()).status);

  if (status === 'undetermined' && input.requestIfNeeded !== false) {
    status = normalizePermissionStatus((await input.sdk.requestPermissionsAsync()).status);
  }
  if (status !== 'granted') return { status, token: null };

  const token = await input.sdk.getExpoPushTokenAsync({ projectId: input.projectId });
  return { status, token: token.data };
}

export function configureForegroundNotificationHandler(sdk: NotificationSdk): void {
  sdk.setNotificationHandler?.({
    handleNotification: async () => ({
      shouldPlaySound: false,
      shouldSetBadge: true,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}

export function subscribeToNotificationEvents(
  sdk: NotificationSdk,
  onReceived: (notification: unknown) => void,
  onResponse: (response: unknown) => void,
): () => void {
  const received = sdk.addNotificationReceivedListener(onReceived);
  const response = sdk.addNotificationResponseReceivedListener(onResponse);
  return () => {
    received.remove();
    response.remove();
  };
}

export function routeFromNotificationResponse(response: unknown): string {
  const candidate = (
    response as {
      notification?: { request?: { content?: { data?: { url?: unknown } } } };
    } | null
  )?.notification?.request?.content?.data?.url;

  if (typeof candidate !== 'string' || !candidate.startsWith('/') || candidate.startsWith('//')) {
    return '/alerts';
  }

  const allowedPrefixes = ['/alerts', '/budget', '/savings/', '/transactions/manage'];
  return allowedPrefixes.some((prefix) => candidate.startsWith(prefix)) ? candidate : '/alerts';
}

export async function openNotificationSettings(
  openSettings?: () => Promise<unknown>,
): Promise<void> {
  if (openSettings) {
    await openSettings();
    return;
  }
  const linking = await import('expo-linking');
  await linking.openSettings();
}
