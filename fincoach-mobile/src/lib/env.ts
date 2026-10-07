import Constants from 'expo-constants';

export const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
export const supabasePublishableKey = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '';
export const googleAuthWebClientId = process.env.EXPO_PUBLIC_GOOGLE_AUTH_WEB_CLIENT_ID ?? '';
const expoDevHost = Constants.expoConfig?.hostUri?.split(':')[0] ?? '';
export const fincoachApiUrl = (process.env.EXPO_PUBLIC_FINCOACH_API_URL ?? (expoDevHost ? `http://${expoDevHost}:8000` : '')).replace(/\/$/, '');

export const isSupabaseConfigured =
  supabaseUrl.startsWith('https://') && supabasePublishableKey.length > 20;

export const isGoogleOAuthConfigured = googleAuthWebClientId.endsWith('.apps.googleusercontent.com');
