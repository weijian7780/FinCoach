import { describe, expect, it, vi } from 'vitest';

import {
  PROVIDER_CONSENT_VERSION,
  clearProviderConsent,
  grantCurrentProviderConsent,
  hasCurrentProviderConsent,
} from './coach-provider-consent';

const assertSecureStoreKey = (key: string) => {
  if (!/^[\w.-]+$/.test(key)) {
    throw new Error('Invalid SecureStore key');
  }
};

const createStore = (value: string | null = null) => ({
  getItemAsync: vi.fn(async (key: string) => {
    assertSecureStoreKey(key);
    return value;
  }),
  setItemAsync: vi.fn(async (key: string) => {
    assertSecureStoreKey(key);
  }),
  deleteItemAsync: vi.fn(async (key: string) => {
    assertSecureStoreKey(key);
  }),
});

describe('coach provider consent', () => {
  it('accepts only the current disclosure version for the signed-in user', async () => {
    const currentStore = createStore(PROVIDER_CONSENT_VERSION);

    await expect(hasCurrentProviderConsent('user-1', currentStore)).resolves.toBe(true);
    await expect(hasCurrentProviderConsent('user-1', createStore('openrouter-free-v0'))).resolves.toBe(false);

    expect(currentStore.getItemAsync).toHaveBeenCalledWith(
      'fincoach.coach-provider-consent.user-1',
    );
  });

  it('stores and withdraws consent in the user-scoped secure key', async () => {
    const store = createStore();

    await grantCurrentProviderConsent('user-1', store);
    await clearProviderConsent('user-1', store);

    expect(store.setItemAsync).toHaveBeenCalledWith(
      'fincoach.coach-provider-consent.user-1',
      PROVIDER_CONSENT_VERSION,
    );
    expect(store.deleteItemAsync).toHaveBeenCalledWith('fincoach.coach-provider-consent.user-1');
  });

  it('keeps consent isolated between signed-in users', async () => {
    const store = createStore();

    await grantCurrentProviderConsent('user-1', store);
    await grantCurrentProviderConsent('user-2', store);

    expect(store.setItemAsync).toHaveBeenNthCalledWith(
      1,
      'fincoach.coach-provider-consent.user-1',
      PROVIDER_CONSENT_VERSION,
    );
    expect(store.setItemAsync).toHaveBeenNthCalledWith(
      2,
      'fincoach.coach-provider-consent.user-2',
      PROVIDER_CONSENT_VERSION,
    );
  });
});
