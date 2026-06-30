export const colors = {
  background: '#F6F7F2',
  border: '#D9E2DC',
  danger: '#DC2626',
  mutedText: '#64736D',
  onPrimary: '#FFFFFF',
  placeholder: '#8A9791',
  primary: '#087A5A',
  primaryDark: '#10231E',
  success: '#15803D',
  surface: '#FFFFFF',
  surfaceAlt: '#F1F5EF',
  text: '#10231E',
  warningText: '#9A3412',
};

export const spacing = {
  xs: 6,
  sm: 10,
  md: 14,
  lg: 22,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 6,
  md: 8,
  lg: 14,
  xl: 24,
  full: 999,
};

const fontFamily = process.env.EXPO_OS === 'web' ? 'Hanken Grotesk, system-ui, sans-serif' : undefined;

export const typography = {
  body: {
    color: colors.mutedText,
    fontFamily,
    fontSize: 16,
    lineHeight: 23,
  },
  bodyStrong: {
    color: colors.text,
    fontFamily,
    fontSize: 16,
    fontWeight: '700' as const,
    lineHeight: 22,
  },
  button: {
    fontFamily,
    fontSize: 16,
    fontWeight: '800' as const,
  },
  caption: {
    color: colors.mutedText,
    fontFamily,
    fontSize: 13,
    lineHeight: 18,
  },
  captionStrong: {
    color: colors.text,
    fontFamily,
    fontSize: 13,
    fontWeight: '700' as const,
    lineHeight: 18,
  },
  eyebrow: {
    color: colors.primary,
    fontFamily,
    fontSize: 13,
    fontWeight: '800' as const,
    letterSpacing: 0,
    textTransform: 'uppercase' as const,
  },
  heroTitle: {
    color: colors.text,
    fontFamily,
    fontSize: 34,
    fontWeight: '900' as const,
    letterSpacing: 0,
    lineHeight: 40,
  },
  label: {
    color: colors.text,
    fontFamily,
    fontSize: 14,
    fontWeight: '800' as const,
  },
  link: {
    color: colors.primary,
    fontFamily,
    fontSize: 16,
    fontWeight: '800' as const,
  },
  title: {
    color: colors.text,
    fontFamily,
    fontSize: 26,
    fontWeight: '900' as const,
    letterSpacing: 0,
    lineHeight: 32,
  },
};
