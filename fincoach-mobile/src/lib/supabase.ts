import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient, processLock } from '@supabase/supabase-js';
import 'react-native-url-polyfill/auto';

import { isSupabaseConfigured, supabasePublishableKey, supabaseUrl } from '@/lib/env';

const fallbackUrl = 'https://placeholder.supabase.co';
const fallbackKey = 'placeholder-publishable-key';

export const supabase = createClient(
  isSupabaseConfigured ? supabaseUrl : fallbackUrl,
  isSupabaseConfigured ? supabasePublishableKey : fallbackKey,
  {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: false,
      flowType: 'pkce',
      lock: processLock,
      persistSession: true,
      storage: AsyncStorage,
    },
  },
);
