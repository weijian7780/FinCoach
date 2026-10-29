import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ReportDashboard, ReportFilters } from '@/components/reports/report-components';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { ReportCalculationError, compileFinancialReport, createPresetSelection, validateReportSelection, withReportCategory } from '@/lib/report-domain';
import { fetchReportSourceData, ReportDataChangedError } from '@/lib/reports';
import { fetchTransactionCategories } from '@/lib/transactions';
import type { Category, FinancialReport, ReportPreset, ReportSelection } from '@/lib/types';

function reportErrorMessage(action: 'load' | 'view' | 'refresh') {
  if (action === 'view') return 'The report could not be displayed. Check your connection and try again.';
  if (action === 'refresh') return 'The report could not be refreshed. Your last successful results are still shown.';
  return 'Financial data could not be loaded. Check your connection and try again.';
}

export default function ReportsScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [selection, setSelection] = useState<ReportSelection>(() => createPresetSelection('current_month'));
  const selectionRef = useRef(selection);
  const [report, setReport] = useState<FinancialReport | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const requestId = useRef(0);
  const focused = useRef(false);
  const reportOwner = useRef(userId);
  const reportRef = useRef<FinancialReport | null>(null);

  const replaceSelection = useCallback((next: ReportSelection) => {
    // Invalidate synchronously: a pending promise can settle before effects run.
    requestId.current += 1;
    selectionRef.current = next;
    reportRef.current = null;
    setSelection(next);
    setReport(null);
    setValidationError(null);
    setError(null);
    setLoading(false);
    setViewing(false);
    setRefreshing(false);
  }, []);

  const runReport = useCallback(async (action: 'load' | 'view' | 'refresh') => {
    if (!focused.current) return;
    if (!userId) { setLoading(false); return; }
    let activeSelection = selectionRef.current;
    if (activeSelection.preset !== 'custom') {
      const resolved = withReportCategory(createPresetSelection(activeSelection.preset), activeSelection.categoryId);
      if (resolved.startDate !== activeSelection.startDate || resolved.endDate !== activeSelection.endDate) {
        replaceSelection(resolved);
        activeSelection = resolved;
      }
    }
    const currentRequest = ++requestId.current;
    const isCurrent = () => focused.current && currentRequest === requestId.current;
    const selectionError = validateReportSelection(activeSelection);
    setValidationError(selectionError);
    setError(null);
    setLoading(false);
    setViewing(false);
    setRefreshing(false);
    if (selectionError) return;
    setLoading(action === 'load');
    setViewing(action === 'view');
    setRefreshing(action === 'refresh');
    try {
      const [availableCategories, source] = await Promise.all([
        fetchTransactionCategories(userId),
        fetchReportSourceData(userId, activeSelection),
      ]);
      if (!isCurrent()) return;
      const compiled = compileFinancialReport(source, activeSelection);
      reportRef.current = compiled;
      setCategories(availableCategories);
      setReport(compiled);
    } catch (failure) {
      if (!isCurrent()) return;
      const retained = reportRef.current !== null;
      setError(failure instanceof ReportCalculationError || failure instanceof ReportDataChangedError
        ? failure.message : reportErrorMessage(action === 'refresh' && !retained ? 'view' : action));
    } finally {
      // An older finally must never stop the newer operation's spinner.
      if (isCurrent()) { setLoading(false); setViewing(false); setRefreshing(false); }
    }
  }, [replaceSelection, userId]);

  const loadPreview = useCallback(() => runReport('load'), [runReport]);
  const viewReport = useCallback(() => runReport('view'), [runReport]);
  const refreshReport = useCallback(() => runReport('refresh'), [runReport]);

  useFocusEffect(useCallback(() => {
    focused.current = true;
    if (reportOwner.current !== userId) {
      reportOwner.current = userId;
      replaceSelection(withReportCategory(selectionRef.current, null));
      setCategories([]);
    }
    void loadPreview();
    let timer: ReturnType<typeof setTimeout>;
    const recheckMonth = () => {
      const current = selectionRef.current;
      if (current.preset !== 'custom') {
        const resolved = createPresetSelection(current.preset);
        if (resolved.startDate !== current.startDate || resolved.endDate !== current.endDate) void loadPreview();
      }
    };
    const schedule = () => {
      const now = new Date();
      const boundary = new Date(now.getFullYear(), now.getMonth() + 1, 1).getTime();
      // Rearm at most a day ahead to avoid timer overflow and handle clock changes.
      timer = setTimeout(() => { recheckMonth(); schedule(); }, Math.max(1, Math.min(86_400_000, boundary - now.getTime())));
    };
    schedule();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') recheckMonth();
    });
    return () => {
      focused.current = false;
      requestId.current += 1;
      clearTimeout(timer);
      subscription.remove();
    };
  }, [loadPreview, replaceSelection, userId]));

  const changePreset = useCallback((preset: ReportPreset) => {
    replaceSelection(withReportCategory(createPresetSelection(preset), selectionRef.current.categoryId));
  }, [replaceSelection]);

  const changeCategory = useCallback((categoryId: number | null) => {
    replaceSelection(withReportCategory(selectionRef.current, categoryId));
  }, [replaceSelection]);

  const changeCustomDate = useCallback((key: 'startDate' | 'endDate', value: string) => {
    replaceSelection({ ...selectionRef.current, [key]: value });
  }, [replaceSelection]);

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => router.back()} hitSlop={8} style={styles.backButton}>
          <MaterialIcons name="arrow-back" size={23} color={authColors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}><Text style={styles.pageTitle}>Reports & Analytics</Text><Text style={styles.pageSubtitle}>View interactive analysis inside FinCoach</Text></View>
      </View>

      {loading ? (
        <View style={styles.centerState}><ActivityIndicator size="large" color={authColors.primary} /><Text style={styles.stateTitle}>Compiling your finances…</Text><Text style={styles.stateCopy}>Loading transactions, budgets, and savings goals.</Text></View>
      ) : (
        <ScrollView
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refreshReport()} tintColor={authColors.primary} colors={[authColors.primary]} />}
          contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 32, gap: 16 }}
          keyboardShouldPersistTaps="handled"
        >
          <ReportFilters
            selection={selection}
            categories={categories}
            onPresetChange={changePreset}
            onCategoryChange={changeCategory}
            onStartDateChange={(value) => changeCustomDate('startDate', value)}
            onEndDateChange={(value) => changeCustomDate('endDate', value)}
            onView={() => void viewReport()}
            viewing={viewing}
            validationError={validationError}
          />
          {error ? (
            <View accessibilityRole="alert" style={styles.errorCard}>
              <MaterialIcons name="cloud-off" size={23} color={authColors.error} />
              <View style={{ flex: 1 }}><Text style={styles.errorTitle}>Report unavailable</Text><Text style={styles.stateCopy}>{error}</Text></View>
              <Pressable accessibilityRole="button" onPress={() => void refreshReport()}><Text style={styles.retryText}>Retry</Text></Pressable>
            </View>
          ) : null}
          {report ? <ReportDashboard report={report} /> : !error ? <View style={styles.centerCard}><MaterialIcons name="analytics" size={34} color={authColors.primary} /><Text style={styles.stateTitle}>Choose filters to view your report</Text></View> : null}
        </ScrollView>
      )}
    </View>
  );
}

const styles = {
  topBar: { minHeight: 76, paddingHorizontal: 16, paddingBottom: 11, flexDirection: 'row', alignItems: 'center', gap: 11, backgroundColor: authColors.surface } as const,
  backButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest } as const,
  pageTitle: { fontSize: 20, lineHeight: 25, fontFamily: authFont.bold, color: authColors.onSurface } as const,
  pageSubtitle: { marginTop: 1, fontSize: 12, lineHeight: 16, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  centerState: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28, gap: 9 } as const,
  centerCard: { minHeight: 150, alignItems: 'center', justifyContent: 'center', gap: 10, borderRadius: 18, padding: 20, backgroundColor: authColors.surfaceContainerLowest } as const,
  stateTitle: { fontSize: 16, fontFamily: authFont.semibold, color: authColors.onSurface, textAlign: 'center' } as const,
  stateCopy: { fontSize: 13, lineHeight: 18, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  errorCard: { borderWidth: 1, borderColor: '#F3B6B6', borderRadius: 16, padding: 14, backgroundColor: '#FFF4F4', flexDirection: 'row', alignItems: 'center', gap: 11 } as const,
  errorTitle: { fontSize: 14, fontFamily: authFont.semibold, color: authColors.error } as const,
  retryText: { fontSize: 13, fontFamily: authFont.bold, color: authColors.primary } as const,
} as const;
