import { describe, expect, it } from 'vitest';

import {
  declinedSpendingConsentStatus,
  isSpendingConsentDeclined,
} from './spending-consent';

describe('spending record consent', () => {
  it('records an initial refusal as denied', () => {
    expect(declinedSpendingConsentStatus('unset')).toBe('denied');
  });

  it('records removal of existing permission as withdrawn', () => {
    expect(declinedSpendingConsentStatus('granted')).toBe('withdrawn');
  });

  it('treats denied and withdrawn as not allowed', () => {
    expect(isSpendingConsentDeclined('denied')).toBe(true);
    expect(isSpendingConsentDeclined('withdrawn')).toBe(true);
    expect(isSpendingConsentDeclined('granted')).toBe(false);
  });
});
