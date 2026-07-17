import { MaterialIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import type { ComponentProps } from 'react';
import { useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StatusBar, Switch, View } from 'react-native';
import type { StyleProp, TextStyle } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

export default function AppSettingsScreen() {
  const [notifications, setNotifications] = useState(true);
  const topPad = (Platform.OS === 'android' ? (StatusBar.currentHeight ?? 24) : 47) + 8;

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      {/* Top app bar */}
      <View style={{ paddingTop: topPad, paddingHorizontal: 16, paddingBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable onPress={() => router.back()} hitSlop={8}>
          <MaterialIcons name="arrow-back" size={24} color={authColors.onSurface} />
        </Pressable>
        <Text style={{ fontSize: 20, fontFamily: authFont.bold, color: authColors.onSurface }}>App Settings</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
        <SectionLabel>PREFERENCES</SectionLabel>
        <SettingRow
          icon="notifications"
          label="Notifications"
          trailing={
            <Switch
              value={notifications}
              onValueChange={setNotifications}
              trackColor={{ false: authColors.surfaceContainerHigh, true: authColors.primary }}
              thumbColor="#ffffff"
            />
          }
        />
        <SettingRow
          icon="payments"
          label="Currency"
          value="MYR (RM)"
          onPress={() => Alert.alert('Currency', 'Only MYR (RM) is supported.')}
        />

        <SectionLabel style={{ marginTop: 12 }}>DATA</SectionLabel>
        <SettingRow
          icon="storage"
          label="Export & Backup"
          onPress={() => router.push('/export-backup' as never)}
        />
      </ScrollView>
    </View>
  );
}

function SectionLabel({ children, style }: { children: React.ReactNode; style?: StyleProp<TextStyle> }) {
  return (
    <Text style={[{ fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant, letterSpacing: 0.6, marginLeft: 4 }, style]}>
      {children}
    </Text>
  );
}

function SettingRow({
  icon,
  label,
  value,
  trailing,
  onPress,
}: {
  icon: IconName;
  label: string;
  value?: string;
  trailing?: React.ReactNode;
  onPress?: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [cardStyle, { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16 }, pressed && onPress ? { opacity: 0.85 } : null]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }}>
        <View style={{ padding: 8, backgroundColor: authColors.primaryFixed, borderRadius: 8 }}>
          <MaterialIcons name={icon} size={22} color={authColors.primary} />
        </View>
        <View>
          <Text style={{ fontSize: 16, fontFamily: authFont.regular, color: authColors.onSurface }}>{label}</Text>
          {value ? <Text style={{ fontSize: 12, fontFamily: authFont.semibold, color: authColors.primary }}>{value}</Text> : null}
        </View>
      </View>
      {trailing ?? (onPress ? <MaterialIcons name="chevron-right" size={22} color={authColors.onSurfaceVariant} /> : null)}
    </Pressable>
  );
}

const cardStyle = {
  backgroundColor: authColors.surfaceContainerLowest,
  borderRadius: 12,
  shadowColor: authColors.primary,
  shadowOffset: { width: 0, height: 4 },
  shadowOpacity: 0.05,
  shadowRadius: 12,
  elevation: 2,
} as const;
