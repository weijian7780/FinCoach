import { MaterialIcons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { ProgressRing } from '@/components/savings/progress-ring';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { formatGoalDate, formatMoney, getGoalStatus, getSavingsMetrics, todayIsoDate } from '@/lib/savings-domain';
import type { SavingsGoal } from '@/lib/types';

type GoalCardProps = { goal: SavingsGoal; onPress: () => void };

export function GoalCard({ goal, onPress }: GoalCardProps) {
  const metrics = getSavingsMetrics(goal.current_amount, goal.target_amount);
  const status = getGoalStatus(
    { currentAmount: goal.current_amount, targetAmount: goal.target_amount, createdAt: goal.created_at, deadline: goal.deadline },
    todayIsoDate(),
  );

  return (
    <Pressable
      accessibilityHint="Opens goal details and contribution history"
      accessibilityLabel={`${goal.name}, ${metrics.percentage} percent saved`}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [cardStyle, pressed && { opacity: 0.88, transform: [{ scale: 0.995 }] }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={iconStyle}>
            <MaterialIcons name="savings" size={23} color={authColors.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text numberOfLines={2} style={{ fontSize: 18, lineHeight: 23, fontFamily: authFont.semibold, color: authColors.onSurface }}>
              {goal.name}
            </Text>
            <Text style={{ marginTop: 2, fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant }}>SAVINGS GOAL</Text>
          </View>
        </View>
        <MaterialIcons name="chevron-right" size={24} color={authColors.outline} />
      </View>

      <View style={{ alignItems: 'center', paddingVertical: 14 }}>
        <ProgressRing color={status.color} progress={metrics.ratio}>
          <Text style={{ fontSize: 18, fontFamily: authFont.bold, color: status.color }}>{metrics.percentage}%</Text>
          <Text style={{ marginTop: 2, fontSize: 18, fontFamily: authFont.bold, color: authColors.onSurface }}>
            {formatMoney(metrics.currentAmount)}
          </Text>
          <Text style={{ fontSize: 12, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>
            of {formatMoney(metrics.targetAmount)}
          </Text>
        </ProgressRing>
      </View>

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <MaterialIcons name="calendar-today" size={16} color={authColors.onSurfaceVariant} />
          <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant }}>{formatGoalDate(goal.deadline)}</Text>
        </View>
        <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurface }}>
          {formatMoney(metrics.remainingAmount)} left
        </Text>
      </View>

      <View style={{ height: 1, marginVertical: 12, backgroundColor: authColors.outlineVariant, opacity: 0.65 }} />
      <Text style={{ alignSelf: 'flex-end', fontSize: 14, fontFamily: authFont.bold, color: status.color }}>{status.label}</Text>
    </Pressable>
  );
}

const iconStyle = {
  width: 44,
  height: 44,
  borderRadius: 22,
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: authColors.primaryFixed,
} as const;

const cardStyle = {
  padding: 18,
  borderRadius: 18,
  backgroundColor: authColors.surfaceContainerLowest,
  borderWidth: 0.5,
  borderColor: authColors.outlineVariant,
  shadowColor: authColors.primary,
  shadowOffset: { width: 0, height: 5 },
  shadowOpacity: 0.07,
  shadowRadius: 14,
  elevation: 3,
} as const;
