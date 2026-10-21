import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('Alert and reminder UI', () => {
  test('alerts inbox follows the prototype filters and grouped history', () => {
    const source = read('src', 'app', 'alerts', 'index.tsx');

    expect(source).toContain('Alerts');
    expect(source).toContain("'All'");
    expect(source).toContain("'Insights'");
    expect(source).toContain("'Alerts'");
    expect(source).toContain('Today');
    expect(source).toContain('Yesterday');
    expect(source).toContain('Earlier');
    expect(source).toContain('markAllAlertsRead');
    expect(source).toContain('fetchAlerts');
    expect(source).toContain('postgres_changes');
    expect(source).toContain("'/alerts/settings'");
    expect(source).not.toContain('styles.moduleTabs');
    expect(source).not.toContain("router.replace('/alerts/reminders'");
  });

  test('alert cards support opening and swipe dismissal', () => {
    const source = read('src', 'components', 'notifications', 'alert-card.tsx');

    expect(source).toContain('PanResponder');
    expect(source).toContain('onDismiss');
    expect(source).toContain('onOpen');
    expect(source).toContain('delete-outline');
  });

  test('main app notification bells open the alert inbox and show unread state', () => {
    const bell = read('src', 'components', 'notifications', 'notification-bell.tsx');
    const home = read('src', 'app', '(app)', 'index.tsx');
    const profile = read('src', 'app', '(app)', 'profile.tsx');

    expect(bell).toContain('fetchUnreadAlertCount');
    expect(bell).toContain("router.push('/alerts'");
    expect(home).toContain('NotificationBell');
    expect(profile).toContain('NotificationBell');
  });

  test('settings use a compact overview and focused preference sheet', () => {
    const source = read('src', 'app', 'alerts', 'settings.tsx');

    expect(source).toContain('ensureNotificationPreferences');
    expect(source).toContain('saveNotificationPreferences');
    expect(source).toContain('Phone notifications');
    expect(source).toContain('Budget alerts');
    expect(source).toContain('Savings reminders');
    expect(source).toContain('Spending check-in');
    expect(source).toContain('Manage reminders');
    expect(source).toContain('Changes save automatically');
    expect(source).toContain('PreferenceSheet');
    expect(source).toContain('Modal');
    expect(source).toContain('savings_lead_days');
    expect(source).toContain('savings_reminder_time');
    expect(source).toContain('spending_frequency');
    expect(source).toContain('spending_weekday');
    expect(source).toContain('spending_reminder_time');
    expect(source).toContain("'/alerts/reminders'");
    expect(source).toContain('ExpoDateTimePicker');
    expect(source).not.toContain('Save settings');
    expect(source).not.toContain('Progress milestones');
    expect(source).not.toContain('Default lead time');
    expect(source).not.toContain('keyboardType="numbers-and-punctuation"');
  });

  test('reminder times use the Expo native dialog instead of manual entry', () => {
    const picker = read('src', 'components', 'notifications', 'time-picker-field.tsx');
    const manage = read('src', 'app', 'alerts', 'reminders', 'manage.tsx');

    expect(picker).toContain("@expo/ui/community/datetime-picker");
    expect(picker).toContain('mode="time"');
    expect(picker).toContain('presentation="dialog"');
    expect(picker).toContain('is24Hour');
    expect(picker).toContain('onDismiss');
    expect(manage).toContain('TimePickerField');
    expect(manage).not.toContain('keyboardType="numbers-and-punctuation"');
  });

  test('bill reminder screens support history, CRUD and recurrence', () => {
    const list = read('src', 'app', 'alerts', 'reminders.tsx');
    const renderedList = read('src', 'components', 'notifications', 'reminders-list-screen.tsx');
    const manage = read('src', 'app', 'alerts', 'reminders', 'manage.tsx');

    expect(list).toContain('fetchReminders');
    expect(list).toContain('setReminderEnabled');
    expect(list).toContain('Upcoming bill reminders');
    expect(list).toContain("'/alerts/reminders/manage'");
    expect(renderedList).toContain('RemindersListScreen');
    expect(renderedList).toContain('fetchReminders');
    expect(renderedList).toContain("'/alerts/reminders/manage'");
    expect(renderedList).not.toContain('styles.moduleTabs');
    expect(renderedList).not.toContain('accessibilityRole="tab"');
    expect(renderedList).not.toContain("router.replace('/alerts'");
    expect(manage).toContain('createReminder');
    expect(manage).toContain('updateReminder');
    expect(manage).toContain('deleteReminder');
    expect(manage).toContain('validateBillReminderInput');
    expect(manage).toContain('DateField');
    expect(manage).toContain('recurrence_anchor_day');
    expect(manage).toContain('Weekly');
    expect(manage).toContain('Monthly');
    expect(manage).toContain('Yearly');
  });
});
