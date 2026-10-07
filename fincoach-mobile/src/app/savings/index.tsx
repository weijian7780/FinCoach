import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GoalCard } from '@/components/savings/goal-card';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { fetchSavingsGoals } from '@/lib/savings';
import type { SavingsGoal } from '@/lib/types';

export default function SavingsGoalListScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [goals, setGoals] = useState<SavingsGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setGoals(await fetchSavingsGoals(userId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load your savings goals.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: insets.top + 8, paddingHorizontal: 18, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable accessibilityLabel="Go back" accessibilityRole="button" hitSlop={10} onPress={() => router.back()}>
          <MaterialIcons name="arrow-back" size={25} color={authColors.onSurface} />
        </Pressable>
        <Text style={{ flex: 1, fontSize: 21, fontFamily: authFont.bold, color: authColors.onSurface }}>Savings Goals</Text>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 }}>
          <ActivityIndicator color={authColors.primary} />
          <Text style={{ fontSize: 14, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Loading your goals…</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 4, paddingBottom: insets.bottom + 104, gap: 16 }} showsVerticalScrollIndicator={false}>
          <Text style={{ fontSize: 15, lineHeight: 21, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Track your progress to financial freedom.</Text>
          {error ? (
            <View style={messageCardStyle}>
              <MaterialIcons name="cloud-off" size={34} color={authColors.error} />
              <Text style={{ textAlign: 'center', fontSize: 15, fontFamily: authFont.semibold, color: authColors.onSurface }}>Could not load goals</Text>
              <Text style={{ textAlign: 'center', fontSize: 13, lineHeight: 19, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>{error}</Text>
              <Pressable accessibilityRole="button" onPress={() => void load()} style={secondaryButtonStyle}><Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>Try again</Text></Pressable>
            </View>
          ) : goals.length === 0 ? (
            <View style={messageCardStyle}>
              <View style={{ width: 62, height: 62, borderRadius: 31, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primaryFixed }}><MaterialIcons name="savings" size={34} color={authColors.primary} /></View>
              <Text style={{ fontSize: 18, fontFamily: authFont.bold, color: authColors.onSurface }}>Start your first savings goal</Text>
              <Text style={{ textAlign: 'center', fontSize: 14, lineHeight: 20, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Choose a purpose, target amount and deadline. Record each contribution as you save.</Text>
              <Pressable accessibilityRole="button" onPress={() => router.push('/savings/manage')} style={primaryButtonStyle}><MaterialIcons name="add" size={19} color={authColors.onPrimary} /><Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.onPrimary }}>Create goal</Text></Pressable>
            </View>
          ) : goals.map((goal) => <GoalCard goal={goal} key={goal.id} onPress={() => router.push({ pathname: '/savings/[goalId]', params: { goalId: String(goal.id) } })} />)}
        </ScrollView>
      )}

      {!loading && !error && goals.length > 0 ? (
        <Pressable accessibilityLabel="Create savings goal" accessibilityRole="button" onPress={() => router.push('/savings/manage')} style={({ pressed }) => [fabStyle, { bottom: Math.max(insets.bottom, 16) + 12 }, pressed && { opacity: 0.88 }]}><MaterialIcons name="add" size={29} color={authColors.onPrimary} /></Pressable>
      ) : null}
    </View>
  );
}

const messageCardStyle = { marginTop: 8, paddingHorizontal: 22, paddingVertical: 32, borderRadius: 20, alignItems: 'center', gap: 10, backgroundColor: authColors.surfaceContainerLowest, borderWidth: 0.5, borderColor: authColors.outlineVariant } as const;
const primaryButtonStyle = { marginTop: 8, paddingHorizontal: 20, paddingVertical: 13, borderRadius: 13, flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: authColors.primary } as const;
const secondaryButtonStyle = { marginTop: 8, paddingHorizontal: 20, paddingVertical: 11, borderRadius: 12, borderWidth: 1, borderColor: authColors.primary } as const;
const fabStyle = { position: 'absolute', right: 20, width: 58, height: 58, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.primary, shadowColor: authColors.primary, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.28, shadowRadius: 10, elevation: 6 } as const;
