import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { authColors } from '@/constants/auth-theme';
import { fetchUnreadAlertCount } from '@/lib/alerts';
import { useAuth } from '@/lib/auth-context';

export function NotificationBell({ filled = false }: { filled?: boolean }) {
  const { session } = useAuth();
  const userId = session?.user.id;
  const [unread, setUnread] = useState(0);

  const load = useCallback(async () => {
    if (!userId) return setUnread(0);
    try {
      setUnread(await fetchUnreadAlertCount(userId));
    } catch {
      // The inbox itself presents the recoverable error state.
    }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={unread ? `Open alerts, ${unread} unread` : 'Open alerts'}
      hitSlop={10}
      onPress={() => router.push('/alerts' as never)}
      style={({ pressed }) => [styles.button, pressed && { opacity: 0.65 }]}>
      <MaterialIcons name={filled ? 'notifications' : 'notifications-none'} size={24} color={authColors.onSurfaceVariant} />
      {unread > 0 ? <View style={styles.dot} /> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  dot: { position: 'absolute', top: 7, right: 7, width: 8, height: 8, borderRadius: 4, backgroundColor: authColors.error, borderWidth: 1.5, borderColor: authColors.surface },
});
