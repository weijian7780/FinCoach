import { useCallback } from 'react';
import {
  Pressable,
  type GestureResponderEvent,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import Animated, {
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import { coachMotion, coachPressScale } from '@/lib/coach-motion';

const ReanimatedPressable = Animated.createAnimatedComponent(Pressable);

type AnimatedPressableProps = Omit<PressableProps, 'style'> & {
  style?: StyleProp<ViewStyle>;
};

export function AnimatedPressable({
  disabled = false,
  onPressIn,
  onPressOut,
  style,
  ...props
}: AnimatedPressableProps) {
  const reduceMotion = useReducedMotion();
  const isDisabled = disabled === true;
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = useCallback((event: GestureResponderEvent) => {
    // Reanimated shared values are intentionally mutable animation state.
    // eslint-disable-next-line react-hooks/immutability
    scale.value = reduceMotion
      ? 1
      : withTiming(coachPressScale(true, isDisabled), {
          duration: coachMotion.tapDuration,
        });
    onPressIn?.(event);
  }, [isDisabled, onPressIn, reduceMotion, scale]);

  const handlePressOut = useCallback((event: GestureResponderEvent) => {
    // Reanimated shared values are intentionally mutable animation state.
    // eslint-disable-next-line react-hooks/immutability
    scale.value = reduceMotion
      ? 1
      : withSpring(1, {
          damping: coachMotion.springDamping,
          stiffness: coachMotion.springStiffness,
        });
    onPressOut?.(event);
  }, [onPressOut, reduceMotion, scale]);

  return (
    <ReanimatedPressable
      {...props}
      disabled={isDisabled}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      style={[style, animatedStyle]}
    />
  );
}
