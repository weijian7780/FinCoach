import fs from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const root = path.resolve(__dirname, '..');

function read(...segments: string[]) {
  return fs.readFileSync(path.join(root, ...segments), 'utf8');
}

describe('Coach spending-consent placement', () => {
  it('keeps transaction consent out of profile setup and editing', () => {
    const editProfile = read('app', 'profile', 'edit.tsx');
    const setupProfile = read('app', 'profile', 'setup.tsx');

    expect(editProfile).not.toContain('ConsentSelector');
    expect(editProfile).not.toContain('AI COACH DATA CONSENT');
    expect(editProfile).not.toContain('spending_records_consent: spendingConsent');
    expect(setupProfile).not.toContain('ConsentSelector');
    expect(setupProfile).not.toContain('spending_records_consent: spendingConsent');
  });

  it('uses contextual Coach actions for initial and transaction-required prompts', () => {
    const selector = read('components', 'ui', 'consent-selector.tsx');
    const coach = read('components', 'coach', 'coach-screen.tsx');

    expect(selector).toContain("'Allow access'");
    expect(selector).toContain("'Not now'");
    expect(selector).toContain("'Allow and continue'");
    expect(selector).toContain("'Continue without data'");
    expect(coach).toContain('requiredForQuestion={Boolean(pendingConsentQuestion)}');
  });

  // Consent continuation is exercised through real React callbacks in
  // coach-screen.test.tsx, including structured choices and a chat change.
});
