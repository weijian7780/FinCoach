import { GoogleSignin } from '@react-native-google-signin/google-signin';
import type { Session } from '@supabase/supabase-js';
import * as Linking from 'expo-linking';
import { makeRedirectUri } from 'expo-auth-session';
import * as WebBrowser from 'expo-web-browser';
import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react';
import { AppState } from 'react-native';

import { deactivateDevice } from '@/lib/alerts';
import { runEligibleAutomaticBackup } from '@/lib/backup-orchestrator';
import { googleAuthWebClientId, isGoogleOAuthConfigured, isSupabaseConfigured } from '@/lib/env';
import { getCurrentExpoPushToken, setCurrentExpoPushToken } from '@/lib/notification-platform';
import { ensureProfile, fetchProfile, updateProfileRow } from '@/lib/profile';
import { supabase } from '@/lib/supabase';
import type { Profile, ProfileUpdate } from '@/lib/types';

WebBrowser.maybeCompleteAuthSession();

if (isGoogleOAuthConfigured) {
  // webClientId is the Google "Web application" OAuth client. The native Android
  // client (matched by package name + SHA-1) is trusted automatically by Google;
  // the ID token Google returns is addressed to this web client, and Supabase
  // validates it against the same id listed under Authentication > Providers > Google.
  GoogleSignin.configure({ webClientId: googleAuthWebClientId });
}

type ActionResult = { ok: true; requiresEmailConfirmation?: boolean } | { ok: false; message: string };

type AuthContextValue = {
  loading: boolean;
  profile: Profile | null;
  refreshProfile: () => Promise<void>;
  resetPasswordForEmail: (email: string) => Promise<ActionResult>;
  session: Session | null;
  signInWithEmail: (email: string, password: string) => Promise<ActionResult>;
  signInWithGoogle: () => Promise<ActionResult>;
  signOut: () => Promise<void>;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<ActionResult>;
  updateProfile: (patch: ProfileUpdate) => Promise<ActionResult>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function requireSupabase() {
  if (!isSupabaseConfigured) {
    return 'Missing EXPO_PUBLIC_SUPABASE_URL or EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.';
  }
  return null;
}

function getAuthRedirect(path: string) {
  return makeRedirectUri({
    native: Linking.createURL(path),
    path,
  });
}

// Which auth providers an email is already registered under (e.g. ['email'], ['google']).
// Used to prompt the user to sign in with their original method (account-collision pattern #2).
async function fetchAuthMethods(email: string): Promise<string[]> {
  const { data, error } = await supabase.rpc('auth_methods_for_email', {
    p_email: email.trim().toLowerCase(),
  });
  if (error) throw error;
  return (data as string[] | null) ?? [];
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [session, setSession] = useState<Session | null>(null);

  const refreshProfile = useCallback(async () => {
    // getSession() only reads the locally-cached token; it never proves the token is
    // still valid. So we revalidate against the auth server with getUser() before
    // touching the profile. This is the single guard against stale sessions (project
    // switched, user deleted, token revoked) instead of reacting to a downstream FK error.
    const { data: cached } = await supabase.auth.getSession();
    if (!cached.session) {
      setSession(null);
      setProfile(null);
      return;
    }

    const { data: verified, error } = await supabase.auth.getUser();
    const status = (error as { status?: number } | null)?.status;

    if (status && status >= 400 && status < 500) {
      // The server rejected the token (invalid / expired / user no longer exists).
      // This is the only case where we clear the session.
      await supabase.auth.signOut({ scope: 'local' });
      setSession(null);
      setProfile(null);
      return;
    }

    if (error || !verified.user) {
      // Transient failure (offline, server hiccup) — keep the cached session and try
      // again later. Never sign the user out just because the network is down.
      setSession(cached.session);
      return;
    }

    // User is confirmed to exist in this project, so the profiles FK is guaranteed safe.
    setSession(cached.session);
    try {
      const ensured = await ensureProfile(verified.user);
      setProfile(ensured);
    } catch (caught) {
      // User is valid; a profile-load failure here is transient (network/RLS), not a
      // bad session — surface nothing destructive, leave profile for the next refresh.
      console.warn('Profile load failed for a valid user; will retry.', caught);
    }
  }, []);

  useEffect(() => {
    // Authentication bootstrap intentionally hydrates provider state from Supabase.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshProfile().finally(() => setLoading(false));

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (!nextSession) {
        setProfile(null);
        return;
      }
      fetchProfile(nextSession.user.id).then(setProfile).catch(() => {});
    });

    const appStateSubscription = AppState.addEventListener('change', (state) => {
      // Supabase recommends pausing token refresh when React Native is backgrounded.
      if (state === 'active') {
        supabase.auth.startAutoRefresh();
      } else {
        supabase.auth.stopAutoRefresh();
      }
    });

    return () => {
      data.subscription.unsubscribe();
      appStateSubscription.remove();
    };
  }, [refreshProfile]);

  useEffect(() => {
    const userId = session?.user.id;
    if (!userId) return;

    const run = () => {
      void runEligibleAutomaticBackup(userId).catch((error) => {
        // Backup failure is persisted by the orchestrator and must never block login.
        console.warn('Automatic backup will retry after the next eligible foreground session.', error);
      });
    };

    run();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') run();
    });
    return () => subscription.remove();
  }, [session?.user.id]);

  const signUpWithEmail = useCallback(
    async (email: string, password: string, fullName: string): Promise<ActionResult> => {
      const setupError = requireSupabase();
      if (setupError) {
        return { ok: false, message: setupError };
      }

      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { full_name: fullName },
          emailRedirectTo: getAuthRedirect('/auth/callback'),
        },
      });

      if (error) {
        return { ok: false, message: error.message };
      }

      // Supabase hides "email already registered" to prevent email enumeration: instead
      // of an error it returns a user with an EMPTY identities array (and no session).
      // Detect that so we warn the user to log in, rather than the misleading "check your email".
      if (data.user && (data.user.identities?.length ?? 0) === 0) {
        let message = 'This email is already registered. Please log in instead.';
        try {
          const methods = await fetchAuthMethods(email);
          if (methods.includes('google') && !methods.includes('email')) {
            message = 'This email is registered with Google. Please continue with Google.';
          }
        } catch {
          // Keep the generic message if the lookup fails.
        }
        return { ok: false, message };
      }

      if (!data.session) {
        return { ok: true, requiresEmailConfirmation: true };
      }

      await refreshProfile();
      return { ok: true };
    },
    [refreshProfile],
  );

  const signInWithEmail = useCallback(
    async (email: string, password: string): Promise<ActionResult> => {
      const setupError = requireSupabase();
      if (setupError) {
        return { ok: false, message: setupError };
      }

      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) {
        let message = error.message;
        try {
          const methods = await fetchAuthMethods(email);
          if (methods.includes('google') && !methods.includes('email')) {
            message = 'This email is registered with Google. Please continue with Google.';
          }
        } catch {
          // Keep the original error if the lookup fails.
        }
        return { ok: false, message };
      }

      await refreshProfile();
      return { ok: true };
    },
    [refreshProfile],
  );

  const signInWithGoogle = useCallback(async (): Promise<ActionResult> => {
    const setupError = requireSupabase();
    if (setupError) {
      return { ok: false, message: setupError };
    }
    if (!isGoogleOAuthConfigured) {
      return { ok: false, message: 'Missing EXPO_PUBLIC_GOOGLE_AUTH_WEB_CLIENT_ID.' };
    }

    try {
      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
      // Clear the cached account so the picker always lets the user choose.
      await GoogleSignin.signOut();
      const response = await GoogleSignin.signIn();

      if (response.type === 'cancelled' || !response.data?.idToken) {
        return { ok: false, message: 'Google sign in was cancelled.' };
      }

      // Account-collision pattern #2: if this email already has a password account but no
      // Google identity, don't silently create/link — ask them to use their original method.
      const googleEmail = response.data.user?.email;
      if (googleEmail) {
        try {
          const methods = await fetchAuthMethods(googleEmail);
          if (methods.includes('email') && !methods.includes('google')) {
            return {
              ok: false,
              message: 'You already have an account with this email. Please sign in with your email and password.',
            };
          }
        } catch {
          // If the lookup fails, fall through and let normal sign-in proceed.
        }
      }

      const { error } = await supabase.auth.signInWithIdToken({
        provider: 'google',
        token: response.data.idToken,
      });

      if (error) {
        return { ok: false, message: error.message };
      }

      await refreshProfile();
      return { ok: true };
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Google sign in failed.';
      return { ok: false, message };
    }
  }, [refreshProfile]);

  const resetPasswordForEmail = useCallback(async (email: string): Promise<ActionResult> => {
    const setupError = requireSupabase();
    if (setupError) {
      return { ok: false, message: setupError };
    }

    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: getAuthRedirect('/auth/reset-password'),
    });
    return error ? { ok: false, message: error.message } : { ok: true };
  }, []);

  const updateProfile = useCallback(
    async (patch: ProfileUpdate): Promise<ActionResult> => {
      if (!session?.user.id) {
        return { ok: false, message: 'No active session found.' };
      }

      const { data, error } = await updateProfileRow(session.user.id, patch);
      if (error) {
        return { ok: false, message: error.message };
      }

      setProfile(data);
      return { ok: true };
    },
    [session],
  );

  const signOut = useCallback(async () => {
    const pushToken = getCurrentExpoPushToken();
    if (pushToken) {
      await deactivateDevice(pushToken).catch(() => {
        // Logout must still complete while offline; token reassignment is also enforced on next login.
      });
    }
    await supabase.auth.signOut();
    setCurrentExpoPushToken(null);
    setProfile(null);
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({
      loading,
      profile,
      refreshProfile,
      resetPasswordForEmail,
      session,
      signInWithEmail,
      signInWithGoogle,
      signOut,
      signUpWithEmail,
      updateProfile,
    }),
    [
      loading,
      profile,
      refreshProfile,
      resetPasswordForEmail,
      session,
      signInWithEmail,
      signInWithGoogle,
      signOut,
      signUpWithEmail,
      updateProfile,
    ],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const context = use(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider.');
  }
  return context;
}
