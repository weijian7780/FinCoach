export const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
export const supabasePublishableKey = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '';
export const googleAuthWebClientId = process.env.EXPO_PUBLIC_GOOGLE_AUTH_WEB_CLIENT_ID ?? '';

export const isSupabaseConfigured =
  supabaseUrl.startsWith('https://') && supabasePublishableKey.length > 20;

export const isGoogleOAuthConfigured = googleAuthWebClientId.endsWith('.apps.googleusercontent.com');
