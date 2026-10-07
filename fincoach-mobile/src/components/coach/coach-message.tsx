import { MaterialCommunityIcons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { memo, useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';
import Animated, {
  cancelAnimation,
  FadeIn,
  FadeInUp,
  FadeOut,
  LinearTransition,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import {
  CoachActionCard,
  CoachClarificationCard,
} from '@/components/coach/coach-interaction-card';
import { AnimatedPressable } from '@/components/ui/animated-pressable';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { coachMotion, coachTypingDotDelay } from '@/lib/coach-motion';
import {
  isCoachAction,
  isCoachChoices,
  isCoachClarification,
  isCoachReadClarification,
} from '@/lib/coach-agent';
import {
  coachFollowUpChips,
  coachSourceDisclosure,
  coachSourceLabel,
  nextCoachFeedback,
  parseCoachMarkdown,
  parseCoachResponseSections,
  type CoachFeedback,
  type CoachResponseSection,
} from '@/lib/coach-ui';
import type {
  CoachInteractionReply,
  CoachMessage as CoachMessageType,
} from '@/lib/types';

function CoachMessageView({
  feedbackDisabled,
  message,
  onFeedback,
  onFollowUp,
  onActionCancel,
  onActionChange,
  onActionConfirm,
  showFollowUps,
}: {
  feedbackDisabled: boolean;
  message: CoachMessageType;
  onFeedback: (messageId: string, feedback: CoachFeedback | null) => Promise<void>;
  onFollowUp: (prompt: string, interactionReply?: CoachInteractionReply) => void;
  onActionCancel: (message: CoachMessageType) => void;
  onActionChange: (message: CoachMessageType) => void;
  onActionConfirm: (message: CoachMessageType) => void;
  showFollowUps: boolean;
}) {
  const isAssistant = message.role === 'assistant';
  const reduceMotion = useReducedMotion();
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  // Parsing is pure but not free: it splits and scans the whole response. The
  // list can hold dozens of messages, so cache per message rather than re-parsing
  // on every keystroke-driven re-render of the screen.
  const responseSections = useMemo(
    () => parseCoachResponseSections(message.content),
    [message.content],
  );
  const followUps = useMemo(
    () => (message.role === 'assistant' ? coachFollowUpChips(message.ui_payload) : []),
    [message.ui_payload, message.role],
  );
  const sourceDisclosure = coachSourceDisclosure(message.sources.length, sourcesExpanded);
  // Read questions reuse the clarification card; a write action never does.
  const clarification = isCoachClarification(message.ui_payload)
    ? message.ui_payload
    : isCoachReadClarification(message.ui_payload)
      ? message.ui_payload
      : null;
  const action = isCoachAction(message.ui_payload) ? message.ui_payload : null;
  // LLM-offered choice cards: tapping one submits its saved query as a new
  // request, resolved server-side by option id (never a resume of state).
  const choices = isCoachChoices(message.ui_payload) ? message.ui_payload.options : [];

  useEffect(() => {
    if (!copied) return;
    const timeout = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timeout);
  }, [copied]);

  const copyResponse = async () => {
    try {
      await Clipboard.setStringAsync(message.content);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const saveFeedback = async (selected: CoachFeedback) => {
    setFeedbackSaving(true);
    try {
      await onFeedback(message.id, nextCoachFeedback(message.feedback, selected));
    } catch {
      // The parent surfaces one privacy-safe API error above the composer.
    } finally {
      setFeedbackSaving(false);
    }
  };

  return (
    <Animated.View
      entering={reduceMotion ? undefined : FadeInUp.duration(coachMotion.messageEnterDuration)}
      layout={reduceMotion ? undefined : LinearTransition.duration(coachMotion.stateTransitionDuration)}
      style={{ alignSelf: isAssistant ? 'flex-start' : 'flex-end', maxWidth: isAssistant ? '90%' : '84%' }}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
        {isAssistant ? (
          <View style={styles.avatar}>
            <MaterialCommunityIcons name="creation" size={16} color={authColors.onPrimary} />
          </View>
        ) : null}
        <View style={isAssistant ? styles.assistantBubble : styles.userBubble}>
          {isAssistant ? (
            <View style={styles.responseSections}>
              {responseSections.map((section, index) => (
                <CoachResponseSectionView
                  key={`${section.kind}-${index}`}
                  section={section}
                  showDivider={index < responseSections.length - 1}
                />
              ))}
            </View>
          ) : (
            <CoachRichText content={message.content} color={authColors.onPrimary} />
          )}
        </View>
      </View>
      {isAssistant && clarification ? (
        <CoachClarificationCard
          disabled={feedbackDisabled}
          onReply={(reply) => onFollowUp(reply.content, {
            assistant_message_id: message.id,
            value: reply.value,
          })}
          payload={clarification}
        />
      ) : null}
      {isAssistant && action ? (
        <CoachActionCard
          busy={feedbackDisabled}
          onCancel={() => onActionCancel(message)}
          onChange={() => onActionChange(message)}
          onConfirm={() => onActionConfirm(message)}
          payload={action}
        />
      ) : null}
      {isAssistant ? (
        <View style={styles.utilityBar}>
          <AnimatedPressable
            accessibilityRole="button"
            accessibilityLabel={copied ? 'Response copied' : 'Copy response'}
            hitSlop={4}
            onPress={() => void copyResponse()}
            style={[styles.utilityAction, copied ? styles.utilityActionSelected : null]}>
            <MaterialCommunityIcons
              name={copied ? 'check' : 'content-copy'}
              size={16}
              color={copied ? authColors.primary : authColors.onSurfaceVariant}
            />
            <Text style={[styles.utilityText, copied ? styles.utilityTextSelected : null]}>
              {copied ? 'Copied' : 'Copy'}
            </Text>
          </AnimatedPressable>
          <View style={styles.utilityDivider} />
          <Text style={styles.helpfulLabel}>Helpful?</Text>
          <AnimatedPressable
            accessibilityRole="button"
            accessibilityLabel="Mark response as helpful"
            accessibilityState={{ selected: message.feedback === 'helpful' }}
            disabled={feedbackDisabled || feedbackSaving}
            hitSlop={4}
            onPress={() => void saveFeedback('helpful')}
            style={[
              styles.feedbackAction,
              message.feedback === 'helpful' ? styles.utilityActionSelected : null,
              feedbackDisabled || feedbackSaving ? styles.utilityDisabled : null,
            ]}>
            <MaterialCommunityIcons
              name={message.feedback === 'helpful' ? 'thumb-up' : 'thumb-up-outline'}
              size={17}
              color={message.feedback === 'helpful' ? authColors.primary : authColors.onSurfaceVariant}
            />
          </AnimatedPressable>
          <AnimatedPressable
            accessibilityRole="button"
            accessibilityLabel="Mark response as not helpful"
            accessibilityState={{ selected: message.feedback === 'not_helpful' }}
            disabled={feedbackDisabled || feedbackSaving}
            hitSlop={4}
            onPress={() => void saveFeedback('not_helpful')}
            style={[
              styles.feedbackAction,
              message.feedback === 'not_helpful' ? styles.utilityActionSelected : null,
              feedbackDisabled || feedbackSaving ? styles.utilityDisabled : null,
            ]}>
            <MaterialCommunityIcons
              name={message.feedback === 'not_helpful' ? 'thumb-down' : 'thumb-down-outline'}
              size={17}
              color={message.feedback === 'not_helpful' ? authColors.primary : authColors.onSurfaceVariant}
            />
          </AnimatedPressable>
        </View>
      ) : null}
      {isAssistant && message.sources.length > 0 ? (
        <View style={styles.sourceDisclosure}>
          <AnimatedPressable
            accessibilityRole="button"
            accessibilityState={{ expanded: sourceDisclosure.showSources }}
            onPress={() => setSourcesExpanded((current) => !current)}
            style={styles.sourceToggle}>
            <MaterialCommunityIcons name="book-open-variant" size={15} color={authColors.primary} />
            <Text style={styles.sourceToggleText}>{sourceDisclosure.label}</Text>
            <MaterialCommunityIcons
              name={sourceDisclosure.showSources ? 'chevron-up' : 'chevron-down'}
              size={17}
              color={authColors.primary}
            />
          </AnimatedPressable>
          {sourceDisclosure.showSources ? (
            <Animated.View
              entering={reduceMotion ? undefined : FadeIn.duration(coachMotion.stateTransitionDuration)}
              exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
              style={styles.sources}>
              {message.sources.map((source, index) => {
                const label = coachSourceLabel(source);
                return label ? (
                  <Animated.View
                    entering={reduceMotion ? undefined : FadeIn
                      .duration(coachMotion.stateTransitionDuration)
                      .delay(Math.min(index, 4) * coachMotion.sourceStagger)}
                    key={`${source.rank}-${source.source ?? source.title}`}
                    style={styles.sourceChip}>
                    <MaterialCommunityIcons name="file-document-outline" size={14} color={authColors.primary} />
                    <Text selectable style={styles.sourceText}>{label}</Text>
                  </Animated.View>
                ) : null;
              })}
            </Animated.View>
          ) : null}
        </View>
      ) : null}
      {isAssistant && choices.length > 0 && !clarification && !action ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeInUp.duration(coachMotion.messageEnterDuration)}
          style={styles.followUpSection}>
          <Text style={styles.followUpLabel}>SUGGESTED NEXT</Text>
          <View style={styles.followUpRow}>
            {choices.map((choice) => (
              <AnimatedPressable
                accessibilityRole="button"
                disabled={feedbackDisabled}
                key={choice.id}
                onPress={() => onFollowUp(choice.query, {
                  assistant_message_id: message.id,
                  value: choice.id,
                })}
                style={[
                  styles.followUpChip,
                  feedbackDisabled ? styles.utilityDisabled : null,
                ]}>
                <Text style={styles.followUpText}>{choice.label}</Text>
                <MaterialCommunityIcons name="arrow-right" size={15} color={authColors.primary} />
              </AnimatedPressable>
            ))}
          </View>
        </Animated.View>
      ) : null}
      {isAssistant && showFollowUps && followUps.length > 0 && choices.length === 0 && !clarification && !action ? (
        <Animated.View
          entering={reduceMotion ? undefined : FadeInUp.duration(coachMotion.messageEnterDuration)}
          style={styles.followUpSection}>
          <Text style={styles.followUpLabel}>CONTINUE WITH</Text>
          <View style={styles.followUpRow}>
            {followUps.map((chip) => (
              <AnimatedPressable
                accessibilityRole="button"
                disabled={feedbackDisabled}
                key={chip.query}
                onPress={() => onFollowUp(chip.query)}
                style={[
                  styles.followUpChip,
                  feedbackDisabled ? styles.utilityDisabled : null,
                ]}>
                <Text style={styles.followUpText}>{chip.label}</Text>
                <MaterialCommunityIcons name="arrow-right" size={15} color={authColors.primary} />
              </AnimatedPressable>
            ))}
          </View>
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}

// A conversation can hold dozens of rows, and the composer re-renders the screen
// on every keystroke. Without memo every row re-parses its markdown and replays
// its layout animation on each character typed, which is what stalls the JS
// thread for tens of seconds on long chats.
export const CoachMessage = memo(CoachMessageView);

function CoachResponseSectionView({
  section,
  showDivider,
}: {
  section: CoachResponseSection;
  showDivider: boolean;
}) {
  const icon = section.kind === 'insight'
    ? 'lightbulb-on-outline'
    : section.kind === 'action'
      ? 'check-circle-outline'
      : 'information-outline';
  const isGuidance = section.kind === 'guidance';

  return (
    <View
      style={[
        styles.responseSection,
        isGuidance ? styles.guidanceSection : null,
        showDivider && !isGuidance ? styles.responseDivider : null,
      ]}>
      {section.title ? (
        <View style={styles.sectionHeading}>
          <MaterialCommunityIcons
            name={icon}
            size={16}
            color={isGuidance ? authColors.onSurfaceVariant : authColors.primary}
          />
          <Text style={[styles.sectionTitle, isGuidance ? styles.guidanceTitle : null]}>
            {section.title}
          </Text>
        </View>
      ) : null}
      <CoachRichText
        content={section.content}
        color={isGuidance ? authColors.onSurfaceVariant : authColors.onSurface}
        compact={isGuidance}
      />
    </View>
  );
}

function CoachRichText({
  color,
  compact = false,
  content,
}: {
  color: string;
  compact?: boolean;
  content: string;
}) {
  const textSegments = parseCoachMarkdown(content);
  return (
    <Text
      selectable
      style={{
        color,
        fontFamily: authFont.regular,
        fontSize: compact ? 12 : 15,
        lineHeight: compact ? 17 : 22,
      }}>
      {textSegments.map((segment, index) => (
        <Text
          key={`${index}-${segment.text}`}
          style={segment.bold ? { fontFamily: authFont.bold } : undefined}>
          {segment.text}
        </Text>
      ))}
    </Text>
  );
}

export function CoachTypingIndicator() {
  const reduceMotion = useReducedMotion();
  return (
    <Animated.View
      accessibilityLabel="FinCoach is typing"
      entering={reduceMotion ? undefined : FadeInUp.duration(coachMotion.messageEnterDuration)}
      exiting={reduceMotion ? undefined : FadeOut.duration(coachMotion.stateTransitionDuration)}
      style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
      <View style={styles.avatar}><MaterialCommunityIcons name="creation" size={16} color={authColors.onPrimary} /></View>
      <View style={[styles.assistantBubble, { flexDirection: 'row', gap: 5, paddingVertical: 16 }]}>
        {[0, 1, 2].map((dot) => <TypingDot index={dot} key={dot} />)}
      </View>
    </Animated.View>
  );
}

function TypingDot({ index }: { index: number }) {
  const reduceMotion = useReducedMotion();
  const progress = useSharedValue(0);

  useEffect(() => {
    if (reduceMotion) {
      progress.value = 0;
      return;
    }
    const halfCycle = coachMotion.typingDotTravelDuration / 2;
    progress.value = withDelay(
      coachTypingDotDelay(index),
      withRepeat(
        withSequence(
          withTiming(1, { duration: halfCycle }),
          withTiming(0, { duration: halfCycle }),
        ),
        -1,
        false,
      ),
    );
    return () => cancelAnimation(progress);
  }, [index, progress, reduceMotion]);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: reduceMotion ? 0.65 : 0.45 + (progress.value * 0.55),
    transform: [{ translateY: reduceMotion ? 0 : progress.value * -3 }],
  }));

  return <Animated.View style={[styles.dot, animatedStyle]} />;
}

const styles = {
  avatar: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary } as const,
  assistantBubble: { flexShrink: 1, borderRadius: 20, borderBottomLeftRadius: 6, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: authColors.surfaceContainerHigh, borderCurve: 'continuous' } as const,
  userBubble: { borderRadius: 20, borderBottomRightRadius: 6, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: authColors.primary, borderCurve: 'continuous' } as const,
  responseSections: { gap: 10 } as const,
  responseSection: { gap: 5 } as const,
  responseDivider: { paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant } as const,
  sectionHeading: { flexDirection: 'row', alignItems: 'center', gap: 6 } as const,
  sectionTitle: { color: authColors.primary, fontFamily: authFont.bold, fontSize: 13, lineHeight: 17 } as const,
  guidanceSection: { borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, gap: 4, backgroundColor: authColors.surfaceContainerLow } as const,
  guidanceTitle: { color: authColors.onSurfaceVariant, fontSize: 11, lineHeight: 15 } as const,
  utilityBar: { minHeight: 40, paddingLeft: 36, paddingTop: 5, flexDirection: 'row', alignItems: 'center', gap: 4 } as const,
  utilityAction: { minHeight: 40, borderRadius: 20, paddingHorizontal: 9, flexDirection: 'row', alignItems: 'center', gap: 5 } as const,
  utilityActionSelected: { backgroundColor: authColors.primaryFixed } as const,
  utilityText: { color: authColors.onSurfaceVariant, fontFamily: authFont.semibold, fontSize: 11, lineHeight: 15 } as const,
  utilityTextSelected: { color: authColors.primary } as const,
  utilityDivider: { width: 1, height: 20, marginHorizontal: 3, backgroundColor: authColors.outlineVariant } as const,
  helpfulLabel: { color: authColors.outline, fontFamily: authFont.semibold, fontSize: 10, lineHeight: 14 } as const,
  feedbackAction: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' } as const,
  utilityDisabled: { opacity: 0.45 } as const,
  sourceDisclosure: { paddingLeft: 36, paddingTop: 7, alignItems: 'flex-start', gap: 6 } as const,
  sourceToggle: { minHeight: 34, flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 17, borderWidth: 1, borderColor: authColors.primaryFixedDim, paddingHorizontal: 11, backgroundColor: authColors.surfaceContainerLowest } as const,
  sourceToggleText: { color: authColors.primary, fontFamily: authFont.semibold, fontSize: 12, lineHeight: 16 } as const,
  sources: { maxWidth: '100%', gap: 6 } as const,
  sourceChip: { maxWidth: '100%', flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: authColors.primaryFixed } as const,
  sourceText: { flexShrink: 1, color: authColors.onPrimaryFixed, fontFamily: authFont.semibold, fontSize: 11, lineHeight: 15 } as const,
  followUpSection: { paddingLeft: 36, paddingTop: 9, gap: 6 } as const,
  followUpLabel: { color: authColors.onSurfaceVariant, fontFamily: authFont.bold, fontSize: 9, lineHeight: 13, letterSpacing: 0.7 } as const,
  followUpRow: { gap: 7 } as const,
  followUpChip: { minHeight: 44, borderRadius: 16, borderWidth: 1, borderColor: authColors.primaryFixedDim, paddingHorizontal: 11, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, backgroundColor: authColors.surfaceContainerLowest } as const,
  followUpText: { flexShrink: 1, color: authColors.primary, fontFamily: authFont.semibold, fontSize: 12, lineHeight: 16 } as const,
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: authColors.onSurfaceVariant } as const,
} as const;
