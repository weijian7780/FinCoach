import { describe, expect, it, vi } from 'vitest';

import {
  FINCOACH_NOTIFICATION_CHANNELS,
  configureAndroidNotificationChannels,
  openNotificationSettings,
  routeFromNotificationResponse,
  registerForPushNotifications,
  subscribeToNotificationEvents,
} from './notification-platform';

function createSdk(permission: 'granted' | 'denied' | 'undetermined' = 'granted') {
  const removeReceived = vi.fn();
  const removeResponse = vi.fn();
  return {
    sdk: {
      AndroidImportance: { DEFAULT: 3, HIGH: 4 },
      setNotificationChannelAsync: vi.fn().mockResolvedValue(null),
      getPermissionsAsync: vi.fn().mockResolvedValue({ status: permission }),
      requestPermissionsAsync: vi.fn().mockResolvedValue({ status: 'granted' }),
      getExpoPushTokenAsync: vi.fn().mockResolvedValue({ data: 'ExponentPushToken[token]' }),
      addNotificationReceivedListener: vi.fn().mockReturnValue({ remove: removeReceived }),
      addNotificationResponseReceivedListener: vi.fn().mockReturnValue({ remove: removeResponse }),
    },
    removeReceived,
    removeResponse,
  };
}

describe('Android notification registration', () => {
  it('creates every FinCoach channel before checking permission', async () => {
    const { sdk } = createSdk();
    const order: string[] = [];
    sdk.setNotificationChannelAsync.mockImplementation(async (id: string) => {
      order.push(`channel:${id}`);
      return null;
    });
    sdk.getPermissionsAsync.mockImplementation(async () => {
      order.push('permission');
      return { status: 'granted' };
    });

    await registerForPushNotifications({
      sdk,
      platform: 'android',
      projectId: 'project-1',
      requestIfNeeded: true,
    });

    expect(sdk.setNotificationChannelAsync).toHaveBeenCalledTimes(
      FINCOACH_NOTIFICATION_CHANNELS.length,
    );
    expect(order.slice(0, FINCOACH_NOTIFICATION_CHANNELS.length)).toEqual(
      FINCOACH_NOTIFICATION_CHANNELS.map((channel) => `channel:${channel.id}`),
    );
    expect(order.at(-1)).toBe('permission');
  });

  it('requests permission only when the user has not decided', async () => {
    const { sdk } = createSdk('undetermined');
    await registerForPushNotifications({
      sdk,
      platform: 'android',
      projectId: 'project-1',
      requestIfNeeded: true,
    });
    expect(sdk.requestPermissionsAsync).toHaveBeenCalledOnce();
    expect(sdk.getExpoPushTokenAsync).toHaveBeenCalledWith({ projectId: 'project-1' });
  });

  it('does not request or fetch a token after denial', async () => {
    const { sdk } = createSdk('denied');
    await expect(
      registerForPushNotifications({
        sdk,
        platform: 'android',
        projectId: 'project-1',
        requestIfNeeded: true,
      }),
    ).resolves.toEqual({ status: 'denied', token: null });
    expect(sdk.requestPermissionsAsync).not.toHaveBeenCalled();
    expect(sdk.getExpoPushTokenAsync).not.toHaveBeenCalled();
  });

  it('returns undetermined without prompting when explanation was declined', async () => {
    const { sdk } = createSdk('undetermined');
    await expect(
      registerForPushNotifications({
        sdk,
        platform: 'android',
        projectId: 'project-1',
        requestIfNeeded: false,
      }),
    ).resolves.toEqual({ status: 'undetermined', token: null });
    expect(sdk.requestPermissionsAsync).not.toHaveBeenCalled();
  });

  it('rejects token registration when the EAS project id is missing', async () => {
    const { sdk } = createSdk();
    await expect(
      registerForPushNotifications({ sdk, platform: 'android', projectId: '' }),
    ).rejects.toThrow('EAS project ID is missing.');
  });

  it('does not create Android channels on other platforms', async () => {
    const { sdk } = createSdk();
    await configureAndroidNotificationChannels(sdk, 'ios');
    expect(sdk.setNotificationChannelAsync).not.toHaveBeenCalled();
  });
});

describe('notification listeners and settings', () => {
  it('accepts only internal notification routes', () => {
    expect(
      routeFromNotificationResponse({
        notification: { request: { content: { data: { url: '/budget?month=2026-07-01' } } } },
      }),
    ).toBe('/budget?month=2026-07-01');
    expect(
      routeFromNotificationResponse({
        notification: { request: { content: { data: { url: 'https://evil.example' } } } },
      }),
    ).toBe('/alerts');
    expect(routeFromNotificationResponse(null)).toBe('/alerts');
  });

  it('subscribes and removes both notification listeners', () => {
    const { sdk, removeReceived, removeResponse } = createSdk();
    const cleanup = subscribeToNotificationEvents(sdk, vi.fn(), vi.fn());
    expect(sdk.addNotificationReceivedListener).toHaveBeenCalledOnce();
    expect(sdk.addNotificationResponseReceivedListener).toHaveBeenCalledOnce();
    cleanup();
    expect(removeReceived).toHaveBeenCalledOnce();
    expect(removeResponse).toHaveBeenCalledOnce();
  });

  it('opens Android application settings through an injected native action', async () => {
    const openSettings = vi.fn().mockResolvedValue(undefined);
    await openNotificationSettings(openSettings);
    expect(openSettings).toHaveBeenCalledOnce();
  });
});
