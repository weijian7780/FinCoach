import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, StatusBar, View } from 'react-native';

import { AppText as Text, AppTextInput as TextInput } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { createSavingsGoal, deleteSavingsGoal, fetchSavingsGoals, updateSavingsGoal } from '@/lib/finance';

type EditableGoal = { key: string; id?: number; name: string; target: string; current: string };

export default function SavingsScreen() {
  const { session } = useAuth();
  const userId = session?.user.id;

  const [goals, setGoals] = useState<EditableGoal[]>([]);
  const [removedIds, setRemovedIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const rows = await fetchSavingsGoals(userId);
      setGoals(rows.map((g) => ({ key: String(g.id), id: g.id, name: g.name, target: String(g.target_amount), current: String(g.current_amount) })));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load your goals.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  function updateGoal(key: string, patch: Partial<EditableGoal>) {
    setGoals((prev) => prev.map((g) => (g.key === key ? { ...g, ...patch } : g)));
  }
  function addGoal() {
    setGoals((prev) => [...prev, { key: `new-${Date.now()}`, name: '', target: '', current: '' }]);
  }
  function removeGoal(goal: EditableGoal) {
    if (goal.id != null) setRemovedIds((prev) => [...prev, goal.id as number]);
    setGoals((prev) => prev.filter((g) => g.key !== goal.key));
  }

  async function save() {
    if (!userId) return;
    setError(null);
    setSaving(true);
    try {
      await Promise.all(removedIds.map((id) => deleteSavingsGoal(id)));
      await Promise.all(
        goals
          .filter((goal) => goal.name.trim() && Number(goal.target) > 0)
          .map((goal) => {
            const payload = { name: goal.name.trim(), target_amount: Number(goal.target), current_amount: Number(goal.current) || 0 };
            return goal.id != null ? updateSavingsGoal(goal.id, payload) : createSavingsGoal(userId, payload);
          }),
      );
      router.back();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your goals.');
      setSaving(false);
    }
  }

  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: topPad, paddingHorizontal: 16, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable onPress={() => router.back()} hitSlop={8}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={{ fontSize: 20, fontFamily: authFont.bold, color: authColors.onSurface }}>Savings Goals</Text>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={authColors.primary} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 32 }} keyboardShouldPersistTaps="handled">
          {goals.length === 0 ? (
            <View style={[cardStyle, { alignItems: 'center', gap: 6, paddingVertical: 28 }]}>
              <MaterialIcons name="savings" size={36} color={authColors.primary} />
              <Text style={{ fontSize: 16, fontFamily: authFont.semibold, color: authColors.onSurface }}>No savings goals yet</Text>
              <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, textAlign: 'center' }}>
                Set a target like a new laptop or a trip, and track your progress.
              </Text>
            </View>
          ) : (
            goals.map((goal) => {
              const ratio = Number(goal.target) > 0 ? Math.min(1, (Number(goal.current) || 0) / Number(goal.target)) : 0;
              return (
                <View key={goal.key} style={[cardStyle, { gap: 12 }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <MaterialIcons name="flag" size={18} color={authColors.primary} />
                    <TextInput
                      style={[fieldStyle, { flex: 1 }]}
                      value={goal.name}
                      onChangeText={(value) => updateGoal(goal.key, { name: value })}
                      placeholder="Goal name (e.g. New Laptop)"
                      placeholderTextColor={authColors.outline}
                    />
                    <Pressable onPress={() => removeGoal(goal)} hitSlop={8}>
                      <MaterialIcons name="delete-outline" size={22} color={authColors.error} />
                    </Pressable>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text style={labelStyle}>Saved (RM)</Text>
                      <TextInput style={fieldStyle} value={goal.current} onChangeText={(value) => updateGoal(goal.key, { current: value })} placeholder="0" placeholderTextColor={authColors.outline} keyboardType="decimal-pad" />
                    </View>
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text style={labelStyle}>Target (RM)</Text>
                      <TextInput style={fieldStyle} value={goal.target} onChangeText={(value) => updateGoal(goal.key, { target: value })} placeholder="3000" placeholderTextColor={authColors.outline} keyboardType="decimal-pad" />
                    </View>
                  </View>
                  <View>
                    <View style={{ height: 8, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${ratio * 100}%`, backgroundColor: authColors.primary, borderRadius: 999 }} />
                    </View>
                    <Text style={{ fontSize: 12, fontFamily: authFont.semibold, color: authColors.primary, marginTop: 4, textAlign: 'right' }}>{Math.round(ratio * 100)}%</Text>
                  </View>
                </View>
              );
            })
          )}

          <Pressable onPress={addGoal} style={({ pressed }) => [{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderRadius: 12, borderWidth: 1.5, borderColor: authColors.primary, paddingVertical: 14 }, pressed && { opacity: 0.85 }]}>
            <MaterialIcons name="add" size={20} color={authColors.primary} />
            <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.primary }}>Add goal</Text>
          </Pressable>

          {error ? <Text style={{ fontSize: 14, fontFamily: authFont.regular, color: authColors.error }}>{error}</Text> : null}

          <Pressable
            disabled={saving}
            onPress={() => void save()}
            style={({ pressed }) => [{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: authColors.primary, paddingVertical: 16, borderRadius: 14 }, pressed && { opacity: 0.9 }]}>
            {saving ? (
              <ActivityIndicator color={authColors.onPrimary} />
            ) : (
              <>
                <MaterialIcons name="check" size={20} color={authColors.onPrimary} />
                <Text style={{ fontSize: 15, fontFamily: authFont.semibold, color: authColors.onPrimary }}>Save Goals</Text>
              </>
            )}
          </Pressable>
        </ScrollView>
      )}
    </View>
  );
}

const labelStyle = { fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant, marginLeft: 2 } as const;
const fieldStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 1,
  borderColor: authColors.outlineVariant,
  borderRadius: 8,
  paddingHorizontal: 14,
  paddingVertical: 11,
  fontSize: 14,
  fontFamily: authFont.regular,
  color: authColors.onSurface,
} as const;
const cardStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderRadius: 12,
  borderWidth: 0.5,
  borderColor: authColors.outlineVariant,
  padding: 14,
} as const;
