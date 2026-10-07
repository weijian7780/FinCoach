import { useEffect, useState, type PropsWithChildren } from 'react';
import { ActivityIndicator, AppState, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import NetInfo from '@react-native-community/netinfo';
import { AppText } from '@/components/ui/app-text';
import { colors, radius, spacing } from '@/constants/design';
import { useAuth } from '@/lib/auth-context';
import { supabase } from '@/lib/supabase';

type Access = 'checking' | 'active' | 'suspended' | 'unavailable';

/** Unmount financial screens on suspension; server-side RLS remains the actual
 * access boundary. Legacy installations work until the access table is added. */
export function AccountAccessGate({ children }: PropsWithChildren) {
  const { session, signOut } = useAuth();
  const userId = session?.user.id;
  if (!userId) return children;
  // Keyed mounting resets all gate state when the signed-in identity changes.
  return <AccountAccessCheck key={userId} userId={userId} signOut={signOut}>{children}</AccountAccessCheck>;
}

function AccountAccessCheck({ children, userId, signOut }: PropsWithChildren<{ userId: string; signOut: () => Promise<void> }>) {
  const [access, setAccess] = useState<Access>('checking');
  const [retry, setRetry] = useState(0);
  const insets = useSafeAreaInsets();

  useEffect(() => {
    let disposed = false;
    let running = false;
    const check = async () => {
      if (running) return;
      running = true;
      try {
        const { data, error } = await supabase.from('account_access').select('status').eq('user_id', userId).maybeSingle();
        if (disposed) return;
        if (error?.code === 'PGRST205' || error?.code === '42P01') {
          // Backward compatibility only for an explicitly missing table. Other
          // errors never turn a missing/suspended account into an active one.
          setAccess('active');
        } else if (error) {
          const network = await NetInfo.fetch();
          if (!disposed) setAccess(previous => network.isConnected === false && previous === 'active' ? previous : 'unavailable');
        } else {
          setAccess(data?.status === 'active' ? 'active' : 'suspended');
        }
      } catch {
        if (!disposed) setAccess('unavailable');
      } finally { running = false; }
    };
    void check();
    const interval = setInterval(() => { void check(); }, 15000);
    const subscription = AppState.addEventListener('change', state => { if (state === 'active') void check(); });
    return () => { disposed = true; clearInterval(interval); subscription.remove(); };
  }, [userId, retry]);

  if (access === 'active') return children;
  return <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl }]}>
    <View style={styles.card}>
      {access === 'checking' ? <><ActivityIndicator color={colors.primary} /><AppText style={styles.title}>Checking account access</AppText></> : <>
        <AppText style={styles.title}>{access === 'suspended' ? 'Account suspended' : 'Account access unavailable'}</AppText>
        <AppText style={styles.body}>{access === 'suspended' ? 'Your FinCoach access has been suspended. Your financial records are preserved. Contact the administrator to restore access.' : 'FinCoach could not verify account access. Check your connection and try again.'}</AppText>
        <Pressable accessibilityRole="button" style={styles.button} onPress={() => { setAccess('checking'); setRetry(value => value + 1); }}><AppText style={styles.buttonText}>Check again</AppText></Pressable>
        <Pressable accessibilityRole="button" onPress={() => { void signOut(); }} style={styles.secondary}><AppText style={styles.link}>Sign out</AppText></Pressable>
      </>}
    </View>
  </ScrollView>;
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: spacing.lg, backgroundColor: colors.background },
  card: { backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.xl, gap: spacing.lg },
  title: { color: colors.text, fontSize: 24, fontWeight: '700', textAlign: 'center' },
  body: { color: colors.mutedText, fontSize: 15, lineHeight: 23, textAlign: 'center' },
  button: { backgroundColor: colors.primary, borderRadius: radius.lg, padding: spacing.md, alignItems: 'center' },
  buttonText: { color: colors.onPrimary, fontWeight: '700', fontSize: 15 },
  secondary: { padding: spacing.sm, alignItems: 'center' },
  link: { color: colors.primary, fontWeight: '700', fontSize: 15 },
});
