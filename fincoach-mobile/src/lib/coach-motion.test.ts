import { describe, expect, it } from 'vitest';

import {
  coachMotion,
  coachPressScale,
  coachTypingDotDelay,
} from './coach-motion';

describe('Coach motion rules', () => {
  it('keeps direct feedback animations below 300ms', () => {
    expect(coachMotion.tapDuration).toBeLessThan(300);
    expect(coachMotion.messageEnterDuration).toBeLessThan(300);
    expect(coachMotion.stateTransitionDuration).toBeLessThan(300);
  });

  it('compresses enabled controls but leaves disabled controls still', () => {
    expect(coachPressScale(true, false)).toBe(coachMotion.tapScale);
    expect(coachPressScale(false, false)).toBe(1);
    expect(coachPressScale(true, true)).toBe(1);
  });

  it('staggers the three typing dots in a predictable sequence', () => {
    expect([0, 1, 2].map(coachTypingDotDelay)).toEqual([
      0,
      coachMotion.typingDotStagger,
      coachMotion.typingDotStagger * 2,
    ]);
  });
});
