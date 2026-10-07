import { MaterialIcons } from '@expo/vector-icons';
import { useMemo, useState } from 'react';
import { Animated, PanResponder, Pressable, StyleSheet, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import type { AlertRecord, NotificationType } from '@/lib/types';

type AlertCardProps = {
  alert: AlertRecord;
  onOpen: () => void;
  onDismiss: () => void;
};

const SWIPE_WIDTH = 88;

const visualByType: Record<NotificationType, { color: string; icon: keyof typeof MaterialIcons.glyphMap }> = {
  budget_warning: { color: '#BA1A1A', icon: 'warning-amber' },
  budget_exceeded: { color: '#BA1A1A', icon: 'error-outline' },
  savings_deadline: { color: '#F59E0B', icon: 'event' },
  savings_milestone: { color: '#06A96B', icon: 'emoji-events' },
  spending_reminder: { color: '#8B5CF6', icon: 'insights' },
  bill_reminder: { color: '#F59E0B', icon: 'schedule' },
};

function timeLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-MY', { hour: 'numeric', minute: '2-digit' }).format(date);
}

export function AlertCard({ alert, onOpen, onDismiss }: AlertCardProps) {
  const [translateX] = useState(() => new Animated.Value(0));
  const visual = visualByType[alert.type] ?? { color: authColors.primary, icon: 'notifications-none' as const };

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 8 && Math.abs(gesture.dx) > Math.abs(gesture.dy),
        onPanResponderGrant: () => {
          translateX.stopAnimation();
        },
        onPanResponderMove: (_, gesture) => {
          translateX.setValue(Math.max(-SWIPE_WIDTH, Math.min(0, gesture.dx)));
        },
        onPanResponderRelease: (_, gesture) => {
          if (gesture.dx <= -58) {
            Animated.timing(translateX, { toValue: -SWIPE_WIDTH, duration: 160, useNativeDriver: true }).start(onDismiss);
          } else {
            Animated.spring(translateX, { toValue: 0, useNativeDriver: true, speed: 24, bounciness: 0 }).start();
          }
        },
        onPanResponderTerminate: () => {
          Animated.spring(translateX, { toValue: 0, useNativeDriver: true }).start();
        },
      }),
    [onDismiss, translateX],
  );

  return (
    <View style={styles.shell}>
      <Pressable accessibilityLabel={`Dismiss ${alert.title}`} onPress={onDismiss} style={styles.deleteAction}>
        <MaterialIcons name="delete-outline" size={23} color="#FFFFFF" />
      </Pressable>
      <Animated.View style={{ transform: [{ translateX }] }} {...panResponder.panHandlers}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${alert.read_at ? '' : 'Unread '}${alert.title}`}
          onPress={onOpen}
          style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
          {alert.kind === 'insight' ? <View style={[styles.insightStripe, { backgroundColor: visual.color }]} /> : null}
          <View style={[styles.iconCircle, { backgroundColor: `${visual.color}1C` }]}>
            <MaterialIcons name={visual.icon} size={21} color={visual.color} />
          </View>
          <View style={styles.content}>
            <View style={styles.titleRow}>
              <View style={styles.titleWrap}>
                {!alert.read_at ? <View style={styles.unreadDot} /> : null}
                <Text numberOfLines={2} style={styles.title}>{alert.title}</Text>
              </View>
              <Text style={styles.time}>{timeLabel(alert.created_at)}</Text>
            </View>
            <Text style={styles.message}>{alert.message}</Text>
          </View>
        </Pressable>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { borderRadius: 22, overflow: 'hidden', backgroundColor: authColors.error },
  deleteAction: { position: 'absolute', top: 0, right: 0, bottom: 0, width: SWIPE_WIDTH, alignItems: 'center', justifyContent: 'center' },
  card: {
    minHeight: 92,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: authColors.outlineVariant,
    backgroundColor: authColors.surfaceContainerLowest,
    shadowColor: '#1B1B23',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 12,
    elevation: 2,
    overflow: 'hidden',
  },
  pressed: { opacity: 0.82 },
  insightStripe: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 6 },
  iconCircle: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  content: { flex: 1, gap: 5 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 },
  titleWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 7 },
  unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: authColors.primary },
  title: { flex: 1, fontFamily: authFont.semibold, fontSize: 15, lineHeight: 20, color: authColors.onSurface },
  time: { fontFamily: authFont.regular, fontSize: 11, lineHeight: 16, color: authColors.onSurfaceVariant },
  message: { fontFamily: authFont.regular, fontSize: 13, lineHeight: 18, color: authColors.onSurfaceVariant },
});
