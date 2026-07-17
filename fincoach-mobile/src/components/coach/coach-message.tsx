import { MaterialIcons } from '@expo/vector-icons';
import { View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { coachSourceLabel } from '@/lib/coach-ui';
import type { CoachMessage as CoachMessageType } from '@/lib/types';

export function CoachMessage({ message }: { message: CoachMessageType }) {
  const isAssistant = message.role === 'assistant';
  return (
    <View style={{ alignSelf: isAssistant ? 'flex-start' : 'flex-end', maxWidth: isAssistant ? '90%' : '84%' }}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
        {isAssistant ? (
          <View style={styles.avatar}>
            <MaterialIcons name="auto-awesome" size={15} color={authColors.onPrimary} />
          </View>
        ) : null}
        <View style={isAssistant ? styles.assistantBubble : styles.userBubble}>
          <Text
            selectable
            style={{
              color: isAssistant ? authColors.onSurface : authColors.onPrimary,
              fontFamily: authFont.regular,
              fontSize: 15,
              lineHeight: 22,
            }}>
            {message.content}
          </Text>
        </View>
      </View>
      {isAssistant && message.sources.length > 0 ? (
        <View style={styles.sources}>
          {message.sources.map((source) => {
            const label = coachSourceLabel(source);
            return label ? (
              <View key={`${source.rank}-${source.source ?? source.title}`} style={styles.sourceChip}>
                <MaterialIcons name="menu-book" size={13} color={authColors.primary} />
                <Text selectable style={styles.sourceText}>{label}</Text>
              </View>
            ) : null;
          })}
        </View>
      ) : null}
    </View>
  );
}

export function CoachTypingIndicator() {
  return (
    <View accessibilityLabel="FinCoach is typing" style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
      <View style={styles.avatar}><MaterialIcons name="auto-awesome" size={15} color={authColors.onPrimary} /></View>
      <View style={[styles.assistantBubble, { flexDirection: 'row', gap: 5, paddingVertical: 16 }]}>
        {[0, 1, 2].map((dot) => <View key={dot} style={styles.dot} />)}
      </View>
    </View>
  );
}

const styles = {
  avatar: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary } as const,
  assistantBubble: { borderRadius: 20, borderBottomLeftRadius: 6, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: authColors.surfaceContainerHigh, borderCurve: 'continuous' } as const,
  userBubble: { borderRadius: 20, borderBottomRightRadius: 6, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: authColors.primary, borderCurve: 'continuous' } as const,
  sources: { paddingLeft: 36, paddingTop: 7, flexDirection: 'row', flexWrap: 'wrap', gap: 6 } as const,
  sourceChip: { maxWidth: '100%', flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 12, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: authColors.primaryFixed } as const,
  sourceText: { flexShrink: 1, color: authColors.onPrimaryFixed, fontFamily: authFont.semibold, fontSize: 11, lineHeight: 15 } as const,
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: authColors.onSurfaceVariant } as const,
} as const;
