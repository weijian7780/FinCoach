import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';

import { LoadingState } from '@/components/ui/loading-state';
import { supabase } from '@/lib/supabase';

export default function AuthCallbackScreen() {
  const { code } = useLocalSearchParams<{ code?: string }>();
  const [message, setMessage] = useState('Completing secure sign in');

  useEffect(() => {
    async function completeCallback() {
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        if (error) {
          setMessage(error.message);
          return;
        }
      }
      router.replace('/');
    }

    completeCallback();
  }, [code]);

  return <LoadingState label={message} />;
}
