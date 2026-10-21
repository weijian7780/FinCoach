import type { ConsentStatus } from '@/lib/types';

export function declinedSpendingConsentStatus(current: ConsentStatus): ConsentStatus {
  return current === 'granted' ? 'withdrawn' : 'denied';
}

export function isSpendingConsentDeclined(value: ConsentStatus) {
  return value === 'denied' || value === 'withdrawn';
}
