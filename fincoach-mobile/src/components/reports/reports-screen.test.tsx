import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import ReportsScreen from './reports-screen';

const fx = vi.hoisted(() => ({ owner: 'owner', blur: null as null | (() => void), source: vi.fn(), categories: vi.fn(), focus: null as null | (() => void | (() => void)), foreground: null as null | ((state: string) => void) }));
vi.mock('@expo/vector-icons', () => ({ MaterialIcons: 'Icon' }));
vi.mock('expo-router', async () => {
  const React = await import('react');
  return { router: { back: vi.fn() }, useFocusEffect: (effect: () => void | (() => void)) => { fx.focus = effect; React.useEffect(() => { const cleanup = effect(); fx.blur = cleanup || null; return cleanup; }, [effect]); } };
});
vi.mock('react-native', () => ({ ActivityIndicator: 'ActivityIndicator', Pressable: 'Pressable', RefreshControl: 'RefreshControl', ScrollView: 'ScrollView', View: 'View', AppState: { addEventListener: (_event: string, listener: (state: string) => void) => { fx.foreground = listener; return { remove: () => { fx.foreground = null; } }; } } }));
vi.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) }));
vi.mock('@/components/ui/app-text', () => ({ AppText: 'Text' }));
vi.mock('@/components/reports/report-components', () => ({ ReportFilters: 'ReportFilters', ReportDashboard: 'ReportDashboard' }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ session: { user: { id: fx.owner } } }) }));
vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('@/lib/reports', async (original) => ({ ...await original<typeof import('@/lib/reports')>(), fetchReportSourceData: fx.source }));
vi.mock('@/lib/transactions', () => ({ fetchTransactionCategories: fx.categories }));

let renderer: ReactTestRenderer | undefined;
const source = (amount = 10) => ({ transactions: [{ id: 't', category_id: 1, amount, transaction_date: '2026-10-02', category: { id: 1, type: 'expense', name: 'Food', color: null } }], monthlyBudgets: [], categoryLimits: [], savingsGoals: [] });
const filters = () => renderer!.root.findByType('ReportFilters' as never).props;
const report = () => renderer!.root.findByType('ReportDashboard' as never).props.report;
const screenText = () => renderer!.root.findAllByType('Text' as never).flatMap((node) => node.children.filter((child) => typeof child === 'string' || typeof child === 'number')).join(' ');
const refresh = () => renderer!.root.findByType('ScrollView' as never).props.refreshControl.props.onRefresh();
function deferred() { let resolve!: (value: unknown) => void; let reject!: (error: Error) => void; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  fx.owner = 'owner';
  vi.useFakeTimers(); vi.setSystemTime(new Date(2026, 9, 21, 12));
  fx.source.mockReset().mockResolvedValue(source());
  fx.categories.mockReset().mockResolvedValue([{ id: 1, type: 'expense', name: 'Food' }, { id: 2, type: 'expense', name: 'Travel' }]);
});
afterEach(async () => { if (renderer) await act(async () => renderer!.unmount()); renderer = undefined; vi.useRealTimers(); });
const mount = async () => { await act(async () => { renderer = create(<ReportsScreen />); }); };

test('ignores a pending result after its selected category changes', async () => {
  await mount(); const pending = deferred(); fx.source.mockReturnValueOnce(pending.promise);
  await act(async () => filters().onView());
  await act(async () => filters().onCategoryChange(2));
  await act(async () => pending.resolve(source(123)));
  expect(filters().selection.categoryId).toBe(2);
  expect(renderer!.root.findAllByType('ReportDashboard' as never)).toHaveLength(0);
  expect(filters().viewing).toBe(false);
});
test('ignores older errors and finally updates while a newer refresh is pending', async () => {
  await mount(); const old = deferred(), fresh = deferred();
  fx.source.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
  await act(async () => filters().onView()); await act(async () => refresh());
  await act(async () => old.reject(new Error('old request')));
  expect(renderer!.root.findByType('ScrollView' as never).props.refreshControl.props.refreshing).toBe(true);
  await act(async () => fresh.resolve(source(50)));
  expect(report().totalExpenses).toBe(50);
  expect(screenText()).not.toContain('Report unavailable');
});
test.each(['source', 'categories'])('Retry restores category controls after initial %s failure', async (dependency) => {
  (dependency === 'source' ? fx.source : fx.categories).mockRejectedValueOnce(new Error('offline'));
  await mount();
  await act(async () => renderer!.root.findAllByType('Pressable' as never).at(-1)!.props.onPress());
  expect(report().totalExpenses).toBe(10);
  expect(filters().categories).toHaveLength(2);
});
test('validates incomplete custom dates on focus without querying', async () => {
  await mount(); await act(async () => filters().onPresetChange('custom'));
  await act(async () => filters().onStartDateChange('2026-10-'));
  fx.source.mockClear(); fx.categories.mockClear();
  await act(async () => { fx.focus!(); });
  expect(filters().validationError).toMatch(/valid.*date/i);
  expect(fx.source).not.toHaveBeenCalled(); expect(fx.categories).not.toHaveBeenCalled();
  expect(screenText()).not.toContain('Check your connection');
});
test('resolves relative presets on focus and preserves the category', async () => {
  await mount(); await act(async () => filters().onCategoryChange(2));
  vi.setSystemTime(new Date(2026, 10, 1, 12));
  await act(async () => { fx.focus!(); });
  expect(filters().selection).toMatchObject({ startDate: '2026-11-01', endDate: '2026-11-30', categoryId: 2 });
});
test('updates an open screen over a month boundary and leaves custom dates fixed', async () => {
  vi.setSystemTime(new Date(2026, 9, 31, 23, 59, 59)); await mount();
  await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
  expect(filters().selection.startDate).toBe('2026-11-01');
  await act(async () => filters().onPresetChange('custom'));
  const selected = filters().selection;
  vi.setSystemTime(new Date(2026, 11, 1));
  await act(async () => fx.foreground?.('active'));
  expect(filters().selection).toEqual(selected);
});
test('keeps matching previous results when refresh fails', async () => {
  await mount(); fx.source.mockRejectedValueOnce(new Error('offline'));
  await act(async () => refresh());
  expect(report().totalExpenses).toBe(10);
  expect(screenText()).toContain('last successful results');
});


test('invalidates work on blur and ignores callbacks retained by an inactive screen', async () => {
  await mount(); const pending = deferred(); fx.source.mockReturnValueOnce(pending.promise);
  await act(async () => filters().onView());
  const oldRefresh = refresh;
  await act(async () => fx.blur?.());
  const count = fx.source.mock.calls.length;
  await act(async () => oldRefresh());
  await act(async () => pending.resolve(source(777)));
  expect(fx.source).toHaveBeenCalledTimes(count);
  expect(report().totalExpenses).toBe(10);
});

test('unmount removes lifecycle subscriptions and ignores a late failure', async () => {
  const pending = deferred(); fx.source.mockReturnValueOnce(pending.promise);
  await mount(); await act(async () => renderer!.unmount()); renderer = undefined;
  expect(fx.foreground).toBeNull(); expect(vi.getTimerCount()).toBe(0);
  await act(async () => pending.reject(new Error('late offline')));
});

test.each([
  ['current_month', '2027-01-01', '2027-01-31'],
  ['previous_month', '2026-12-01', '2026-12-31'],
  ['last_3_months', '2026-11-01', '2027-01-31'],
])('refreshes %s across the year on foreground return', async (preset, startDate, endDate) => {
  vi.setSystemTime(new Date(2026, 11, 31)); await mount();
  await act(async () => filters().onPresetChange(preset));
  vi.setSystemTime(new Date(2027, 0, 1));
  await act(async () => fx.foreground?.('active'));
  expect(filters().selection).toMatchObject({ startDate, endDate });
});

test('does not retain a previous owner report when the new owner load fails', async () => {
  await mount(); fx.owner = 'another-owner'; fx.source.mockRejectedValueOnce(new Error('offline'));
  await act(async () => renderer!.update(<ReportsScreen />));
  expect(renderer!.root.findAllByType('ReportDashboard' as never)).toHaveLength(0);
  expect(filters().categories).toHaveLength(0);
  expect(screenText()).not.toContain('last successful results');
});
