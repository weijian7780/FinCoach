import type { MaterialIcons } from '@expo/vector-icons';
import type { ComponentProps } from 'react';

type IconName = ComponentProps<typeof MaterialIcons>['name'];

// Fixed spending categories shown as chips in the profile-setup wizard.
export const SPENDING_CATEGORIES: { key: string; label: string; icon: IconName }[] = [
  { key: 'food', label: 'Food', icon: 'restaurant' },
  { key: 'transport', label: 'Transport', icon: 'directions-car' },
  { key: 'rent', label: 'Rent', icon: 'home' },
  { key: 'entertainment', label: 'Entertainment', icon: 'movie' },
  { key: 'education', label: 'Education', icon: 'school' },
  { key: 'others', label: 'Others', icon: 'more-horiz' },
];
