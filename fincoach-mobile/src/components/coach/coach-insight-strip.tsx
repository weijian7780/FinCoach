import { MaterialCommunityIcons } from '@expo/vector-icons';
import { ScrollView, View, type TextStyle } from 'react-native';
import Animated, { FadeInUp, useReducedMotion } from 'react-native-reanimated';

import { AnimatedPressable } from '@/components/ui/animated-pressable';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import type { CoachInsightCard, CoachInsightTone } from '@/lib/coach-insights';
import { coachMotion } from '@/lib/coach-motion';

const TONE_STYLES = {
  critical: {
    backgroundColor: '#FFF0F0',
    borderColor: '#F6C5C5',
    foreground: authColors.error,
    icon: 'alert-circle-outline',
  },
  healthy: {
    backgroundColor: '#EAF8F2',
    borderColor: '#B9E6D2',
    foreground: '#087A55',
    icon: 'shield-check-outline',
  },
  neutral: {
    backgroundColor: authColors.primaryFixed,
    borderColor: authColors.primaryFixedDim,
    foreground: authColors.primary,
    icon: 'chart-line',
  },
  warning: {
    backgroundColor: '#FFF5DF',
    borderColor: '#F0D39A',
    foreground: '#9A5B00',
    icon: 'gauge',
  },
} as const satisfies Record<CoachInsightTone, {
  backgroundColor: string;
  borderColor: string;
  foreground: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
}>;

export function CoachInsightStrip({
  cards,
  loading,
  onSelect,
}: {
  cards: readonly CoachInsightCard[];
  loading: boolean;
  onSelect: (prompt: string) => void;
}) {
  const reduceMotion = useReducedMotion();
  if (!loading && cards.length === 0) return null;

  return (
    <View style={styles.container}>
      <View style={styles.headingRow}>
        <View>
          <Text style={styles.eyebrow}>YOUR SNAPSHOT</Text>
          <Text style={styles.heading}>Based on your recorded data</Text>
        </View>
        <MaterialCommunityIcons name="lock-check-outline" size={18} color={authColors.onSurfaceVariant} />
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}>
        {loading ? (
          [0, 1].map((index) => (
            <View accessibilityLabel="Loading financial insight" key={index} style={styles.skeletonCard}>
              <View style={styles.skeletonIcon} />
              <View style={styles.skeletonTitle} />
              <View style={styles.skeletonCopy} />
            </View>
          ))
        ) : (
          cards.map((card, index) => {
            const tone = TONE_STYLES[card.tone];
            return (
              <Animated.View
                entering={reduceMotion ? undefined : FadeInUp
                  .duration(coachMotion.messageEnterDuration)
                  .delay(Math.min(index, 2) * coachMotion.sourceStagger)}
                key={card.id}>
                <AnimatedPressable
                  accessibilityRole="button"
                  accessibilityLabel={`${card.title}. Ask FinCoach about this insight.`}
                  onPress={() => onSelect(card.prompt)}
                  style={[
                    styles.card,
                    {
                      backgroundColor: tone.backgroundColor,
                      borderColor: tone.borderColor,
                    },
                  ]}>
                  <View style={styles.cardTopRow}>
                    <View style={[styles.iconShell, { backgroundColor: authColors.surfaceContainerLowest }]}>
                      <MaterialCommunityIcons name={tone.icon} size={19} color={tone.foreground} />
                    </View>
                    <MaterialCommunityIcons name="arrow-top-right" size={18} color={tone.foreground} />
                  </View>
                  <Text selectable numberOfLines={2} style={[styles.cardTitle, { color: tone.foreground }]}>
                    {card.title}
                  </Text>
                  <Text selectable numberOfLines={2} style={styles.cardDetail}>{card.detail}</Text>
                </AnimatedPressable>
              </Animated.View>
            );
          })
        )}
      </ScrollView>
    </View>
  );
}

const styles = {
  container: { gap: 10, paddingBottom: 2 } as const,
  headingRow: { paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const,
  eyebrow: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 10, lineHeight: 14, letterSpacing: 0.8 } as const,
  heading: { color: authColors.onSurface, fontFamily: authFont.semibold, fontSize: 14, lineHeight: 19 } as const,
  row: { paddingHorizontal: 18, gap: 10 } as const,
  card: { width: 224, minHeight: 132, borderRadius: 18, borderWidth: 1, padding: 14, gap: 8, borderCurve: 'continuous' } as const,
  cardTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const,
  iconShell: { width: 34, height: 34, borderRadius: 12, alignItems: 'center', justifyContent: 'center' } as const,
  cardTitle: { fontFamily: authFont.bold, fontSize: 16, lineHeight: 20, fontVariant: ['tabular-nums'] as TextStyle['fontVariant'] } as const,
  cardDetail: { color: authColors.onSurfaceVariant, fontFamily: authFont.regular, fontSize: 12, lineHeight: 17, fontVariant: ['tabular-nums'] as TextStyle['fontVariant'] } as const,
  skeletonCard: { width: 224, minHeight: 132, borderRadius: 18, borderWidth: 1, borderColor: authColors.outlineVariant, padding: 14, gap: 11, backgroundColor: authColors.surfaceContainerLow } as const,
  skeletonIcon: { width: 34, height: 34, borderRadius: 12, backgroundColor: authColors.surfaceContainerHigh } as const,
  skeletonTitle: { width: '68%', height: 15, borderRadius: 8, backgroundColor: authColors.surfaceContainerHigh } as const,
  skeletonCopy: { width: '88%', height: 11, borderRadius: 6, backgroundColor: authColors.surfaceContainerHigh } as const,
} as const;
