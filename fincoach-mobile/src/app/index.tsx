import { Redirect } from 'expo-router';

import { LoadingState } from '@/components/ui/loading-state';
import { useAuth } from '@/lib/auth-context';

export default function IndexRoute() {
  const { loading, profile, session } = useAuth();

  if (loading) {
    return <LoadingState label="Checking secure session" />;
  }

  if (!session) {
    return <Redirect href="/onboarding" />;
  }

  if (!profile?.onboarding_completed) {
    return <Redirect href="/profile/setup" />;
  }

  return <Redirect href="/(app)" />;
}
