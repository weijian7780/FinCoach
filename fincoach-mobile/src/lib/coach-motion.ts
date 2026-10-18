export const coachMotion = {
  tapScale: 0.96,
  tapDuration: 90,
  messageEnterDuration: 190,
  stateTransitionDuration: 200,
  sourceStagger: 45,
  typingDotStagger: 140,
  typingDotTravelDuration: 420,
  springDamping: 18,
  springStiffness: 240,
} as const;

export function coachPressScale(pressed: boolean, disabled: boolean): number {
  if (disabled) return 1;
  return pressed ? coachMotion.tapScale : 1;
}

export function coachTypingDotDelay(index: number): number {
  return Math.max(0, index) * coachMotion.typingDotStagger;
}
