export const PROVIDER_CONSENT_VERSION = 'openrouter-free-v1';

export type SecureStoreAdapter = {
  getItemAsync: (key: string) => Promise<string | null>;
  setItemAsync: (key: string, value: string) => Promise<void>;
  deleteItemAsync: (key: string) => Promise<void>;
};

function providerConsentKey(userId: string) {
  return `fincoach.coach-provider-consent.${userId}`;
}

async function nativeStore(): Promise<SecureStoreAdapter> {
  return import('expo-secure-store');
}

export async function hasCurrentProviderConsent(
  userId: string,
  store?: SecureStoreAdapter,
): Promise<boolean> {
  const selectedStore = store ?? await nativeStore();
  return (await selectedStore.getItemAsync(providerConsentKey(userId))) === PROVIDER_CONSENT_VERSION;
}

export async function grantCurrentProviderConsent(
  userId: string,
  store?: SecureStoreAdapter,
): Promise<void> {
  const selectedStore = store ?? await nativeStore();
  await selectedStore.setItemAsync(providerConsentKey(userId), PROVIDER_CONSENT_VERSION);
}

export async function clearProviderConsent(
  userId: string,
  store?: SecureStoreAdapter,
): Promise<void> {
  const selectedStore = store ?? await nativeStore();
  await selectedStore.deleteItemAsync(providerConsentKey(userId));
}
