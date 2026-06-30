import { MaterialIcons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';

import { authColors, authFont } from '@/constants/auth-theme';

export default function AppLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: authColors.primary,
        tabBarInactiveTintColor: authColors.outline,
        tabBarStyle: { backgroundColor: authColors.surfaceContainerLowest, borderTopColor: authColors.outlineVariant },
        tabBarLabelStyle: { fontFamily: authFont.semibold, fontSize: 11 },
      }}>
      <Tabs.Screen
        name="index"
        options={{ title: 'Home', tabBarIcon: ({ color, size }) => <MaterialIcons name="home" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="transactions"
        options={{ title: 'Transactions', tabBarIcon: ({ color, size }) => <MaterialIcons name="account-balance-wallet" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="coach"
        options={{ title: 'Coach', tabBarIcon: ({ color, size }) => <MaterialIcons name="smart-toy" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="budget"
        options={{ title: 'Budget', tabBarIcon: ({ color, size }) => <MaterialIcons name="pie-chart" size={size} color={color} /> }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Profile', tabBarIcon: ({ color, size }) => <MaterialIcons name="person" size={size} color={color} /> }}
      />
    </Tabs>
  );
}
