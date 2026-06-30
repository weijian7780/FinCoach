// Indigo design tokens extracted verbatim from the Stitch FinCoach mockups
// (stitch-export/04-sign-up, 05-set-pin, 06-login). These are scoped to the
// auth + onboarding flow on purpose: the rest of the app still uses the green
// palette in src/constants/design.ts. When the whole app is re-themed, fold
// these in.

export const authColors = {
  primary: '#4648d4',
  primaryContainer: '#6063ee',
  primaryFixed: '#e1e0ff',
  primaryFixedDim: '#c0c1ff',
  onPrimary: '#ffffff',
  onPrimaryFixed: '#07006c',
  surface: '#fcf8ff',
  surfaceContainerLowest: '#ffffff',
  surfaceContainerLow: '#f5f2fe',
  surfaceContainer: '#efecf8',
  surfaceContainerHigh: '#e9e6f3',
  surfaceVariant: '#e4e1ed',
  onSurface: '#1b1b23',
  onSurfaceVariant: '#464554',
  outline: '#767586',
  outlineVariant: '#c7c4d7',
  error: '#ba1a1a',
} as const;

// borderRadius: DEFAULT 1rem, lg 2rem, xl 3rem, full 9999px
export const authRadius = {
  md: 16,
  lg: 32,
  xl: 48,
  full: 9999,
} as const;

// spacing: unit 4, stack-sm 8, stack-md/gutter 16, stack-lg/container-padding 24
export const authSpacing = {
  unit: 4,
  sm: 8,
  md: 16,
  lg: 24,
  container: 24,
} as const;

// Hanken Grotesk (the Stitch design typeface), bundled via
// @expo-google-fonts/hanken-grotesk and loaded in app/_layout.tsx. Each weight
// is a separate font file, so we reference the family name per weight rather
// than relying on fontWeight (which RN does not synthesize reliably on Android).
export const authFont = {
  regular: 'HankenGrotesk_400Regular',
  semibold: 'HankenGrotesk_600SemiBold',
  bold: 'HankenGrotesk_700Bold',
} as const;

// fontSize tokens from the Stitch config. letterSpacing converted from em to px.
export const authType = {
  displayTitle: { fontSize: 28, lineHeight: 36, fontFamily: authFont.bold, letterSpacing: -0.5 },
  headline: { fontSize: 24, lineHeight: 32, fontFamily: authFont.semibold, letterSpacing: -0.2 },
  titleSm: { fontSize: 18, lineHeight: 24, fontFamily: authFont.semibold },
  body: { fontSize: 16, lineHeight: 24, fontFamily: authFont.regular },
  bodySm: { fontSize: 14, lineHeight: 20, fontFamily: authFont.regular },
  labelCaps: {
    fontSize: 12,
    lineHeight: 16,
    fontFamily: authFont.bold,
    letterSpacing: 0.6,
    textTransform: 'uppercase' as const,
  },
} as const;
