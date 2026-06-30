import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { router } from 'expo-router';
import type { ComponentProps } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StatusBar, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { fetchSavingsGoals } from '@/lib/finance';
import type { SavingsGoal } from '@/lib/types';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

function firstName(name: string | null | undefined) {
  const part = (name ?? '').trim().split(/\s+/)[0];
  return part || 'there';
}
function rm(value: number) {
  return `RM ${value.toLocaleString('en-MY', { maximumFractionDigits: 0 })}`;
}

export default function HomeScreen() {
  const { profile, session } = useAuth();
  const userId = session?.user.id;
  const [goals, setGoals] = useState<SavingsGoal[]>([]);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      setGoals(await fetchSavingsGoals(userId));
    } catch {
      // Best-effort; the rest of the dashboard still renders.
    }
  }, [userId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;
  const allowance = profile?.monthly_allowance ?? null;
  const spent = 0; // Transactions module not built yet → no spending recorded.
  const remaining = allowance != null ? allowance - spent : 0;
  const pctSpent = allowance && allowance > 0 ? Math.min(100, (spent / allowance) * 100) : 0;
  const topGoal = goals[0];
  const topGoalRatio = topGoal && topGoal.target_amount > 0 ? Math.min(1, topGoal.current_amount / topGoal.target_amount) : 0;

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      {/* Top app bar */}
      <View style={{ paddingTop: topPad, paddingHorizontal: 16, paddingBottom: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Pressable onPress={() => router.push('/profile')}>
          <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
            {profile?.avatar_url ? (
              <Image source={{ uri: profile.avatar_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" />
            ) : (
              <MaterialIcons name="person" size={22} color={authColors.primary} />
            )}
          </View>
        </Pressable>
        <Text style={{ fontSize: 20, fontFamily: authFont.bold, color: authColors.primary }}>FinCoach</Text>
        <MaterialIcons name="notifications-none" size={24} color={authColors.onSurfaceVariant} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 32 }}>
        {/* Greeting */}
        <View>
          <Text style={{ fontSize: 24, fontFamily: authFont.bold, color: authColors.onSurface }}>Hello, {firstName(profile?.full_name)}! 👋</Text>
          <Text style={{ fontSize: 14, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, marginTop: 2 }}>Let&apos;s check in on your money today.</Text>
        </View>

        {/* Budget card */}
        <View style={cardStyle}>
          {allowance == null ? (
            <View style={{ alignItems: 'center', gap: 8, paddingVertical: 8 }}>
              <Text style={{ fontSize: 16, fontFamily: authFont.semibold, color: authColors.onSurface }}>Set your monthly allowance</Text>
              <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, textAlign: 'center' }}>
                Add it in Preferences to start tracking your budget.
              </Text>
              <Pressable onPress={() => router.push('/profile/edit')} style={primaryBtn}>
                <Text style={primaryBtnText}>Set allowance</Text>
              </Pressable>
            </View>
          ) : (
            <>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <View>
                  <Text style={labelCaps}>REMAINING BUDGET</Text>
                  <Text style={{ fontSize: 30, fontFamily: authFont.bold, color: authColors.onSurface, marginTop: 2 }}>{rm(remaining)}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={labelCaps}>Total Monthly</Text>
                  <Text style={{ fontSize: 18, fontFamily: authFont.semibold, color: authColors.onSurface, marginTop: 4 }}>{rm(allowance)}</Text>
                </View>
              </View>
              <View style={{ height: 8, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh, overflow: 'hidden', marginTop: 12 }}>
                <View style={{ height: '100%', width: `${pctSpent}%`, backgroundColor: authColors.primary, borderRadius: 999 }} />
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Spent: {rm(spent)}</Text>
                <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant }}>{Math.round(100 - pctSpent)}% left</Text>
              </View>
              <View style={{ height: 1, backgroundColor: authColors.outlineVariant, opacity: 0.5, marginVertical: 14 }} />
              <View style={{ flexDirection: 'row', gap: 10 }}>
                <Pressable
                  onPress={() => Alert.alert('Coming soon', 'Adding expenses arrives with the Transactions module.')}
                  style={[primaryBtn, { flex: 1, flexDirection: 'row', gap: 6 }]}>
                  <MaterialIcons name="add" size={18} color={authColors.onPrimary} />
                  <Text style={primaryBtnText}>Add Expense</Text>
                </Pressable>
                <Pressable
                  onPress={() => Alert.alert('Coming soon', 'Budget details arrive with the Budget module.')}
                  style={[secondaryBtn, { flex: 1 }]}>
                  <Text style={secondaryBtnText}>View Details</Text>
                </Pressable>
              </View>
            </>
          )}
        </View>

        {/* Quick actions */}
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <QuickAction icon="document-scanner" label="Scan" onPress={() => Alert.alert('Coming soon', 'Receipt scanning arrives later.')} />
          <QuickAction icon="savings" label="Goals" onPress={() => router.push('/savings')} />
          <QuickAction icon="bar-chart" label="Reports" onPress={() => router.push('/reports')} />
        </View>

        {/* This Month report preview */}
        <View style={cardStyle}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ fontSize: 18, fontFamily: authFont.bold, color: authColors.onSurface }}>This Month</Text>
            <Pressable onPress={() => router.push('/reports')}>
              <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>View report</Text>
            </Pressable>
          </View>
          <View style={{ alignItems: 'center', paddingVertical: 8 }}>
            <View style={{ width: 150, height: 150, borderRadius: 75, borderWidth: 14, borderColor: authColors.surfaceContainerHigh, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ fontSize: 12, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>Total</Text>
              <Text style={{ fontSize: 22, fontFamily: authFont.bold, color: authColors.onSurface }}>{rm(spent)}</Text>
            </View>
            <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, marginTop: 12, textAlign: 'center' }}>
              No expenses yet this month. Your spending breakdown will appear here.
            </Text>
          </View>
        </View>

        {/* Savings goal preview */}
        <View style={cardStyle}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: topGoal ? 12 : 8 }}>
            <Text style={{ fontSize: 18, fontFamily: authFont.bold, color: authColors.onSurface }}>Savings Goal</Text>
            <Pressable onPress={() => router.push('/savings')}>
              <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>{topGoal ? 'View all' : 'Add'}</Text>
            </Pressable>
          </View>
          {topGoal ? (
            <View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface }}>{topGoal.name}</Text>
                <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>
                  {rm(topGoal.current_amount)} / {rm(topGoal.target_amount)}
                </Text>
              </View>
              <View style={{ height: 8, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh, overflow: 'hidden' }}>
                <View style={{ height: '100%', width: `${topGoalRatio * 100}%`, backgroundColor: authColors.primary, borderRadius: 999 }} />
              </View>
            </View>
          ) : (
            <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>
              No savings goals yet. Tap “Add” to start one.
            </Text>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function QuickAction({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [cardStyle, { flex: 1, alignItems: 'center', paddingVertical: 16, gap: 8 }, pressed && { opacity: 0.85 }]}>
      <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center' }}>
        <MaterialIcons name={icon} size={22} color={authColors.primary} />
      </View>
      <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurface }}>{label}</Text>
    </Pressable>
  );
}

const labelCaps = { fontSize: 11, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant, letterSpacing: 0.5 } as const;
const cardStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderRadius: 16,
  padding: 16,
  shadowColor: authColors.primary,
  shadowOffset: { width: 0, height: 4 },
  shadowOpacity: 0.05,
  shadowRadius: 12,
  elevation: 2,
} as const;
const primaryBtn = { backgroundColor: authColors.primary, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' } as const;
const primaryBtnText = { fontSize: 14, fontFamily: authFont.semibold, color: authColors.onPrimary } as const;
const secondaryBtn = { backgroundColor: authColors.primaryFixed, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' } as const;
const secondaryBtnText = { fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary } as const;
