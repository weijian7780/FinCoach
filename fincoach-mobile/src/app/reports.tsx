import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { Platform, Pressable, ScrollView, StatusBar, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

export default function ReportsScreen() {
  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={{ paddingTop: topPad, paddingHorizontal: 16, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable onPress={() => router.back()} hitSlop={8}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={{ fontSize: 20, fontFamily: authFont.bold, color: authColors.onSurface }}>Reports</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 32 }}>
        {/* Period */}
        <View style={[cardStyle, { alignItems: 'center' }]}>
          <Text style={{ fontSize: 11, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant, letterSpacing: 0.5 }}>CURRENT PERIOD</Text>
          <Text style={{ fontSize: 16, fontFamily: authFont.semibold, color: authColors.primary, marginTop: 2 }}>This Month</Text>
        </View>

        {/* Total spent */}
        <View style={cardStyle}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <MaterialIcons name="account-balance-wallet" size={18} color={authColors.primary} />
            <Text style={{ fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant }}>Total Spent</Text>
          </View>
          <Text style={{ fontSize: 30, fontFamily: authFont.bold, color: authColors.onSurface }}>RM 0</Text>
          <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, marginTop: 4 }}>No expenses recorded yet.</Text>
        </View>

        {/* Category breakdown empty state */}
        <View style={cardStyle}>
          <Text style={{ fontSize: 16, fontFamily: authFont.bold, color: authColors.onSurface, marginBottom: 12 }}>Category Breakdown</Text>
          <View style={{ alignItems: 'center', paddingVertical: 20, gap: 8 }}>
            <MaterialIcons name="pie-chart-outline" size={40} color={authColors.outline} />
            <Text style={{ fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface }}>Nothing to report yet</Text>
            <Text style={{ fontSize: 13, fontFamily: authFont.regular, color: authColors.onSurfaceVariant, textAlign: 'center' }}>
              Once you start adding expenses, your spending by category and monthly trends will show up here.
            </Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

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
