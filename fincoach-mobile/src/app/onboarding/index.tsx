import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  Image,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
  Pressable,
  StatusBar,
  View,
  useWindowDimensions,
} from 'react-native';
import Animated, {
  Extrapolation,
  interpolate,
  interpolateColor,
  type SharedValue,
  useAnimatedRef,
  useAnimatedStyle,
  useScrollViewOffset,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { AppText as Text } from '@/components/ui/app-text';
import { AuthBackdrop } from '@/components/ui/auth-backdrop';
import { authColors, authFont, authRadius, authSpacing, authType } from '@/constants/auth-theme';

const CORAL = '#D85A30'; // over-budget alert (Stitch coral)
const CORAL_DARK = '#993C1D';

const CHART_HEIGHT = 110;
const CHART_BARS = [
  { day: 'Mon', pct: 0.42, over: false },
  { day: 'Tue', pct: 0.54, over: false },
  { day: 'Wed', pct: 0.48, over: false },
  { day: 'Thu', pct: 0.86, over: true },
  { day: 'Fri', pct: 0.38, over: false },
];

const slides = [
  {
    key: 'track',
    title: 'Track Every Ringgit',
    body: 'Log expenses in seconds and see where your money goes.',
    button: 'Get Started',
  },
  {
    key: 'categorize',
    title: 'All Your Spending in One Place',
    body: 'Track food, transport, books and more — all categorized automatically.',
    button: 'Continue',
  },
  {
    key: 'coach',
    title: 'Your Personal Finance Coach',
    body: 'Get smart, personalized money advice based on your own spending.',
    button: 'Get Started',
  },
];

const ORBIT_TILES = [
  { icon: 'shopping-bag', color: '#F43F5E', size: 48, style: { top: '6%', left: '16%' } },
  { icon: 'menu-book', color: '#F59E0B', size: 56, style: { top: '14%', right: '10%' } },
  { icon: 'directions-car', color: '#3B82F6', size: 56, style: { top: '46%', left: '0%' } },
  { icon: 'local-cafe', color: '#A0522D', size: 48, style: { top: '56%', right: '4%' } },
  { icon: 'flight', color: '#14B8A6', size: 56, style: { bottom: '8%', left: '22%' } },
  { icon: 'receipt-long', color: '#10B981', size: 48, style: { bottom: '18%', right: '26%' } },
] as const;

function softShadow(opacity: number) {
  return {
    shadowColor: authColors.primary,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: opacity,
    shadowRadius: 24,
    elevation: 4,
  };
}

function TrackArt({ size }: { size: number }) {
  return (
    <View
      style={[
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: 'rgba(255,255,255,0.35)',
          borderWidth: 1,
          borderColor: 'rgba(255,255,255,0.6)',
          alignItems: 'center',
          justifyContent: 'center',
        },
        softShadow(0.1),
      ]}>
      <View
        style={{
          position: 'absolute',
          width: size * 0.74,
          height: size * 0.74,
          borderRadius: (size * 0.74) / 2,
          backgroundColor: authColors.primaryFixed,
          opacity: 0.6,
        }}
      />
      <Image
        source={require('../../../assets/images/fincoach-logo.png')}
        style={{ width: size * 0.56, height: size * 0.56, borderRadius: (size * 0.56) / 2 }}
        resizeMode="cover"
      />
    </View>
  );
}

// One floating category tile that gently bobs + rotates forever, staggered by `delay`.
function FloatingTile({
  tile,
  delay,
}: {
  tile: (typeof ORBIT_TILES)[number];
  delay: number;
}) {
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withDelay(delay, withRepeat(withTiming(1, { duration: 2000 }), -1, true));
  }, [delay, progress]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: interpolate(progress.value, [0, 1], [0, -10]) },
      { rotate: `${interpolate(progress.value, [0, 1], [0, 2])}deg` },
    ],
  }));

  return (
    <Animated.View
      style={[
        {
          position: 'absolute',
          width: tile.size,
          height: tile.size,
          borderRadius: authRadius.md,
          backgroundColor: authColors.surfaceContainerLowest,
          alignItems: 'center',
          justifyContent: 'center',
        },
        tile.style,
        softShadow(0.1),
        animatedStyle,
      ]}>
      <MaterialIcons name={tile.icon} size={tile.size * 0.5} color={tile.color} />
    </Animated.View>
  );
}

function CategorizeArt({ size }: { size: number }) {
  return (
    <View style={{ width: size, height: size }}>
      <View
        style={[
          {
            position: 'absolute',
            top: '50%',
            left: '50%',
            width: 88,
            height: 88,
            marginLeft: -44,
            marginTop: -44,
            borderRadius: authRadius.lg,
            backgroundColor: authColors.surfaceContainerLowest,
            alignItems: 'center',
            justifyContent: 'center',
          },
          softShadow(0.12),
        ]}>
        <MaterialIcons name="account-balance-wallet" size={40} color={authColors.primary} />
      </View>
      {ORBIT_TILES.map((tile, tileIndex) => (
        <FloatingTile key={tile.icon} tile={tile} delay={tileIndex * 300} />
      ))}
    </View>
  );
}

// A single chart bar that grows up from the baseline when the slide becomes active.
function AnimatedBar({
  targetHeight,
  color,
  delay,
  active,
}: {
  targetHeight: number;
  color: string;
  delay: number;
  active: boolean;
}) {
  const height = useSharedValue(0);

  useEffect(() => {
    height.value = active ? withDelay(delay, withTiming(targetHeight, { duration: 550 })) : 0;
  }, [active, delay, targetHeight, height]);

  const animatedStyle = useAnimatedStyle(() => ({ height: height.value }));

  return (
    <Animated.View
      style={[{ width: '100%', borderTopLeftRadius: 6, borderTopRightRadius: 6, backgroundColor: color }, animatedStyle]}
    />
  );
}

function CoachArt({ active }: { active: boolean }) {
  const tagProgress = useSharedValue(0);

  useEffect(() => {
    tagProgress.value = active ? withDelay(850, withTiming(1, { duration: 300 })) : 0;
  }, [active, tagProgress]);

  const tagStyle = useAnimatedStyle(() => ({
    opacity: tagProgress.value,
    transform: [{ translateY: interpolate(tagProgress.value, [0, 1], [6, 0]) }],
  }));

  return (
    <View
      style={[
        {
          width: '100%',
          backgroundColor: authColors.surfaceContainerLowest,
          borderRadius: authRadius.lg,
          padding: authSpacing.lg,
          gap: authSpacing.md,
          overflow: 'hidden',
        },
        softShadow(0.08),
      ]}>
      <View
        style={{ position: 'absolute', top: 0, left: 0, width: 4, height: '100%', backgroundColor: authColors.primary, opacity: 0.8 }}
      />

      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: authSpacing.sm }}>
        <View
          style={{
            width: 36,
            height: 36,
            borderRadius: 18,
            backgroundColor: authColors.primaryFixed,
            alignItems: 'center',
            justifyContent: 'center',
          }}>
          <Text style={{ color: authColors.primary, fontFamily: authFont.bold, fontSize: 13 }}>RK</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: authSpacing.unit }}>
          <MaterialIcons name="auto-awesome" size={15} color={authColors.primary} />
          <Text style={{ color: authColors.primary, fontFamily: authFont.semibold, fontSize: 13 }}>FinCoach AI</Text>
        </View>
      </View>

      {/* Message */}
      <Text style={[authType.bodySm, { color: authColors.onSurface }]}>
        You&apos;re trending <Text style={{ color: CORAL_DARK, fontFamily: authFont.semibold }}>↑ 15% over</Text> your dining
        budget this week.
      </Text>

      {/* Chart */}
      <View style={{ height: CHART_HEIGHT, justifyContent: 'flex-end' }}>
        {/* Budget line (dashed) */}
        <View style={{ position: 'absolute', left: 0, right: 0, bottom: CHART_HEIGHT * 0.68, flexDirection: 'row', overflow: 'hidden' }}>
          {Array.from({ length: 28 }).map((_, dashIndex) => (
            <View key={dashIndex} style={{ width: 5, height: 1.5, marginRight: 4, backgroundColor: authColors.primaryFixedDim }} />
          ))}
        </View>
        <Text
          style={{
            position: 'absolute',
            right: 0,
            bottom: CHART_HEIGHT * 0.68 + 3,
            fontSize: 11,
            color: authColors.primary,
            fontFamily: authFont.regular,
          }}>
          budget
        </Text>
        {/* Bars */}
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: authSpacing.md, height: '100%' }}>
          {CHART_BARS.map((bar, barIndex) => (
            <View key={bar.day} style={{ flex: 1, height: '100%', justifyContent: 'flex-end' }}>
              {bar.over ? (
                <Animated.View
                  style={[
                    {
                      position: 'absolute',
                      bottom: CHART_HEIGHT * bar.pct + 4,
                      alignSelf: 'center',
                      backgroundColor: CORAL_DARK,
                      paddingHorizontal: 8,
                      paddingVertical: 2,
                      borderRadius: authRadius.full,
                      zIndex: 2,
                    },
                    tagStyle,
                  ]}>
                  <Text style={{ color: authColors.onPrimary, fontSize: 11, fontFamily: authFont.bold }}>+15%</Text>
                </Animated.View>
              ) : null}
              <AnimatedBar
                active={active}
                color={bar.over ? CORAL : authColors.primaryFixedDim}
                delay={barIndex * 90}
                targetHeight={CHART_HEIGHT * bar.pct}
              />
            </View>
          ))}
        </View>
      </View>

      {/* Day labels */}
      <View style={{ flexDirection: 'row', gap: authSpacing.md }}>
        {CHART_BARS.map((bar) => (
          <Text
            key={bar.day}
            style={{
              flex: 1,
              textAlign: 'center',
              fontSize: 11,
              fontFamily: bar.over ? authFont.semibold : authFont.regular,
              color: bar.over ? CORAL_DARK : authColors.onSurfaceVariant,
            }}>
            {bar.day}
          </Text>
        ))}
      </View>

      {/* Action */}
      <View
        style={{
          alignSelf: 'flex-end',
          flexDirection: 'row',
          alignItems: 'center',
          gap: authSpacing.unit,
          backgroundColor: authColors.primary,
          paddingHorizontal: 16,
          paddingVertical: 8,
          borderRadius: authRadius.full,
        }}>
        <MaterialIcons name="check" size={14} color={authColors.onPrimary} />
        <Text style={{ color: authColors.onPrimary, fontSize: 13, fontFamily: authFont.semibold }}>Set a limit</Text>
      </View>
    </View>
  );
}

// Fades + slides the slide's content based on how centered the page is.
function SlideContent({
  pageIndex,
  scrollX,
  width,
  children,
}: {
  pageIndex: number;
  scrollX: SharedValue<number>;
  width: number;
  children: React.ReactNode;
}) {
  const animatedStyle = useAnimatedStyle(() => {
    const input = [(pageIndex - 1) * width, pageIndex * width, (pageIndex + 1) * width];
    return {
      opacity: interpolate(scrollX.value, input, [0.25, 1, 0.25], Extrapolation.CLAMP),
      transform: [{ translateY: interpolate(scrollX.value, input, [18, 0, 18], Extrapolation.CLAMP) }],
    };
  });

  return (
    <Animated.View style={[{ flex: 1, paddingHorizontal: authSpacing.container }, animatedStyle]}>
      {children}
    </Animated.View>
  );
}

function PagerDot({ index, scrollX, width }: { index: number; scrollX: SharedValue<number>; width: number }) {
  const animatedStyle = useAnimatedStyle(() => {
    const input = [(index - 1) * width, index * width, (index + 1) * width];
    return {
      width: interpolate(scrollX.value, input, [8, 24, 8], Extrapolation.CLAMP),
      backgroundColor: interpolateColor(scrollX.value, input, [
        authColors.surfaceVariant,
        authColors.primary,
        authColors.surfaceVariant,
      ]),
    };
  });

  return <Animated.View style={[{ height: 8, borderRadius: authRadius.full }, animatedStyle]} />;
}

export default function OnboardingScreen() {
  const [index, setIndex] = useState(0);
  const { width, height } = useWindowDimensions();
  const scrollRef = useAnimatedRef<Animated.ScrollView>();
  const scrollX = useScrollViewOffset(scrollRef);
  const isLast = index === slides.length - 1;

  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + authSpacing.sm;
  const circleSize = Math.min(width * 0.7, height * 0.34, 280);
  const orbitSize = Math.min(width * 0.84, height * 0.42, 300);

  function handleMomentumEnd(event: NativeSyntheticEvent<NativeScrollEvent>) {
    setIndex(Math.round(event.nativeEvent.contentOffset.x / width));
  }

  function handleNext() {
    if (isLast) {
      router.replace('/auth/sign-up');
      return;
    }
    scrollRef.current?.scrollTo({ x: (index + 1) * width, animated: true });
  }

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <AuthBackdrop color="#A5B4FC" height={Math.round(height * 0.4)} maxOpacity={0.5} />
      <View style={{ flex: 1, paddingTop: topPad, paddingBottom: authSpacing.lg }}>
        <Animated.ScrollView
          ref={scrollRef}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          onMomentumScrollEnd={handleMomentumEnd}
          style={{ flex: 1 }}>
          {slides.map((slide, slideIndex) => (
            <View key={slide.key} style={{ width }}>
              <SlideContent pageIndex={slideIndex} scrollX={scrollX} width={width}>
                <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                  {slideIndex === 0 ? <TrackArt size={circleSize} /> : null}
                  {slideIndex === 1 ? <CategorizeArt size={orbitSize} /> : null}
                  {slideIndex === 2 ? <CoachArt active={index === 2} /> : null}
                </View>
                <View style={{ alignItems: 'center', gap: authSpacing.sm, marginBottom: authSpacing.lg }}>
                  <Text
                    allowFontScaling={false}
                    style={[authType.displayTitle, { color: authColors.onSurface, textAlign: 'center' }]}>
                    {slide.title}
                  </Text>
                  <Text
                    allowFontScaling={false}
                    style={[authType.body, { color: authColors.onSurfaceVariant, textAlign: 'center', maxWidth: 300 }]}>
                    {slide.body}
                  </Text>
                </View>
              </SlideContent>
            </View>
          ))}
        </Animated.ScrollView>

        {/* Pager */}
        <View
          style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: authSpacing.sm, marginBottom: authSpacing.lg }}>
          {slides.map((slide, dotIndex) => (
            <PagerDot key={slide.key} index={dotIndex} scrollX={scrollX} width={width} />
          ))}
        </View>

        {/* Button */}
        <View style={{ paddingHorizontal: authSpacing.container }}>
          <Pressable
            onPress={handleNext}
            style={({ pressed }) => [
              {
                height: 56,
                borderRadius: authRadius.full,
                backgroundColor: authColors.primary,
                alignItems: 'center',
                justifyContent: 'center',
              },
              pressed && { opacity: 0.9 },
            ]}>
            <Text
              allowFontScaling={false}
              numberOfLines={1}
              style={[authType.titleSm, { color: authColors.onPrimary }]}>
              {slides[index].button}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}
